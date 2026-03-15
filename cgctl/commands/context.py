"""
cgctl context — Get full context for a file from the knowledge graph.

Calls POST /api/ask with a structured file-context question and renders
the answer (purpose, owners, decisions, dependents) in a rich layout.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from rich.columns import Columns
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich import box

from cgctl.utils.output import console, print_error, print_info, print_warning

app = typer.Typer(help="Get context for a file from the knowledge graph")


def _read_project_id(project_path: str) -> str:
    cg = Path(project_path) / ".codeguardian" / "config.toml"
    if cg.exists():
        for line in cg.read_text().splitlines():
            if line.strip().startswith("project_id"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.path.basename(project_path)


@app.callback(invoke_without_command=True)
def get_context(
    ctx: typer.Context,
    file_path: str = typer.Argument(..., help="File path (relative to project root)"),
    path: str = typer.Option(".", "--path", "-p", help="Project root directory"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Override project ID"),
):
    """
    Show full context for a file: purpose, architecture, owners,
    architectural decisions, and what depends on it.

    Requires the server to be running and the project to be indexed.

    Examples:
        cgctl context server/routes/query.py
        cgctl context --path /my/project src/auth.ts
    """
    from cgctl.client import is_offline, make_client

    if is_offline():
        print_info(
            "[yellow]context[/yellow] command requires the server. "
            "Remove [bold]--offline[/bold] and run [cyan]cgctl serve[/cyan] first."
        )
        raise typer.Exit(1)

    project_path = os.path.abspath(os.path.expanduser(path))
    pid = project_id or _read_project_id(project_path)

    question = (
        f"Explain the purpose, architecture, and key functions of `{file_path}`. "
        "Who are the primary owners? What architectural decisions affect this file? "
        "What other files depend on it?"
    )

    client = make_client()
    try:
        with console.status(f"[bold green]Fetching context for [cyan]{file_path}[/cyan]…[/bold green]"):
            data = client.post(
                "/api/ask",
                {"project_id": pid, "question": question, "conversation_history": []},
            )
    except ConnectionError as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        print_error(f"Context fetch failed: {exc}")
        raise typer.Exit(1)

    # ── Header ───────────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel(
            f"[bold cyan]{file_path}[/bold cyan]",
            title="[bold]File Context[/bold]",
            border_style="cyan",
        )
    )

    # ── Answer ───────────────────────────────────────────────────────────
    answer = data.get("answer", "").strip()
    if answer:
        console.print()
        from rich.markdown import Markdown
        console.print(Markdown(answer))

    # ── Owners ───────────────────────────────────────────────────────────
    experts = data.get("experts", [])
    if experts:
        console.print()
        console.print(Rule("[dim]Owners[/dim]", style="dim"))
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
        table.add_column("Name", style="green")
        table.add_column("Email", style="dim")
        table.add_column("Expertise", justify="right")
        for e in experts:
            table.add_row(
                e.get("name", ""),
                e.get("email", "—"),
                f"{e.get('expertise_score', 0.0):.1f}",
            )
        console.print(table)

    # ── Architectural decisions ───────────────────────────────────────────
    decisions = data.get("decisions_referenced", [])
    if decisions:
        console.print()
        console.print(Rule("[dim]Architectural Decisions[/dim]", style="dim"))
        for d in decisions:
            title = d.get("title") or "Untitled"
            body = d.get("decision", "")
            ref = d.get("source_ref", "")
            console.print(f"  [bold yellow]▶[/bold yellow] [bold]{title}[/bold]")
            if body:
                console.print(f"    [dim]{body[:300]}[/dim]")
            if ref:
                console.print(f"    [dim italic]Source: {ref}[/dim italic]")

    # ── Sources in this file ──────────────────────────────────────────────
    file_sources = [
        s for s in data.get("sources", [])
        if s.get("file_path", "") == file_path
    ]
    if file_sources:
        console.print()
        console.print(Rule("[dim]Retrieved chunks[/dim]", style="dim"))
        for s in file_sources[:5]:
            start = s.get("start_line")
            end = s.get("end_line")
            ctype = s.get("chunk_type", "")
            loc = file_path + (f":{start}–{end}" if start else "")
            tag = f" [dim]({ctype})[/dim]" if ctype else ""
            console.print(f"  [cyan]{loc}[/cyan]{tag}")

    console.print()
