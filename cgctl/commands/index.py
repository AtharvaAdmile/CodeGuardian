"""
cgctl index - Index a codebase for semantic search.

Scans project files, generates embeddings, and stores them in Supabase.
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
        help="Re-index even if already indexed"
    ),
    show_tokens: bool = typer.Option(
        False,
        "--tokens",
        help="Display token usage for the request"
    ),
):
    """
    Index a codebase for semantic search.
    
    This command scans your project files, generates embeddings using
    Gemini, and stores them in Supabase for fast similarity search.
    
    Example:
        cgctl index
        cgctl index /path/to/project --dry-run
    """
    print_header("CodeGuardian Indexing", "Scanning and indexing your codebase")
    
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
        from src.db.queries import (
            insert_file, insert_embeddings_batch, 
            update_project_indexed, clear_project_embeddings
        )
        from src.llm.caller import generate_batch_embeddings
        from src.code_parser import CodeParser
        from src.text_chunker import TextChunker
        
        parser = CodeParser()
        chunker = TextChunker()
        
        # Clear existing embeddings if force
        if force:
            print_info("Clearing existing embeddings...")
            cleared = clear_project_embeddings(project_id)
            print_info(f"Cleared {cleared} existing embeddings")
        
        total_chunks = 0
        total_lines = 0
        total_tokens = 0
        errors = []
        
        from src.llm.caller import count_tokens
        
        with create_progress() as progress:
            task = progress.add_task("Indexing files...", total=len(files))
            
            # Process in batches
            batch_size = settings.embedding.batch_size
            all_embeddings_data = []
            
            for file_info in files:
                try:
                    # Read file
                    with open(file_info["full_path"], "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    
                    line_count = content.count("\n") + 1
                    total_lines += line_count
                    
                    # Detect language
                    language = detect_language(file_info["path"])
                    
                    # Insert file record
                    file_record = insert_file(
                        project_id=project_id,
                        path=file_info["path"],
                        language=language,
                        content=content,
                        line_count=line_count,
                    )
                    file_id = file_record["id"]
                    
                    # Parse and chunk
                    parsed = parser.parse_file(file_info["path"], content)
                    chunks = chunker.chunk_code(parsed)
                    
                    # Generate embeddings for chunks
                    for chunk in chunks:
                        all_embeddings_data.append({
                            "file_id": file_id,
                            "chunk_text": chunk.content,
                            "start_line": chunk.metadata.start_line,
                            "end_line": chunk.metadata.end_line,
                            "metadata": {
                                "chunk_type": chunk.metadata.chunk_type,
                                "language": chunk.metadata.language,
                                "function_name": chunk.metadata.function_name,
                                "class_name": chunk.metadata.class_name,
                            }
                        })
                        total_chunks += 1
                    
                    # Generate and store embeddings in batches
                    if len(all_embeddings_data) >= batch_size:
                        batch_data = all_embeddings_data[:batch_size]
                        texts = [e["chunk_text"] for e in batch_data]
                        
                        if show_tokens:
                            batch_tokens = sum(count_tokens(t) for t in texts)
                            total_tokens += batch_tokens
                        
                        embeddings = generate_batch_embeddings(texts)
                        
                        for i, emb in enumerate(embeddings):
                            batch_data[i]["embedding"] = emb
                        
                        insert_embeddings_batch(batch_data)
                        all_embeddings_data = all_embeddings_data[batch_size:]
                    
                except Exception as e:
                    errors.append({
                        "file": file_info["path"],
                        "error": str(e)
                    })
                
                progress.update(task, advance=1)
            
            # Process remaining embeddings
            if all_embeddings_data:
                texts = [e["chunk_text"] for e in all_embeddings_data]
                
                if show_tokens:
                    batch_tokens = sum(count_tokens(t) for t in texts)
                    total_tokens += batch_tokens
                
                embeddings = generate_batch_embeddings(texts)
                
                for i, emb in enumerate(embeddings):
                    all_embeddings_data[i]["embedding"] = emb
                
                insert_embeddings_batch(all_embeddings_data)
        
        # Update project stats
        update_project_indexed(project_id, len(files), total_lines)
        
        # Summary
        print_header("Indexing Complete!")
        print_stats({
            "Files indexed": len(files),
            "Chunks created": total_chunks,
            "Total lines": total_lines,
            "Total tokens": total_tokens if show_tokens else "N/A",
            "Errors": len(errors),
        })
        
        if errors:
            print_warning(f"\n{len(errors)} files had errors:")
            for err in errors[:5]:
                console.print(f"  [red]•[/red] {err['file']}: {err['error']}")
            if len(errors) > 5:
                console.print(f"  ... and {len(errors) - 5} more")
        
        print_success("\nCodebase indexed successfully!")
        print_info("Run [cyan]cgctl ask[/cyan] to start querying")
        
    except Exception as e:
        print_error(f"Indexing failed: {e}")
        raise typer.Exit(1)
