"""
cgctl index - Index a codebase for semantic search.

Scans project files, generates local embeddings, and stores them in ChromaDB.
"""

import typer
import os
from pathlib import Path
from typing import List, Optional

from cgctl.utils.output import (
    console, print_success, print_error, print_info,
    print_warning, print_header, print_stats, create_progress,
    print_file_tree
)
from cgctl.utils.validators import validate_project_path

app = typer.Typer(help="Index a codebase for semantic search")


def get_project_id(project_path: str) -> Optional[str]:
    """Get project ID from .codeguardian file."""
    config_file = Path(project_path) / ".codeguardian"
    if config_file.exists():
        content = config_file.read_text()
        for line in content.split("\n"):
            if line.startswith("project_id"):
                return line.split("=")[1].strip().strip('"')
    return None


def get_chroma_path(project_path: str) -> str:
    """Get the ChromaDB storage path for the project."""
    return str(Path(project_path) / "chroma_data")


def scan_files(project_path: str, extensions: List[str], exclude_dirs: List[str]) -> List[dict]:
    """Scan project for supported files."""
    files = []
    
    for root, dirs, filenames in os.walk(project_path):
        # Filter out excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for filename in filenames:
            ext = os.path.splitext(filename)[1]
            if ext in extensions:
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, project_path)
                
                try:
                    stat = os.stat(full_path)
                    files.append({
                        "path": rel_path,
                        "full_path": full_path,
                        "size": stat.st_size,
                    })
                except OSError:
                    continue
    
    return files


def detect_language(file_path: str) -> str:
    """Detect programming language from file extension."""
    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
    }
    ext = os.path.splitext(file_path)[1].lower()
    return ext_map.get(ext, "unknown")


@app.callback(invoke_without_command=True)
def index_project(
    ctx: typer.Context,
    path: str = typer.Argument(
        ".",
        help="Path to the project directory"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be indexed without actually indexing"
    ),
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Re-index even if already indexed (clears existing)"
    ),
):
    """
    Index a codebase for semantic search.
    
    This command scans your project files, generates embeddings using
    local sentence-transformers, and stores them in ChromaDB.
    
    No API keys required - all processing is done locally.
    
    Example:
        cgctl index
        cgctl index /path/to/project --dry-run
        cgctl index --force  # Re-index everything
    """
    print_header("CodeGuardian Indexing", "Scanning and indexing your codebase locally")
    
    # Resolve path
    project_path = os.path.abspath(os.path.expanduser(path))
    
    # Validate path
    is_valid, error = validate_project_path(project_path)
    if not is_valid:
        print_error(error)
        raise typer.Exit(1)
    
    # Check for project initialization
    project_id = get_project_id(project_path)
    if not project_id:
        print_error("Project not initialized. Run 'cgctl init' first.")
        raise typer.Exit(1)
    
    print_info(f"Project ID: [cyan]{project_id}[/cyan]")
    print_info(f"Project path: [cyan]{project_path}[/cyan]")
    print_info(f"Using [green]local embeddings[/green] (sentence-transformers)")
    
    # Load settings
    try:
        from src.config.settings import get_settings
        settings = get_settings(project_path)
    except Exception as e:
        print_error(f"Failed to load settings: {e}")
        raise typer.Exit(1)
    
    # Scan for files
    print_info("Scanning for files...")
    files = scan_files(
        project_path,
        settings.indexing.supported_extensions,
        settings.indexing.exclude_dirs
    )
    
    if not files:
        print_warning("No supported files found.")
        raise typer.Exit(0)
    
    # Calculate stats
    total_size = sum(f["size"] for f in files)
    
    print_stats({
        "Files found": len(files),
        "Total size": f"{total_size / 1024:.1f} KB",
        "Extensions": ", ".join(settings.indexing.supported_extensions),
    })
    
    if dry_run:
        print_header("Dry Run - Files to Index")
        print_file_tree([f["path"] for f in files[:50]])
        if len(files) > 50:
            print_info(f"... and {len(files) - 50} more files")
        raise typer.Exit(0)
    
    # Start indexing
    print_header("Indexing Files")
    
    try:
        from src.embedding_generator import EmbeddingGenerator
        from src.vector_store import VectorStore
        from src.code_parser import CodeParser
        from src.text_chunker import TextChunker
        
        # Initialize local components
        print_info("Loading embedding model...")
        embedding_generator = EmbeddingGenerator()
        vector_store = VectorStore(persist_directory=get_chroma_path(project_path))
        parser = CodeParser()
        chunker = TextChunker()
        
        # Clear existing collection if force
        if force:
            print_info("Clearing existing index...")
            try:
                vector_store.delete_collection("codeguardian")
                print_info("Cleared existing index")
            except Exception:
                pass  # Collection might not exist
        
        # Create or get collection
        collection = vector_store.create_collection("codeguardian")
        
        total_chunks = 0
        total_lines = 0
        errors = []
        
        with create_progress() as progress:
            task = progress.add_task("Indexing files...", total=len(files))
            
            # Collect all chunks first
            all_chunks_data = []
            
            for file_info in files:
                try:
                    # Read file
                    with open(file_info["full_path"], "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    
                    line_count = content.count("\n") + 1
                    total_lines += line_count
                    
                    # Detect language
                    language = detect_language(file_info["path"])
                    
                    # Parse and chunk
                    parsed = parser.parse_file(file_info["path"], content)
                    chunks = chunker.chunk_code(parsed)
                    
                    for chunk in chunks:
                        chunk_id = f"{project_id}_{file_info['path']}_{chunk.metadata.start_line}_{chunk.metadata.end_line}"
                        all_chunks_data.append({
                            "id": chunk_id,
                            "text": chunk.content,
                            "metadata": {
                                "file_path": file_info["path"],
                                "start_line": chunk.metadata.start_line,
                                "end_line": chunk.metadata.end_line,
                                "chunk_type": chunk.metadata.chunk_type,
                                "language": language,
                                "function_name": chunk.metadata.function_name,
                                "class_name": chunk.metadata.class_name,
                                "project_id": project_id,
                            }
                        })
                        total_chunks += 1
                    
                except Exception as e:
                    errors.append({
                        "file": file_info["path"],
                        "error": str(e)
                    })
                
                progress.update(task, advance=1)
        
        # Generate embeddings in batches
        if all_chunks_data:
            print_info(f"Generating embeddings for {len(all_chunks_data)} chunks...")
            
            batch_size = 32
            with create_progress() as progress:
                task = progress.add_task("Generating embeddings...", total=len(all_chunks_data))
                
                for i in range(0, len(all_chunks_data), batch_size):
                    batch = all_chunks_data[i:i + batch_size]
                    texts = [c["text"] for c in batch]
                    
                    # Generate embeddings locally
                    embeddings = embedding_generator.generate_batch_embeddings(texts)
                    
                    # Store in ChromaDB
                    vector_store.add_embeddings(
                        collection_name="codeguardian",
                        embeddings=embeddings,
                        documents=texts,
                        metadatas=[c["metadata"] for c in batch],
                        ids=[c["id"] for c in batch]
                    )
                    
                    progress.update(task, advance=len(batch))
        
        # Summary
        print_header("Indexing Complete!")
        print_stats({
            "Files indexed": len(files),
            "Chunks created": total_chunks,
            "Total lines": total_lines,
            "Embedding model": "all-MiniLM-L6-v2 (384-dim)",
            "Storage": "ChromaDB (local)",
            "Errors": len(errors),
        })
        
        if errors:
            print_warning(f"\n{len(errors)} files had errors:")
            for err in errors[:5]:
                console.print(f"  [red]•[/red] {err['file']}: {err['error']}")
            if len(errors) > 5:
                console.print(f"  ... and {len(errors) - 5} more")
        
        print_success("\nCodebase indexed successfully!")
        print_info("Run [cyan]cgctl ask[/cyan] to retrieve context")
        print_info("Run [cyan]cgctl serve[/cyan] to start the MCP server")
        
    except Exception as e:
        print_error(f"Indexing failed: {e}")
        raise typer.Exit(1)


@app.command("status")
def index_status(
    path: str = typer.Option(".", "--path", "-p", help="Project path"),
):
    """
    Show indexing status for the current project.
    """
    project_path = os.path.abspath(os.path.expanduser(path))
    
    project_id = get_project_id(project_path)
    if not project_id:
        print_error("Project not initialized. Run 'cgctl init' first.")
        raise typer.Exit(1)
    
    try:
        from src.vector_store import VectorStore
        
        vector_store = VectorStore(persist_directory=get_chroma_path(project_path))
        stats = vector_store.get_collection_stats("codeguardian")
        
        print_header("Index Status")
        print_stats({
            "Collection": stats.name,
            "Chunks indexed": stats.count,
            "Embedding dimension": stats.dimension or 384,
            "Storage path": get_chroma_path(project_path),
        })
        
    except Exception as e:
        print_warning(f"Could not get index status: {e}")
        print_info("The index may not exist yet. Run 'cgctl index' first.")
