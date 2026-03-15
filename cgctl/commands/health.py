"""
cgctl health — Show server and component health status.

Calls GET /api/health and renders a Rich status table with colour-coded
component indicators and uptime.
"""

from __future__ import annotations

import typer
from rich import box
from rich.panel import Panel
from rich.table import Table

from cgctl.utils.output import console, print_error, print_info

app = typer.Typer(help="Show server health status")

_STATUS_STYLE = {
    "ok":              ("[green]✓ ok[/green]",                "green"),
    "healthy":         ("[green]● healthy[/green]",           "green"),
    "degraded":        ("[yellow]◑ degraded[/yellow]",        "yellow"),
    "unhealthy":       ("[red]✗ unhealthy[/red]",             "red"),
    "error":           ("[red]✗ error[/red]",                 "red"),
    "not_initialized": ("[dim]○ not initialised[/dim]",       "dim"),
}


def _fmt_status(s: str) -> str:
    return _STATUS_STYLE.get(s, (f"[dim]{s}[/dim]", "dim"))[0]


def _fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    return f"{s // 3600}h {(s % 3600) // 60}m"


@app.callback(invoke_without_command=True)
def health(
    ctx: typer.Context,
    watch: bool = typer.Option(False, "--watch", "-w", help="Refresh every 5 seconds"),
):
    """
    Show the health of the CodeGuardian server and its components.

    If the server is not running, prints a helpful startup message.

    Examples:
        cgctl health
        cgctl health --watch
    """
    import time
    from cgctl.client import is_offline, make_client

    if is_offline():
        print_info(
            "[yellow]health[/yellow] checks the server — not available in offline mode."
        )
        raise typer.Exit(0)

    client = make_client()

    def _once() -> bool:
        """Fetch and render health. Returns True on success."""
        try:
            data = client.get("/api/health")
        except ConnectionError as exc:
            console.print(
                Panel(
                    f"[red]Server is not running.[/red]\n\n"
                    f"Start it with: [bold cyan]cgctl serve[/bold cyan]",
                    title="[red]CodeGuardian[/red]",
                    border_style="red",
                )
            )
            return False
        except Exception as exc:
            print_error(f"Health check failed: {exc}")
            return False

        overall = data.get("status", "unknown")
        uptime = _fmt_uptime(data.get("uptime_seconds", 0.0))
        components: dict = data.get("components", {})

        border = _STATUS_STYLE.get(overall, ("", "dim"))[1]

        table = Table(
            show_header=True,
            header_style="bold dim",
            box=box.SIMPLE_HEAVY,
        )
        table.add_column("Component", style="bold")
        table.add_column("Status")
        table.add_column("Detail", style="dim")

        for name, info in components.items():
            if isinstance(info, dict):
                s = info.get("status", "unknown")
                detail = info.get("detail") or ""
            else:
                s = str(info)
                detail = ""
            table.add_row(name.replace("_", " ").title(), _fmt_status(s), detail[:60])

        console.print()
        console.print(
            Panel(
                table,
                title=f"[bold]CodeGuardian Server[/bold]  {_fmt_status(overall)}",
                subtitle=f"[dim]uptime {uptime}[/dim]",
                border_style=border,
            )
        )
        console.print()
        return True

    if watch:
        try:
            while True:
                console.clear()
                _once()
                time.sleep(5)
        except KeyboardInterrupt:
            pass
    else:
        ok = _once()
        if not ok:
            raise typer.Exit(1)
