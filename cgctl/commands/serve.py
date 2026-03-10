"""
CodeGuardian CLI - Serve command.

Starts the MCP server for integration with VS Code and GitHub Copilot.
"""

import typer
import sys
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(help="Start the CodeGuardian MCP server")
console = Console(stderr=True)  # Use stderr for console output


@app.callback(invoke_without_command=True)
def serve(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
):
    """
    🚀 Start the CodeGuardian MCP server.
    
    The server uses Stdio transport for VS Code integration.
    It exposes code analysis tools to AI assistants like GitHub Copilot.
    
    Tools available:
    - query_codebase: Semantic search over indexed codebase
    - analyze_structure: Project structure and complexity analysis
    - find_dependencies: Import and call-graph analysis
    - analyze_testability: Identify testable code elements
    - run_tests: Execute pytest and return results
    - detect_documentation_gaps: Find undocumented code
    
    Usage with VS Code:
    Add to your MCP settings:
    {
        "codeguardian": {
            "command": "cgctl",
            "args": ["serve"]
        }
    }
    """
    import logging
    
    # Configure logging based on verbosity
    log_level = logging.DEBUG if verbose else logging.WARNING
    
    # Log to stderr so it doesn't interfere with stdio transport
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr
    )
    
    # Show startup message on stderr (not stdout - that's for MCP)
    if verbose:
        console.print(
            Panel.fit(
                "[bold green]CodeGuardian MCP Server[/bold green]\n"
                "Starting in Stdio mode...\n\n"
                "[dim]Tools: query_codebase, analyze_structure, find_dependencies,[/dim]\n"
                "[dim]       analyze_testability, run_tests, detect_documentation_gaps[/dim]",
                title="🛡️ CodeGuardian",
                border_style="green"
            )
        )
    
    # Import and run the MCP server
    try:
        from src.mcp_server import run_server
        run_server()
    except ImportError as e:
        console.print(f"[red]Error importing MCP server: {e}[/red]")
        console.print("[dim]Make sure all dependencies are installed: pip install -r requirements.txt[/dim]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Error starting MCP server: {e}[/red]")
        raise typer.Exit(code=1)
