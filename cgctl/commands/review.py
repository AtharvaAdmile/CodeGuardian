"""
cgctl review — Run the LangGraph code-review pipeline on a file or diff.

POST /api/review → renders findings with severity colour labels,
a human-readable summary, and impact data.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich import box
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from cgctl.utils.output import console, print_error, print_info, print_success, print_warning

app = typer.Typer(help="Run code review on a file or diff")

# Severity → (foreground colour, badge text)
_SEV = {
    "critical": ("bold red",    "CRITICAL"),
    "high":     ("red",         "HIGH    "),
    "medium":   ("yellow",      "MEDIUM  "),
    "low":      ("dim",         "LOW     "),
}

_CAT_ICON = {
    "security":   "🔒",
    "pattern":    "📐",
    "complexity": "📊",
    "impact":     "💥",
}


def _read_project_id(project_path: str) -> str:
    cg = Path(project_path) / ".codeguardian" / "config.toml"
    if cg.exists():
        for line in cg.read_text().splitlines():
            if line.strip().startswith("project_id"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.path.basename(project_path)


@app.callback(invoke_without_command=True)
def review(
    ctx: typer.Context,
    file_path: str = typer.Argument(..., help="File to review"),
    path: str = typer.Option(".", "--path", "-p", help="Project root directory"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Override project ID"),
    diff: bool = typer.Option(False, "--diff", help="Read unified diff from stdin instead of file content"),
    pr: Optional[int] = typer.Option(None, "--pr", help="(Future) PR number — logs intent, not yet automated"),
    compact: bool = typer.Option(False, "--compact", help="Single-line finding format (good for CI)"),
):
    """
    Run a multi-stage code review on a file.

    Checks security vulnerabilities, code patterns, cyclomatic complexity,
    and blast-radius impact. Results are rendered with severity colours.

    Pass [bold]--diff[/bold] to review a unified diff from stdin:
        git diff HEAD~1 -- server/app.py | cgctl review server/app.py --diff

    Examples:
        cgctl review server/routes/query.py
        cgctl review src/auth.ts --path /my/project
        git diff HEAD~1 | cgctl review server/app.py --diff
    """
    from cgctl.client import is_offline, make_client

    if is_offline():
        print_info(
            "[yellow]review[/yellow] requires the server. "
            "Remove [bold]--offline[/bold] and run [cyan]cgctl serve[/cyan] first."
        )
        raise typer.Exit(1)

    if pr is not None:
        print_info(
            f"[dim]PR #{pr} noted — automated review posting is not yet implemented.[/dim]\n"
            "Reviewing local file content instead."
        )

    project_path = os.path.abspath(os.path.expanduser(path))
    pid = project_id or _read_project_id(project_path)

    # Build payload
    payload: dict = {"project_id": pid, "project_path": project_path}

    if diff:
        diff_content = sys.stdin.read()
        if not diff_content.strip():
            print_error("No diff received on stdin.")
            raise typer.Exit(1)
        payload["diff"] = diff_content
        payload["file_path"] = file_path
    else:
        abs_file = os.path.join(project_path, file_path) if not os.path.isabs(file_path) else file_path
        if not os.path.isfile(abs_file):
            print_error(f"File not found: {abs_file}")
            raise typer.Exit(1)
        try:
            payload["code"] = open(abs_file, encoding="utf-8", errors="ignore").read()
        except OSError as exc:
            print_error(f"Cannot read file: {exc}")
            raise typer.Exit(1)
        payload["file_path"] = file_path

    client = make_client()
    try:
        with console.status(f"[bold green]Reviewing [cyan]{file_path}[/cyan]…[/bold green]"):
            data = client.post("/api/review", payload)
    except ConnectionError as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        print_error(f"Review failed: {exc}")
        raise typer.Exit(1)

    if data.get("error"):
        print_error(data["error"])
        raise typer.Exit(1)

    findings = data.get("findings", [])
    summary = data.get("summary", "").strip()
    counts = data.get("severity_counts", {})
    impact = data.get("impact_report", {})

    # ── Header panel ─────────────────────────────────────────────────────
    total = len(findings)
    n_crit = counts.get("critical", 0)
    n_high = counts.get("high", 0)
    border = "red" if n_crit else "yellow" if n_high else "green"

    console.print()
    counts_str = "  ".join(
        f"[{_SEV.get(s, ('dim',''))[0]}]{n} {s}[/{_SEV.get(s, ('dim',''))[0]}]"
        for s, n in counts.items() if n
    ) or "[green]clean[/green]"
    console.print(
        Panel(
            f"[bold cyan]{file_path}[/bold cyan]\n{counts_str}",
            title="[bold]Code Review[/bold]",
            border_style=border,
        )
    )

    # ── Summary ───────────────────────────────────────────────────────────
    if summary:
        console.print()
        from rich.markdown import Markdown
        console.print(Markdown(summary))

    # ── Findings ──────────────────────────────────────────────────────────
    if not findings:
        console.print()
        print_success("No issues found.")
    elif compact:
        _render_compact(findings)
    else:
        _render_findings(findings)

    # ── Impact ────────────────────────────────────────────────────────────
    if impact and not impact.get("error") and impact.get("total_affected", 0):
        total_aff = impact["total_affected"]
        console.print()
        console.print(Rule("[dim]Impact[/dim]", style="dim"))
        console.print(f"  [bold]{total_aff}[/bold] downstream file(s) affected.")
        for f in impact.get("high_risk", [])[:3]:
            console.print(f"  [red]↳ {f['file_path']}[/red] [dim]risk={f['risk_score']:.2f}[/dim]")

    console.print()

    # Exit 1 if critical/high found (useful for CI)
    if n_crit or n_high:
        raise typer.Exit(1)


def _render_findings(findings: list[dict]) -> None:
    console.print()
    console.print(Rule("[dim]Findings[/dim]", style="dim"))
    for i, f in enumerate(findings, 1):
        sev = f.get("severity", "low")
        cat = f.get("category", "")
        msg = f.get("message", "")
        fp = f.get("file_path", "")
        line = f.get("line")
        suggestion = f.get("suggestion", "")
        conf = f.get("confidence", 0.0)

        colour, badge = _SEV.get(sev, ("dim", sev.upper()))
        icon = _CAT_ICON.get(cat, "•")
        loc = f" [dim]{fp}:{line}[/dim]" if fp and line else (f" [dim]{fp}[/dim]" if fp else "")

        console.print(f"\n  [{colour}][{badge}][/{colour}] {icon}  {msg}{loc}")
        if suggestion:
            console.print(f"  [dim]    → {suggestion}[/dim]")
        console.print(f"  [dim]    confidence: {conf:.0%}[/dim]")


def _render_compact(findings: list[dict]) -> None:
    """One-line-per-finding format for CI output."""
    console.print()
    for f in findings:
        sev = f.get("severity", "low")
        cat = f.get("category", "")
        msg = f.get("message", "")
        fp = f.get("file_path", "")
        line = f.get("line", "")
        colour, badge = _SEV.get(sev, ("dim", sev.upper()))
        loc = f"{fp}:{line}" if fp and line else fp
        console.print(f"[{colour}]{badge.strip()}[/{colour}]\t{loc}\t{msg}")
