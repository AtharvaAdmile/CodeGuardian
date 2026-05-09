"""
cgctl review — review git history and current uncommitted changes.
"""

from __future__ import annotations

import os
from typing import Optional

import typer
from rich import box
from rich.panel import Panel
from rich.table import Table

from cgctl.utils.output import console, print_error, print_info, print_success

app = typer.Typer(help="Review git changes and optionally create a commit")


def _render_status(data: dict) -> None:
    recommendation = data.get("recommendation", {})
    should_commit = recommendation.get("should_commit", False)
    border = "green" if should_commit else "yellow"
    title = recommendation.get("title") or "Commit Review"
    reason = recommendation.get("reason") or ""

    console.print()
    console.print(
        Panel(
            f"[bold]{title}[/bold]\n{reason}\n\n{data.get('summary', '')}",
            title="[bold]Commit Review[/bold]",
            border_style=border,
        )
    )

    concerns = recommendation.get("concerns", [])
    for concern in concerns:
        console.print(f"[yellow]![/] {concern}")

    files = data.get("uncommitted_files", [])
    if files:
        table = Table(title="Uncommitted files", box=box.SIMPLE_HEAVY)
        table.add_column("File", style="cyan", overflow="fold")
        table.add_column("Scope")
        table.add_column("Status")
        table.add_column("+", justify="right", style="green")
        table.add_column("-", justify="right", style="red")
        for item in files:
            scope = "untracked" if item.get("untracked") else "staged" if item.get("staged") else "unstaged"
            if item.get("staged") and item.get("unstaged"):
                scope = "staged + unstaged"
            table.add_row(
                item.get("file_path", ""),
                scope,
                item.get("status", ""),
                str(item.get("additions", 0)),
                str(item.get("deletions", 0)),
            )
        console.print(table)
    else:
        print_success("Working tree clean.")

    history = data.get("recent_commits", [])
    if history:
        table = Table(title="Recent commits", box=box.SIMPLE_HEAVY)
        table.add_column("SHA", style="cyan")
        table.add_column("Message", overflow="fold")
        table.add_column("Author")
        table.add_column("Files", justify="right")
        table.add_column("+/-", justify="right")
        for item in history[:10]:
            table.add_row(
                item.get("short_sha", ""),
                item.get("message", ""),
                item.get("author", ""),
                str(len(item.get("files", []))),
                f"+{item.get('insertions', 0)}/-{item.get('deletions', 0)}",
            )
        console.print(table)


@app.callback(invoke_without_command=True)
def review(
    path: str = typer.Option(".", "--path", "-p", help="Project root directory"),
    history_limit: int = typer.Option(10, "--history-limit", min=1, max=50, help="Recent commits to show"),
    commit: bool = typer.Option(False, "--commit", help="Stage and commit all current changes"),
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Commit message"),
):
    """
    Review recent git history and current uncommitted changes.

    Use [bold]--commit -m "message"[/bold] to stage and commit the reviewed
    working tree.
    """
    from cgctl.client import is_offline, make_client

    if is_offline():
        print_info(
            "[yellow]review[/yellow] requires the server. "
            "Remove [bold]--offline[/bold] and run [cyan]cgctl serve[/cyan] first."
        )
        raise typer.Exit(1)

    project_path = os.path.abspath(os.path.expanduser(path))
    payload = {"project_path": project_path, "history_limit": history_limit}
    client = make_client()

    try:
        with console.status("[bold green]Loading commit review...[/bold green]"):
            data = client.post("/api/review/status", payload)
    except ConnectionError as exc:
        console.print(f"[red]x[/red] {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        print_error(f"Commit review failed: {exc}")
        raise typer.Exit(1)

    _render_status(data)

    if not commit:
        return

    commit_message = (message or data.get("recommendation", {}).get("suggested_message") or "").strip()
    if not commit_message:
        print_error("Commit message required. Pass --message / -m.")
        raise typer.Exit(1)

    try:
        with console.status("[bold green]Staging and committing changes...[/bold green]"):
            result = client.post(
                "/api/review/commit",
                {
                    "project_path": project_path,
                    "message": commit_message,
                    "history_limit": history_limit,
                },
            )
    except Exception as exc:
        print_error(f"Commit failed: {exc}")
        raise typer.Exit(1)

    if result.get("error"):
        print_error(result["error"])
        raise typer.Exit(1)
    if result.get("committed"):
        print_success(f"Committed {result.get('commit_sha', '')[:7]}: {result.get('message', '')}")
    else:
        print_info("No changes were committed.")
