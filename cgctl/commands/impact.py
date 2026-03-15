"""
cgctl impact — Show blast radius for a changed file.

Calls POST /api/impact/analyze and renders a Rich tree of affected files
grouped by risk level, with a suggested-reviewer list at the bottom.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from rich import box
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.tree import Tree

from cgctl.utils.output import console, print_error, print_info, print_stats

app = typer.Typer(help="Show blast radius for a changed file")

_RISK_STYLE = {
    "high":   ("red",    "🔴"),
    "medium": ("yellow", "🟡"),
    "low":    ("dim",    "⚪"),
}


def _read_project_path_from_config(project_path: str) -> str:
    return project_path


def _read_project_id(project_path: str) -> str:
    cg = Path(project_path) / ".codeguardian" / "config.toml"
    if cg.exists():
        for line in cg.read_text().splitlines():
            if line.strip().startswith("project_id"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.path.basename(project_path)


@app.callback(invoke_without_command=True)
def impact(
    ctx: typer.Context,
    file_path: str = typer.Argument(..., help="File that was changed (relative to project root)"),
    path: str = typer.Option(".", "--path", "-p", help="Project root directory"),
    diff: Optional[str] = typer.Option(None, "--diff", help="Unified diff of the change (enables breaking-change detection)"),
    tree: bool = typer.Option(True, "--tree/--no-tree", help="Show affected files as a tree"),
):
    """
    Calculate the blast radius of changing a file.

    Shows which files are transitively affected, their risk scores,
    and who should review the change.

    Requires the server to be running and the project to be indexed.

    Examples:
        cgctl impact server/routes/query.py
        cgctl impact src/auth.ts --path /my/project
        git diff HEAD~1 | cgctl impact server/app.py --diff -
    """
    from cgctl.client import is_offline, make_client

    if is_offline():
        print_info(
            "[yellow]impact[/yellow] requires the server. "
            "Remove [bold]--offline[/bold] and run [cyan]cgctl serve[/cyan] first."
        )
        raise typer.Exit(1)

    project_path = os.path.abspath(os.path.expanduser(path))

    # Handle --diff - (read from stdin)
    diff_content: Optional[str] = None
    if diff == "-":
        import sys
        diff_content = sys.stdin.read()
    elif diff:
        diff_content = diff

    payload: dict = {"project_path": project_path, "file_path": file_path}
    if diff_content:
        payload["diff"] = diff_content

    client = make_client()
    try:
        with console.status(f"[bold green]Analysing impact of [cyan]{file_path}[/cyan]…[/bold green]"):
            data = client.post("/api/impact/analyze", payload)
    except ConnectionError as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        print_error(f"Impact analysis failed: {exc}")
        raise typer.Exit(1)

    if data.get("error"):
        print_error(data["error"])
        raise typer.Exit(1)

    changed = data.get("changed_file", file_path)
    total = data.get("total_affected", 0)
    high_risk = data.get("high_risk", [])
    medium_risk = data.get("medium_risk", [])
    low_risk = data.get("low_risk", [])
    modules = data.get("affected_modules", [])
    reviewers = data.get("suggested_reviewers", [])

    # ── Header ───────────────────────────────────────────────────────────
    console.print()
    colour = "red" if high_risk else "yellow" if medium_risk else "green"
    console.print(
        Panel(
            f"[bold cyan]{changed}[/bold cyan]\n"
            f"[{colour}]{total} file(s) affected[/{colour}]",
            title="[bold]Blast Radius[/bold]",
            border_style=colour,
        )
    )
    console.print()

    if total == 0:
        print_info("No downstream files affected. Safe to merge.")
        return

    if tree:
        _render_tree(changed, high_risk, medium_risk, low_risk)
    else:
        _render_table(high_risk, medium_risk, low_risk)

    # ── Affected modules ──────────────────────────────────────────────────
    if modules:
        console.print()
        console.print(Rule("[dim]Affected Modules[/dim]", style="dim"))
        console.print("  " + "  ".join(f"[cyan]{m}[/cyan]" for m in modules))

    # ── Suggested reviewers ───────────────────────────────────────────────
    if reviewers:
        console.print()
        console.print(Rule("[dim]Suggested Reviewers[/dim]", style="dim"))
        for r in reviewers:
            console.print(f"  [green]@{r}[/green]")

    console.print()


def _render_tree(
    root: str,
    high: list[dict],
    medium: list[dict],
    low: list[dict],
) -> None:
    t = Tree(f"[bold cyan]{root}[/bold cyan] [dim](changed)[/dim]")

    def _add_bucket(parent, label: str, files: list[dict], colour: str, emoji: str) -> None:
        if not files:
            return
        branch = parent.add(f"[{colour}]{emoji} {label} ({len(files)})[/{colour}]")
        for f in files:
            fp = f.get("file_path", "")
            score = f.get("risk_score", 0.0)
            reason = f.get("reason", "")
            line = f"[{colour}]{fp}[/{colour}] [dim]risk={score:.2f}[/dim]"
            if reason:
                line += f" — [dim]{reason[:60]}[/dim]"
            branch.add(line)

    _add_bucket(t, "High Risk",   high,   "red",    "🔴")
    _add_bucket(t, "Medium Risk", medium, "yellow", "🟡")
    _add_bucket(t, "Low Risk",    low,    "dim",    "⚪")

    console.print(t)


def _render_table(
    high: list[dict],
    medium: list[dict],
    low: list[dict],
) -> None:
    table = Table(
        show_header=True,
        header_style="bold dim",
        box=box.SIMPLE_HEAVY,
    )
    table.add_column("Risk", width=8)
    table.add_column("File", style="cyan")
    table.add_column("Score", justify="right", width=6)
    table.add_column("Reason", style="dim")

    for f in high:
        table.add_row("[red]HIGH[/red]", f.get("file_path", ""), f"{f.get('risk_score', 0):.2f}", f.get("reason", "")[:60])
    for f in medium:
        table.add_row("[yellow]MED[/yellow]", f.get("file_path", ""), f"{f.get('risk_score', 0):.2f}", f.get("reason", "")[:60])
    for f in low:
        table.add_row("[dim]LOW[/dim]", f.get("file_path", ""), f"{f.get('risk_score', 0):.2f}", f.get("reason", "")[:60])

    console.print(table)
