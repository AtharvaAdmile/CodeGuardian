#!/usr/bin/env python3
"""
Migration script to re-index codebase into Supabase.

This script:
1. Scans project files
2. Generates new 768-dim embeddings via Gemini
3. Inserts into Supabase pgvector
4. Shows progress bar
5. Reports statistics

Usage:
    python scripts/migrate_to_supabase.py /path/to/project

Or from project root:
    python scripts/migrate_to_supabase.py .
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()


def scan_files(project_path: str, extensions: List[str], exclude_dirs: List[str]) -> List[Dict]:
    """Scan project for supported files."""
    files = []
    
    for root, dirs, filenames in os.walk(project_path):
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


def main():
    parser = argparse.ArgumentParser(
        description="Migrate codebase to Supabase with new embeddings"
    )
    parser.add_argument(
        "project_path",
        help="Path to the project directory"
    )
    parser.add_argument(
        "--name",
        help="Project name (defaults to directory name)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for embedding generation"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    
    args = parser.parse_args()
    
    # Resolve path
    project_path = os.path.abspath(os.path.expanduser(args.project_path))
    
    if not os.path.isdir(project_path):
        print(f"Error: {project_path} is not a directory")
        sys.exit(1)
    
    project_name = args.name or os.path.basename(project_path)
    
    print("=" * 60)
    print("CodeGuardian Migration to Supabase")
    print("=" * 60)
    print(f"Project: {project_name}")
    print(f"Path: {project_path}")
    print(f"Batch size: {args.batch_size}")
    print()
    
    # Configuration
    extensions = [".py", ".js", ".jsx", ".ts", ".tsx"]
    exclude_dirs = [
        ".git", "__pycache__", "node_modules", "venv", ".venv",
        "env", ".env", "dist", "build", ".idea", ".vscode", "site-packages"
    ]
    
    # Scan files
    print("Scanning files...")
    files = scan_files(project_path, extensions, exclude_dirs)
    
    print(f"Found {len(files)} files")
    
    if args.dry_run:
        print("\n[DRY RUN] Files that would be indexed:")
        for f in files[:20]:
            print(f"  {f['path']}")
        if len(files) > 20:
            print(f"  ... and {len(files) - 20} more")
        return
    
    # Import after validation to avoid slow startup for --help
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
    from src.config.settings import get_settings
    from src.db.queries import (
        create_project, get_project_by_path, insert_file,
        insert_embeddings_batch, update_project_indexed, clear_project_embeddings
    )
    from src.llm.caller import generate_batch_embeddings
    from src.code_parser import CodeParser
    from src.text_chunker import TextChunker
    
    settings = get_settings(project_path)
    parser_obj = CodeParser()
    chunker = TextChunker()
    
    # Create or get project
    print("\nChecking Supabase project...")
    existing = get_project_by_path(project_path)
    
    if existing:
        project_id = existing['id']
        print(f"Found existing project: {project_id}")
        
        # Clear old embeddings
        print("Clearing old embeddings...")
        cleared = clear_project_embeddings(project_id)
        print(f"Cleared {cleared} old embeddings")
    else:
        project = create_project(name=project_name, root_path=project_path)
        project_id = project['id']
        print(f"Created new project: {project_id}")
    
    # Process files
    print("\nIndexing files...")
    
    total_chunks = 0
    total_lines = 0
    errors = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    ) as progress:
        task = progress.add_task("Processing files...", total=len(files))
        
        all_embeddings_data = []
        
        for file_info in files:
            try:
                # Read file
                with open(file_info["full_path"], "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                line_count = content.count("\n") + 1
                total_lines += line_count
                
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
                parsed = parser_obj.parse_file(file_info["path"], content)
                chunks = chunker.chunk_code(parsed)
                
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
                
                # Batch process embeddings
                if len(all_embeddings_data) >= args.batch_size:
                    batch = all_embeddings_data[:args.batch_size]
                    texts = [e["chunk_text"] for e in batch]
                    embeddings = generate_batch_embeddings(texts)
                    
                    for i, emb in enumerate(embeddings):
                        batch[i]["embedding"] = emb
                    
                    insert_embeddings_batch(batch)
                    all_embeddings_data = all_embeddings_data[args.batch_size:]
                
            except Exception as e:
                errors.append({"file": file_info["path"], "error": str(e)})
            
            progress.update(task, advance=1)
        
        # Process remaining
        if all_embeddings_data:
            texts = [e["chunk_text"] for e in all_embeddings_data]
            embeddings = generate_batch_embeddings(texts)
            
            for i, emb in enumerate(embeddings):
                all_embeddings_data[i]["embedding"] = emb
            
            insert_embeddings_batch(all_embeddings_data)
    
    # Update project stats
    update_project_indexed(project_id, len(files), total_lines)
    
    # Summary
    print()
    print("=" * 60)
    print("Migration Complete!")
    print("=" * 60)
    print(f"Project ID: {project_id}")
    print(f"Files indexed: {len(files)}")
    print(f"Chunks created: {total_chunks}")
    print(f"Total lines: {total_lines}")
    print(f"Errors: {len(errors)}")
    
    if errors:
        print("\nFiles with errors:")
        for err in errors[:10]:
            print(f"  - {err['file']}: {err['error']}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")
    
    print()
    print("Next steps:")
    print("  1. Run 'cgctl ask \"your question\"' to query your codebase")
    print("  2. Run 'cgctl config show' to view configuration")


if __name__ == "__main__":
    main()
