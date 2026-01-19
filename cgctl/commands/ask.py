"""
cgctl ask - Retrieve relevant code context from your codebase.

Uses local embeddings and vector search to find relevant code chunks.
Returns context that can be used by AI assistants like GitHub Copilot.
"""

import typer
import os
import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from cgctl.utils.output import (
    console, print_success, print_error, print_info,
    print_warning, print_header, print_sources_table,
    print_code
)
from cgctl.utils.validators import validate_question

app = typer.Typer(help="Retrieve relevant code context from your codebase")


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


# ============================================
# FUNCTION A: Context Retrieval (Local Only)
# ============================================

def retrieve_context(
    question: str,
    project_path: str,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Retrieve relevant code context using local embeddings.
    
    This function uses sentence-transformers for embeddings and
    ChromaDB for vector search. No external API calls are made.
    
    Args:
        question: User's question/query
        project_path: Path to the project
        top_k: Number of results to retrieve
        
    Returns:
        Dictionary containing:
        - chunks: List of relevant code chunks with content and metadata
        - sources: List of source references (file, line numbers)
        - metadata: Additional metadata
    """
    from src.embedding_generator import EmbeddingGenerator
    from src.vector_store import VectorStore
    from src.query_engine import QueryEngine
    
    # Initialize local components
    embedding_generator = EmbeddingGenerator()
    vector_store = VectorStore(persist_directory=get_chroma_path(project_path))
    query_engine = QueryEngine(
        embedding_generator=embedding_generator,
        vector_store=vector_store,
        collection_name="codeguardian"
    )
    
    # Generate embedding for the question (local)
    question_embedding = embedding_generator.generate_embedding(question)
    
    # Search for similar chunks
    chunks = query_engine.retrieve_chunks(question_embedding, n_results=top_k)
    
    if not chunks:
        return {
            "chunks": [],
            "sources": [],
            "context_text": "",
            "metadata": {"chunks_found": 0}
        }
    
    # Rerank for better relevance
    chunks = query_engine.rerank_results(chunks, question)
    
    # Format results
    formatted_chunks = []
    sources = []
    context_parts = []
    
    for i, chunk in enumerate(chunks):
        formatted_chunks.append({
            "id": chunk.id,
            "content": chunk.content,
            "file_path": chunk.file_path,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "chunk_type": chunk.chunk_type,
            "language": chunk.language,
            "distance": chunk.distance
        })
        
        sources.append({
            "file_path": chunk.file_path,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "similarity": 1.0 - chunk.distance,  # Convert distance to similarity
        })
        
        # Build context text for display/export
        context_parts.append(f"""
--- Source {i + 1}: {chunk.file_path} (lines {chunk.start_line}-{chunk.end_line}) ---
```{chunk.language}
{chunk.content}
```
""")
    
    context_text = "\n".join(context_parts)
    avg_similarity = sum(s['similarity'] for s in sources) / len(sources)
    
    return {
        "chunks": formatted_chunks,
        "sources": sources,
        "context_text": context_text,
        "metadata": {
            "chunks_found": len(chunks),
            "avg_similarity": round(avg_similarity, 3)
        }
    }


@app.callback(invoke_without_command=True)
def ask_question(
    ctx: typer.Context,
    question: str = typer.Argument(
        ...,
        help="Your question or search query about the codebase"
    ),
    path: str = typer.Option(
        ".",
        "--path", "-p",
        help="Path to the project directory"
    ),
    top_k: int = typer.Option(
        5,
        "--top-k", "-k",
        help="Number of code chunks to retrieve"
    ),
    output_json: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON (for programmatic use)"
    ),
    show_sources: bool = typer.Option(
        True,
        "--sources/--no-sources",
        help="Show source references"
    ),
    show_content: bool = typer.Option(
        True,
        "--content/--no-content",
        help="Show code content in output"
    ),
):
    """
    Retrieve relevant code context from your codebase.
    
    Uses local embeddings to find code that's relevant to your query.
    Returns context chunks that can be used with AI assistants.
    
    Example:
        cgctl ask "What does the main function do?"
        cgctl ask "How is authentication implemented?" --top-k 10
        cgctl ask "database queries" --json
    
    Note: This command only retrieves context. For AI-generated answers,
    use the MCP server with GitHub Copilot (cgctl serve).
    """
    # Validate question
    is_valid, error = validate_question(question)
    if not is_valid:
        print_error(error)
        raise typer.Exit(1)
    
    # Resolve project path
    project_path = os.path.abspath(os.path.expanduser(path))
    
    # Check for project initialization
    project_id = get_project_id(project_path)
    if not project_id:
        print_error("Project not initialized. Run 'cgctl init' first.")
        raise typer.Exit(1)
    
    if not output_json:
        console.print()
        console.print(f"[bold cyan]Query:[/bold cyan] {question}")
        console.print()
    
    # Retrieve context (local embeddings only)
    with console.status("[bold green]Searching codebase...[/bold green]") if not output_json else nullcontext():
        try:
            result = retrieve_context(
                question=question,
                project_path=project_path,
                top_k=top_k,
            )
        except Exception as e:
            if output_json:
                print(json.dumps({"error": str(e)}))
            else:
                print_error(f"Failed to search codebase: {e}")
            raise typer.Exit(1)
    
    # Check if we found any context
    if not result["chunks"]:
        if output_json:
            print(json.dumps({"chunks": [], "message": "No relevant code found"}))
        else:
            print_warning("No relevant code found for your query.")
            print_info("Try rephrasing your query or indexing more files.")
        raise typer.Exit(0)
    
    # Output results
    if output_json:
        # JSON output for programmatic use
        print(json.dumps(result, indent=2))
    else:
        # Human-readable output
        print_success(f"Found {result['metadata']['chunks_found']} relevant code chunks")
        print_info(f"Average similarity: {result['metadata']['avg_similarity']:.1%}")
        console.print()
        
        if show_content:
            console.print("[bold]Relevant Code:[/bold]")
            console.print(result["context_text"])
        
        if show_sources:
            print_sources_table(result["sources"])
        
        console.print()
        print_info("💡 Tip: Use this context with GitHub Copilot or run 'cgctl serve' to start the MCP server.")


# Context manager for silent operation
from contextlib import contextmanager, nullcontext


@app.command("context")
def get_context_only(
    query: str = typer.Argument(..., help="Search query"),
    path: str = typer.Option(".", "--path", "-p", help="Project path"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of chunks"),
):
    """
    Get raw context chunks as JSON (for scripting/piping).
    
    This is a simplified command that outputs only the context text,
    suitable for piping to other tools.
    
    Example:
        cgctl ask context "authentication" | pbcopy
    """
    project_path = os.path.abspath(os.path.expanduser(path))
    
    try:
        result = retrieve_context(
            question=query,
            project_path=project_path,
            top_k=top_k,
        )
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        raise typer.Exit(1)
