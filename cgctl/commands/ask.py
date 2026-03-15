"""
cgctl ask — Ask a natural-language question about the indexed codebase.

Connected mode:  streams from POST /api/ask/stream, rendering tokens
                 live with Rich Markdown as they arrive.

Offline mode:    falls back to local vector search via src.* (no LLM answer,
                 just ranked code chunks).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import typer
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from cgctl.utils.output import (
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
)

app = typer.Typer(help="Ask a question about the codebase")

_SEVERITY_COLOUR = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "dim",
}


def _read_project_id(project_path: str) -> str:
    cg = Path(project_path) / ".codeguardian" / "config.toml"
    if cg.exists():
        for line in cg.read_text().splitlines():
            if line.strip().startswith("project_id"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    flat = Path(project_path) / ".codeguardian"
    if flat.is_file():
        for line in flat.read_text().splitlines():
            if line.startswith("project_id"):
                return line.split("=", 1)[1].strip().strip('"')
    return os.path.basename(project_path)


# ── Main command ──────────────────────────────────────────────────────────


@app.callback(invoke_without_command=True)
def ask_question(
    ctx: typer.Context,
    question: str = typer.Argument(..., help="Natural-language question about the codebase"),
    path: str = typer.Option(".", "--path", "-p", help="Path to the project directory"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Override project ID"),
    no_stream: bool = typer.Option(False, "--no-stream", help="Use non-streaming mode (connected only)"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Chunks to retrieve (offline mode)"),
    output_json: bool = typer.Option(False, "--json", help="Output raw JSON (connected only)"),
):
    """
    Ask a natural-language question about the indexed codebase.

    In connected mode the answer is streamed from the server and rendered
    as Markdown with source citations and expert attribution.

    In offline mode (--offline) the command retrieves the most relevant
    code chunks using local embeddings — no LLM answer is generated.

    Examples:
        cgctl ask "How does the authentication flow work?"
        cgctl ask "Who owns server/routes/query.py?" --path /my/project
        cgctl ask "rate limiting" --offline
    """
    from cgctl.client import is_offline, make_client

    project_path = os.path.abspath(os.path.expanduser(path))
    pid = project_id or _read_project_id(project_path)

    console.print()
    console.print(Panel(f"[bold]{question}[/bold]", title="[cyan]Question[/cyan]", border_style="cyan"))
    console.print()

    if is_offline():
        _ask_offline(question, project_path, pid, top_k)
        return

    client = make_client()
    try:
        if no_stream:
            _ask_blocking(client, pid, question, output_json)
        else:
            _ask_streaming(client, pid, question, output_json)
    except ConnectionError as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        print_error(f"Query failed: {exc}")
        raise typer.Exit(1)


# ── Connected: streaming ──────────────────────────────────────────────────


def _ask_streaming(client, pid: str, question: str, output_json: bool) -> None:
    payload = {"project_id": pid, "question": question, "conversation_history": []}

    sources: list[dict] = []
    decisions: list[dict] = []
    experts: list[dict] = []
    answer_parts: list[str] = []

    with console.status("[bold green]Querying…[/bold green]", spinner="dots"):
        # Consume first event to confirm connection before removing spinner
        first = True
        for event in client.stream_post("/api/ask/stream", payload):
            if first:
                first = False

            etype = event.get("type")

            if etype == "source":
                sources.append(event.get("source", {}))

            elif etype == "chunk":
                answer_parts.append(event.get("content", ""))

            elif etype == "metadata":
                decisions = event.get("decisions", [])
                experts = event.get("experts", [])

            elif etype == "error":
                print_error(event.get("message", "Stream error"))
                return

    if output_json:
        print(json.dumps({
            "answer": "".join(answer_parts),
            "sources": sources,
            "decisions": decisions,
            "experts": experts,
        }, indent=2))
        return

    # Render answer
    answer = "".join(answer_parts).strip()
    if answer:
        console.print(Markdown(answer))

    _render_sources(sources)
    _render_decisions(decisions)
    _render_experts(experts)


# ── Connected: non-streaming ──────────────────────────────────────────────


def _ask_blocking(client, pid: str, question: str, output_json: bool) -> None:
    payload = {"project_id": pid, "question": question, "conversation_history": []}

    with console.status("[bold green]Querying…[/bold green]"):
        data = client.post("/api/ask", payload)

    if output_json:
        print(json.dumps(data, indent=2))
        return

    answer = data.get("answer", "").strip()
    if answer:
        console.print(Markdown(answer))

    _render_sources(data.get("sources", []))
    _render_decisions(data.get("decisions_referenced", []))
    _render_experts(data.get("experts", []))


# ── Rich renderers ────────────────────────────────────────────────────────


def _render_sources(sources: list[dict]) -> None:
    if not sources:
        return
    console.print()
    console.print(Rule("[dim]Sources[/dim]", style="dim"))
    seen: set[str] = set()
    table = Table(show_header=True, header_style="bold dim", box=None)
    table.add_column("File", style="cyan")
    table.add_column("Lines", justify="center", style="dim")
    table.add_column("Relevance", justify="right", style="dim")
    for s in sources:
        fp = s.get("file_path", "")
        if fp in seen:
            continue
        seen.add(fp)
        start = s.get("start_line")
        end = s.get("end_line")
        lines = f"{start}–{end}" if start else "—"
        score = s.get("relevance_score", 0.0)
        table.add_row(fp, lines, f"{score:.2f}")
    console.print(table)


def _render_decisions(decisions: list[dict]) -> None:
    if not decisions:
        return
    console.print()
    console.print(Rule("[dim]Architectural Decisions[/dim]", style="dim"))
    for d in decisions:
        title = d.get("title") or "Untitled"
        body = d.get("decision", "")
        console.print(f"  [bold yellow]▶[/bold yellow] [bold]{title}[/bold]")
        if body:
            console.print(f"    [dim]{body[:200]}[/dim]")


def _render_experts(experts: list[dict]) -> None:
    if not experts:
        return
    names = ", ".join(e.get("name", "") for e in experts if e.get("name"))
    if names:
        console.print()
        console.print(f"[dim]File owners:[/dim] [green]{names}[/green]")


# ── Offline fallback ──────────────────────────────────────────────────────


def _ask_offline(question: str, project_path: str, project_id: str, top_k: int) -> None:
    print_info("Running in [yellow]offline[/yellow] mode — retrieving chunks (no LLM answer).")
    try:
        from src.embedding_generator import EmbeddingGenerator  # type: ignore
        from src.vector_store import VectorStore  # type: ignore
        from src.query_engine import QueryEngine  # type: ignore
    except ImportError as exc:
        print_error(f"Offline mode requires legacy src modules: {exc}")
        raise typer.Exit(1)

    chroma_path = str(Path(project_path) / "chroma_data")
    try:
        embed_gen = EmbeddingGenerator()
        vector_store = VectorStore(persist_directory=chroma_path)
        qe = QueryEngine(
            embedding_generator=embed_gen,
            vector_store=vector_store,
            collection_name="codeguardian",
        )
        q_emb = embed_gen.generate_embedding(question)
        chunks = qe.retrieve_chunks(q_emb, n_results=top_k)
        chunks = qe.rerank_results(chunks, question)

        if not chunks:
            print_warning("No relevant chunks found. Have you run [cyan]cgctl index[/cyan]?")
            return

        print_success(f"Found {len(chunks)} relevant chunk(s).")
        for i, chunk in enumerate(chunks, 1):
            console.print(f"\n[bold cyan]── Chunk {i}: {chunk.file_path}:{chunk.start_line}–{chunk.end_line}[/bold cyan]")
            from rich.syntax import Syntax
            lang = getattr(chunk, "language", "python") or "python"
            console.print(Syntax(chunk.content, lang, theme="monokai", line_numbers=True, start_line=chunk.start_line))

    except Exception as exc:
        print_error(f"Offline query failed: {exc}")
        raise typer.Exit(1)
