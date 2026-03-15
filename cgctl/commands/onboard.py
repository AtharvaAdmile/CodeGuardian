"""
cgctl onboard — Generate an ordered learning path for a task.

Calls POST /api/onboard/generate and renders a numbered step-by-step
plan with file actions, focus areas, decisions, and expert contacts.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich import box

from cgctl.utils.output import console, print_error, print_info, print_warning

app = typer.Typer(help="Generate a learning path for a new task")

_ACTION_STYLE = {
    "read":       ("[cyan]read[/cyan]",       "📖"),
    "understand": ("[blue]understand[/blue]", "🧠"),
    "review":     ("[yellow]review[/yellow]", "🔍"),
}


def _read_project_id(project_path: str) -> str:
    cg = Path(project_path) / ".codeguardian" / "config.toml"
    if cg.exists():
        for line in cg.read_text().splitlines():
            if line.strip().startswith("project_id"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.path.basename(project_path)


@app.callback(invoke_without_command=True)
def onboard(
    ctx: typer.Context,
    task_description: str = typer.Argument(..., help="Plain-text description of the task to implement"),
    path: str = typer.Option(".", "--path", "-p", help="Project root directory"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Override project ID"),
    compact: bool = typer.Option(False, "--compact", help="Table view instead of expanded panels"),
):
    """
    Generate an ordered learning path for a new developer picking up a task.

    The learning path is built from the knowledge graph's file context,
    architectural decisions, and expert data, then sorted from foundational
    to task-specific.

    Requires the server to be running and the project to be indexed.

    Examples:
        cgctl onboard "implement rate limiting on the query API"
        cgctl onboard "add OAuth2 login" --path /my/project
    """
    from cgctl.client import is_offline, make_client

    if is_offline():
        print_info(
            "[yellow]onboard[/yellow] requires the server. "
            "Remove [bold]--offline[/bold] and run [cyan]cgctl serve[/cyan] first."
        )
        raise typer.Exit(1)

    if len(task_description.strip()) < 5:
        print_error("Task description is too short.")
        raise typer.Exit(1)

    project_path = os.path.abspath(os.path.expanduser(path))
    pid = project_id or _read_project_id(project_path)

    client = make_client()
    try:
        with console.status("[bold green]Building learning path…[/bold green]"):
            data = client.post(
                "/api/onboard/generate",
                {"project_id": pid, "task_description": task_description},
            )
    except ConnectionError as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        print_error(f"Onboarding generation failed: {exc}")
        raise typer.Exit(1)

    if data.get("error"):
        print_error(data["error"])
        raise typer.Exit(1)

    steps = data.get("learning_path", [])
    if not steps:
        print_warning("No learning path generated. Is the project indexed?")
        raise typer.Exit(0)

    # ── Header ───────────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel(
            f"[bold]{task_description}[/bold]\n[dim]{len(steps)} steps[/dim]",
            title="[bold cyan]Onboarding Path[/bold cyan]",
            border_style="cyan",
        )
    )
    console.print()

    if compact:
        _render_compact(steps)
    else:
        _render_steps(steps)


def _render_steps(steps: list[dict]) -> None:
    for step in steps:
        num = step.get("step_number", "?")
        action = step.get("action", "read")
        fp = step.get("file_path", "unknown")
        focus = step.get("focus_area", "")
        context = step.get("context", "")
        decisions = step.get("related_decisions") or []
        expert = step.get("expert_contact")

        action_label, icon = _ACTION_STYLE.get(action, (f"[dim]{action}[/dim]", "•"))

        console.print(
            f"  {icon}  [bold]Step {num}[/bold]  {action_label}  [cyan]{fp}[/cyan]"
        )
        if focus:
            console.print(f"     [bold dim]Focus:[/bold dim] {focus}")
        if context:
            console.print(f"     [dim]{context[:200]}[/dim]")
        if decisions:
            console.print(f"     [bold dim]Decisions:[/bold dim] [yellow]{', '.join(decisions[:3])}[/yellow]")
        if expert:
            console.print(f"     [bold dim]Expert:[/bold dim] [green]{expert}[/green]")
        console.print()


def _render_compact(steps: list[dict]) -> None:
    table = Table(
        show_header=True,
        header_style="bold dim",
        box=box.SIMPLE_HEAVY,
        expand=False,
    )
    table.add_column("#", width=3, justify="right")
    table.add_column("Action", width=12)
    table.add_column("File", style="cyan")
    table.add_column("Focus")
    table.add_column("Expert", style="green", width=16)

    for step in steps:
        num = str(step.get("step_number", "?"))
        action = step.get("action", "read")
        fp = step.get("file_path", "unknown")
        focus = (step.get("focus_area") or "")[:40]
        expert = step.get("expert_contact") or "—"
        _, icon = _ACTION_STYLE.get(action, ("", "•"))
        action_label = f"{icon} {action}"
        table.add_row(num, action_label, fp, focus, expert)

    console.print(table)
