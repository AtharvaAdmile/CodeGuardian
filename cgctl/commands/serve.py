"""
cgctl serve — Start the CodeGuardian FastAPI server in the foreground.

Launches uvicorn on 0.0.0.0:8742 with the server.app:app factory.
In MCP-stdio mode (--mcp) it delegates to the MCP server instead.
"""

from __future__ import annotations

import sys

import typer
from rich.panel import Panel

app = typer.Typer(help="Start the CodeGuardian server")

_WELCOME = """[bold cyan]CodeGuardian[/bold cyan] API server

  • REST API:  [link]http://localhost:{port}[/link]
  • Docs:      [link]http://localhost:{port}/docs[/link]
  • Health:    [link]http://localhost:{port}/api/health[/link]

Press [bold]Ctrl-C[/bold] to stop."""


@app.callback(invoke_without_command=True)
def serve(
    ctx: typer.Context,
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8742, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (dev mode)"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of uvicorn workers"),
    log_level: str = typer.Option("info", "--log-level", help="Uvicorn log level"),
    mcp: bool = typer.Option(False, "--mcp", help="Start the MCP server (stdio) instead of the REST API"),
    mcp_sse: bool = typer.Option(False, "--mcp-sse", help="Start the MCP server in SSE mode"),
    mcp_port: int = typer.Option(8743, "--mcp-port", help="Port for MCP SSE mode"),
):
    """
    Start the CodeGuardian FastAPI server in the foreground.

    This is the main backend that all CLI commands talk to.
    Keep it running in a terminal while you use [cyan]cgctl[/cyan].

    Pass [bold]--mcp[/bold] to start the MCP stdio server for Claude Code /
    AI assistant integration instead.

    Examples:
        cgctl serve
        cgctl serve --port 9000 --reload
        cgctl serve --mcp
        cgctl serve --mcp-sse --mcp-port 8743
    """
    from cgctl.utils.output import console

    if mcp or mcp_sse:
        _start_mcp(mcp_sse, host, mcp_port, log_level)
        return

    console.print()
    console.print(
        Panel(
            _WELCOME.format(port=port),
            title="🛡️  [bold]Starting server[/bold]",
            border_style="cyan",
        )
    )
    console.print()

    try:
        import uvicorn
    except ImportError:
        console.print("[red]✗[/red] uvicorn is not installed. Run [cyan]pip install uvicorn[/cyan].")
        raise typer.Exit(1)

    try:
        uvicorn.run(
            "server.app:app",
            host=host,
            port=port,
            reload=reload,
            workers=workers if not reload else 1,
            log_level=log_level,
        )
    except KeyboardInterrupt:
        console.print("\n[dim]Server stopped.[/dim]")
    except Exception as exc:
        console.print(f"[red]✗[/red] Server error: {exc}")
        raise typer.Exit(1)


def _start_mcp(sse: bool, host: str, port: int, log_level: str) -> None:
    from cgctl.utils.output import console

    import logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        from server.mcp_server import main as mcp_main
    except ImportError as exc:
        console.print(f"[red]✗[/red] Cannot import MCP server: {exc}")
        raise typer.Exit(1)

    # Patch sys.argv so argparse inside mcp_server.main() sees the right flags
    argv = ["mcp_server"]
    if sse:
        argv += ["--sse", "--host", host, "--port", str(port)]
    sys.argv = argv

    console.print(
        Panel(
            f"MCP server starting in [bold]{'SSE' if sse else 'stdio'}[/bold] mode"
            + (f" on {host}:{port}" if sse else ""),
            title="🛡️  [bold]CodeGuardian MCP[/bold]",
            border_style="green",
        ),
        file=sys.stderr,
    )

    try:
        mcp_main()
    except KeyboardInterrupt:
        pass
