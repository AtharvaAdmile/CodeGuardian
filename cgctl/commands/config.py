"""
cgctl config - Manage CodeGuardian configuration.

View and modify configuration settings.
"""

import typer
import os
from pathlib import Path

from cgctl.utils.output import (
    console, print_success, print_error, print_info,
    print_warning, print_header, print_stats
)
from src.config.settings import get_settings

app = typer.Typer(help="Manage CodeGuardian configuration")


@app.callback(invoke_without_command=True)
def config_main(ctx: typer.Context):
    """
    Manage CodeGuardian configuration.
    
    Use subcommands to view or modify settings.
    """
    if ctx.invoked_subcommand is None:
        # Show current config
        show_config()


@app.command("show")
def show_config():
    """Show current configuration."""
    print_header("CodeGuardian Configuration")
    
    try:
        settings = get_settings()
        
        # API Keys (masked)
        console.print("\n[bold]API Keys:[/bold]")
        google_key = settings.google_api_key
        if google_key:
            masked = google_key[:8] + "..." + google_key[-4:] if len(google_key) > 12 else "***"
            console.print(f"  GOOGLE_API_KEY: [green]{masked}[/green]")
        else:
            console.print("  GOOGLE_API_KEY: [red]Not set[/red]")
        
        # Database
        console.print("\n[bold]Database:[/bold]")
        if settings.database.url:
            console.print(f"  SUPABASE_URL: [green]{settings.database.url}[/green]")
        else:
            console.print("  SUPABASE_URL: [red]Not set[/red]")
        
        if settings.database.key:
            masked = settings.database.key[:8] + "..."
            console.print(f"  SUPABASE_KEY: [green]{masked}[/green]")
        else:
            console.print("  SUPABASE_KEY: [red]Not set[/red]")
        
        # LLM Settings
        console.print("\n[bold]LLM Settings:[/bold]")
        console.print(f"  Provider: {settings.llm.provider}")
        console.print(f"  Model: {settings.llm.model}")
        console.print(f"  Temperature: {settings.llm.temperature}")
        console.print(f"  Max Tokens: {settings.llm.max_tokens}")
        console.print(f"  Stream: {settings.llm.stream}")
        
        # Embedding Settings
        console.print("\n[bold]Embedding Settings:[/bold]")
        console.print(f"  Model: {settings.embedding.model}")
        console.print(f"  Dimension: {settings.embedding.dimension}")
        console.print(f"  Batch Size: {settings.embedding.batch_size}")
        
        # Indexing Settings
        console.print("\n[bold]Indexing Settings:[/bold]")
        console.print(f"  Exclude Dirs: {', '.join(settings.indexing.exclude_dirs[:5])}...")
        console.print(f"  Extensions: {', '.join(settings.indexing.supported_extensions)}")
        
        # Retrieval Settings
        console.print("\n[bold]Retrieval Settings:[/bold]")
        console.print(f"  Initial Count: {settings.retrieval.initial_count}")
        console.print(f"  Final Count: {settings.retrieval.final_count}")
        console.print(f"  Similarity Threshold: {settings.retrieval.similarity_threshold}")
        
    except Exception as e:
        print_error(f"Failed to load configuration: {e}")
        raise typer.Exit(1)


@app.command("path")
def show_config_paths():
    """Show configuration file paths."""
    print_header("Configuration File Paths")
    
    paths = [
        ("Current directory .env", Path.cwd() / ".env"),
        ("Current directory config.toml", Path.cwd() / "config.toml"),
        ("Home directory config", Path.home() / ".codeguardian" / "config.toml"),
    ]
    
    for name, path in paths:
        exists = "✓" if path.exists() else "✗"
        color = "green" if path.exists() else "red"
        console.print(f"  [{color}]{exists}[/{color}] {name}: {path}")


@app.command("check")
def check_config():
    """Check configuration for issues."""
    print_header("Configuration Check")
    
    try:
        settings = get_settings()
        issues = []
        warnings = []
        
        # Required settings
        if not settings.google_api_key:
            issues.append("GOOGLE_API_KEY is not set")
        
        if not settings.database.url:
            issues.append("SUPABASE_URL is not set")
        
        if not settings.database.key:
            issues.append("SUPABASE_KEY is not set")
        
        # Warnings
        if settings.llm.temperature > 0.9:
            warnings.append("High LLM temperature may produce inconsistent results")
        
        if settings.retrieval.similarity_threshold < 0.5:
            warnings.append("Low similarity threshold may return irrelevant results")
        
        # Report
        if issues:
            console.print("\n[bold red]Issues:[/bold red]")
            for issue in issues:
                console.print(f"  [red]✗[/red] {issue}")
        
        if warnings:
            console.print("\n[bold yellow]Warnings:[/bold yellow]")
            for warning in warnings:
                console.print(f"  [yellow]⚠[/yellow] {warning}")
        
        if not issues and not warnings:
            print_success("All configuration checks passed!")
        elif not issues:
            print_info("Configuration is valid with warnings")
        else:
            print_error("Configuration has issues that need to be resolved")
            raise typer.Exit(1)
            
    except Exception as e:
        print_error(f"Configuration check failed: {e}")
        raise typer.Exit(1)
