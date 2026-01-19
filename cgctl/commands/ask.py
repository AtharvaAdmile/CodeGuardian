"""
cgctl ask - Ask questions about your codebase.

Uses RAG to find relevant code and generates answers using the Universal LLM Caller.
"""

import typer
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from cgctl.utils.output import (
    console, print_success, print_error, print_info,
    print_warning, print_header, print_sources_table,
    print_code, print_markdown
)
from cgctl.utils.validators import validate_question

app = typer.Typer(help="Ask questions about your codebase")


def get_project_id(project_path: str) -> Optional[str]:
    """Get project ID from .codeguardian file."""
    config_file = Path(project_path) / ".codeguardian"
    if config_file.exists():
        content = config_file.read_text()
        for line in content.split("\n"):
            if line.startswith("project_id"):
                return line.split("=")[1].strip().strip('"')
    return None


# ============================================
# FUNCTION A: Context Gathering
# ============================================

def gather_ask_context(
    question: str,
    project_id: str,
    top_k: int = 5,
    similarity_threshold: float = 0.7
) -> Dict[str, Any]:
    """
    Function A: Gather context for answering a question.
    
    This function handles all the algorithmic/programmatic processing:
    - Generates embedding for the question
    - Searches vector store for similar chunks
    - Retrieves and formats relevant code context
    
    Args:
        question: User's question
        project_id: UUID of the project
        top_k: Number of results to retrieve
        similarity_threshold: Minimum similarity score
        
    Returns:
        Dictionary containing:
        - context: Formatted context string for LLM
        - sources: List of source references
        - metadata: Additional metadata
    """
    from src.llm.caller import generate_embedding
    from src.db.queries import match_embeddings
    
    # Generate embedding for the question
    question_embedding = generate_embedding(question)
    
    # Search for similar chunks
    matches = match_embeddings(
        query_embedding=question_embedding,
        match_threshold=similarity_threshold,
        match_count=top_k
    )
    
    if not matches:
        return {
            "context": "",
            "sources": [],
            "metadata": {"chunks_found": 0}
        }
    
    # Format context for LLM
    context_parts = []
    sources = []
    
    for i, match in enumerate(matches):
        context_parts.append(f"""
--- Source {i + 1}: {match['file_path']} (lines {match['start_line']}-{match['end_line']}) ---
{match['chunk_text']}
""")
        
        sources.append({
            "file_path": match['file_path'],
            "start_line": match['start_line'],
            "end_line": match['end_line'],
            "similarity": match['similarity'],
        })
    
    context = "\n".join(context_parts)
    
    return {
        "context": context,
        "sources": sources,
        "metadata": {
            "chunks_found": len(matches),
            "avg_similarity": sum(m['similarity'] for m in matches) / len(matches)
        }
    }


# ============================================
# System Prompt for Code Q&A
# ============================================

CODE_QA_SYSTEM_PROMPT = """You are CodeGuardian, an AI assistant that helps developers understand their codebase.

You have access to relevant code snippets from the user's project. Use this context to answer their questions accurately.

Guidelines:
1. Base your answers on the provided code context
2. Reference specific files and line numbers when applicable
3. If the context doesn't contain enough information, say so clearly
4. Provide code examples when helpful
5. Be concise but thorough

Format your response using markdown for better readability."""


@app.callback(invoke_without_command=True)
def ask_question(
    ctx: typer.Context,
    question: str = typer.Argument(
        ...,
        help="Your question about the codebase"
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
    no_stream: bool = typer.Option(
        False,
        "--no-stream",
        help="Disable streaming output"
    ),
    show_sources: bool = typer.Option(
        True,
        "--sources/--no-sources",
        help="Show source references"
     ),
    show_tokens: bool = typer.Option(
        False,
        "--tokens",
        help="Display token usage for the request"
    ),
):
    """
    Ask a question about your codebase.
    
    Uses RAG to find relevant code and generates an answer using the LLM.
    
    Example:
        cgctl ask "What does the main function do?"
        cgctl ask "How is authentication implemented?" --top-k 10
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
    
    # Load settings
    try:
        from src.config.settings import get_settings
        settings = get_settings(project_path)
    except Exception as e:
        print_error(f"Failed to load settings: {e}")
        raise typer.Exit(1)
    
    console.print()
    console.print(f"[bold cyan]Question:[/bold cyan] {question}")
    console.print()
    
    # Token counting for embedding call
    if show_tokens:
        try:
            from src.llm.caller import count_tokens
            tokens = count_tokens(question)
            print_info(f"Question tokens (Embedding input): [cyan]{tokens}[/cyan]")
        except Exception as e:
            print_warning(f"Failed to count tokens: {e}")

    # Function A: Gather context
    with console.status("[bold green]Searching codebase...[/bold green]"):
        try:
            context_result = gather_ask_context(
                question=question,
                project_id=project_id,
                top_k=top_k,
                similarity_threshold=settings.retrieval.similarity_threshold
            )
        except Exception as e:
            print_error(f"Failed to search codebase: {e}")
            raise typer.Exit(1)
    
    # Check if we found any context
    if not context_result["context"]:
        print_warning("No relevant code found for your question.")
        print_info("Try rephrasing your question or indexing more files.")
        raise typer.Exit(0)
    
    print_info(f"Found {context_result['metadata']['chunks_found']} relevant code chunks")
    console.print()
    
    # Token counting for generation call
    if show_tokens:
        try:
            from src.llm.caller import count_tokens
            full_text = f"System: {CODE_QA_SYSTEM_PROMPT}\n\nContext:\n{context_result['context']}\n\nUser: {question}"
            tokens = count_tokens(full_text)
            print_info(f"Full prompt tokens (Generation input): [cyan]{tokens}[/cyan]")
        except Exception as e:
            print_warning(f"Failed to count tokens: {e}")

    # Function X: Call LLM
    console.print("[bold cyan]Answer:[/bold cyan]")
    console.print()
    
    try:
        from src.llm.caller import llm_call, llm_stream
        
        if no_stream:
            # Non-streaming response
            answer = llm_call(
                prompt=question,
                context=context_result["context"],
                system_prompt=CODE_QA_SYSTEM_PROMPT,
            )
            print_markdown(answer)
        else:
            # Streaming response
            full_response = ""
            for chunk in llm_stream(
                prompt=question,
                context=context_result["context"],
                system_prompt=CODE_QA_SYSTEM_PROMPT,
            ):
                console.print(chunk, end="")
                full_response += chunk
            console.print()  # Final newline
        
    except Exception as e:
        print_error(f"Failed to generate answer: {e}")
        raise typer.Exit(1)
    
    # Show sources
    if show_sources and context_result["sources"]:
        console.print()
        print_sources_table(context_result["sources"])


@app.command("interactive")
def interactive_mode(
    path: str = typer.Option(
        ".",
        "--path", "-p",
        help="Path to the project directory"
    ),
):
    """
    Start an interactive Q&A session.
    
    Allows asking multiple questions without restarting the CLI.
    """
    # Resolve project path
    project_path = os.path.abspath(os.path.expanduser(path))
    
    # Check for project initialization
    project_id = get_project_id(project_path)
    if not project_id:
        print_error("Project not initialized. Run 'cgctl init' first.")
        raise typer.Exit(1)
    
    print_header("CodeGuardian Interactive Mode", "Type 'exit' or 'quit' to leave")
    
    from src.config.settings import get_settings
    from src.llm.caller import llm_stream
    
    settings = get_settings(project_path)
    
    while True:
        try:
            console.print()
            question = console.input("[bold cyan]You:[/bold cyan] ")
            
            if question.lower() in ("exit", "quit", "q"):
                print_info("Goodbye!")
                break
            
            if not question.strip():
                continue
            
            # Validate
            is_valid, error = validate_question(question)
            if not is_valid:
                print_warning(error)
                continue
            
            # Gather context
            with console.status("[dim]Searching...[/dim]"):
                context_result = gather_ask_context(
                    question=question,
                    project_id=project_id,
                    top_k=5,
                    similarity_threshold=settings.retrieval.similarity_threshold
                )
            
            if not context_result["context"]:
                print_warning("No relevant code found.")
                continue
            
            # Stream response
            console.print()
            console.print("[bold green]CodeGuardian:[/bold green] ", end="")
            
            for chunk in llm_stream(
                prompt=question,
                context=context_result["context"],
                system_prompt=CODE_QA_SYSTEM_PROMPT,
            ):
                console.print(chunk, end="")
            
            console.print()
            
        except KeyboardInterrupt:
            print_info("\nGoodbye!")
            break
        except Exception as e:
            print_error(f"Error: {e}")
