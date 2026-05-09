"""
CodeGuardian CLI - Main entry point.

Provides the cgctl command-line interface.
"""

import typer
from typing import Optional

from cgctl import __version__
from cgctl.commands import init, config, index, ask, serve, audit, context, impact, review, onboard, health, hooks
from cgctl.state import get_state

# Create the main CLI app
app = typer.Typer(
    name="cgctl",
    help="🛡️ CodeGuardian - AI-powered institutional memory for codebases",
    add_completion=True,
    rich_markup_mode="rich",
)

# Register command modules
app.add_typer(init.app, name="init")
app.add_typer(config.app, name="config")
app.add_typer(index.app, name="index")
app.add_typer(ask.app, name="ask")
app.add_typer(serve.app, name="serve")
app.add_typer(audit.app, name="audit")
app.add_typer(context.app, name="context")
app.add_typer(impact.app, name="impact")
app.add_typer(review.app, name="review")
app.add_typer(onboard.app, name="onboard")
app.add_typer(health.app, name="health")
app.add_typer(hooks.app, name="hooks")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version"),
    offline: bool = typer.Option(False, "--offline", help="Run in offline mode (direct Python imports)"),
    api_url: str = typer.Option("http://localhost:8742", "--api-url", help="API server URL"),
):
    """
    🛡️ CodeGuardian - AI-powered institutional memory for codebases.
    
    Use cgctl to index your codebase, retrieve context about your code,
    and run an MCP server for integration with AI assistants like
    GitHub Copilot.
    
    Global Options:
        --offline          Run in offline mode (direct Python imports)
        --api-url          API server URL (default: http://localhost:8742)
    
    Commands:
        init    - Initialize a new project
        index   - Index your codebase into the vector store
        ask     - Ask questions about the codebase
        context - Get context for a specific file
        impact  - Show blast radius for a changed file
        review  - Run code review on a file or diff
        onboard - Generate a learning path for a task
        health  - Show server health status
        serve   - Start the FastAPI server
        config  - Manage project configuration
        audit   - Run code audits
    """
    if version:
        typer.echo(f"CodeGuardian CLI v{__version__}")
        raise typer.Exit()
    
    # Set global state
    state = get_state()
    state.offline = offline
    state.api_url = api_url
    
    # If no command provided, show help
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


if __name__ == "__main__":
    app()
