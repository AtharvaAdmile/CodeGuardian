"""
CodeGuardian CLI - Main entry point.

Provides the cgctl command-line interface.
"""

import typer
from typing import Optional

from cgctl import __version__
from cgctl.commands import init, config, index, ask, serve, audit

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


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version"),
):
    """
    🛡️ CodeGuardian - AI-powered institutional memory for codebases.
    
    Use cgctl to index your codebase, retrieve context about your code,
    and run an MCP server for integration with AI assistants like
    GitHub Copilot.
    
    Commands:
        init    - Initialize a new project
        index   - Index your codebase into the vector store
        ask     - Retrieve relevant code context
        serve   - Start the MCP server for VS Code integration
        config  - Manage project configuration
        audit   - Run code audits (experts, health, compliance)
    """
    if version:
        typer.echo(f"CodeGuardian CLI v{__version__}")
        raise typer.Exit()
    
    # If no command provided, show help
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


if __name__ == "__main__":
    app()
