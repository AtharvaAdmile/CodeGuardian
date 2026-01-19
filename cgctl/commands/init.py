"""
cgctl init - Initialize a CodeGuardian project.

Sets up the project directory with configuration files and
connects to Supabase.
"""

import typer
import os
from pathlib import Path

from cgctl.utils.output import (
    console, print_success, print_error, print_info,
    print_warning, print_header, print_stats
)
from cgctl.utils.validators import validate_project_path, sanitize_project_name
from src.config.settings import get_settings

app = typer.Typer(help="Initialize a CodeGuardian project")


@app.callback(invoke_without_command=True)
def init_project(
    ctx: typer.Context,
    path: str = typer.Argument(
        ".",
        help="Path to the project directory"
    ),
    name: str = typer.Option(
        None,
        "--name", "-n",
        help="Project name (defaults to directory name)"
    ),
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Overwrite existing configuration"
    ),
):
    """
    Initialize a new CodeGuardian project.
    
    This command sets up the necessary configuration files and
    creates a project record in Supabase.
    
    Example:
        cgctl init
        cgctl init /path/to/project --name my-project
    """
    print_header("CodeGuardian Project Setup", "Initializing project configuration")
    
    # Resolve path
    project_path = os.path.abspath(os.path.expanduser(path))
    
    # Validate path
    is_valid, error = validate_project_path(project_path)
    if not is_valid:
        print_error(error)
        raise typer.Exit(1)
    
    # Determine project name
    if not name:
        name = os.path.basename(project_path)
    
    project_name = sanitize_project_name(name)
    print_info(f"Project path: [cyan]{project_path}[/cyan]")
    print_info(f"Project name: [cyan]{project_name}[/cyan]")
    
    # Check for existing configuration
    config_file = Path(project_path) / ".codeguardian"
    if config_file.exists() and not force:
        print_warning("Project already initialized. Use --force to reinitialize.")
        raise typer.Exit(0)
    
    # Check environment
    try:
        settings = get_settings(project_path)
    except Exception as e:
        print_error(f"Failed to load settings: {e}")
        raise typer.Exit(1)
    
    # Validate required configuration
    issues = []
    
    if not settings.google_api_key:
        issues.append("GOOGLE_API_KEY not set in .env")
    
    if not settings.database.url:
        issues.append("SUPABASE_URL not set in .env")
    
    if not settings.database.key:
        issues.append("SUPABASE_KEY not set in .env")
    
    if issues:
        print_error("Missing configuration:")
        for issue in issues:
            console.print(f"  [red]•[/red] {issue}")
        print_info("\nCreate a .env file with the required variables.")
        raise typer.Exit(1)
    
    # Test Supabase connection
    print_info("Testing Supabase connection...")
    
    try:
        from src.db.supabase_client import get_supabase_client
        from src.db.queries import create_project, get_project_by_path
        
        client = get_supabase_client()
        
        # Check if project already exists
        existing = get_project_by_path(project_path)
        
        if existing:
            print_info(f"Found existing project: {existing['id']}")
            project_id = existing['id']
        else:
            # Create new project
            project = create_project(
                name=project_name,
                root_path=project_path,
            )
            project_id = project['id']
            print_success(f"Created project in Supabase: {project_id}")
        
        # Write local config
        config_content = f"""# CodeGuardian Project Configuration
project_id = "{project_id}"
project_name = "{project_name}"
"""
        config_file.write_text(config_content)
        print_success(f"Created .codeguardian config file")
        
        # Summary
        print_header("Setup Complete!")
        print_stats({
            "Project ID": project_id,
            "Project Name": project_name,
            "Path": project_path,
        })
        
        print_info("\nNext steps:")
        console.print("  1. Run [cyan]cgctl index[/cyan] to index your codebase")
        console.print("  2. Run [cyan]cgctl ask[/cyan] to start querying")
        
    except Exception as e:
        print_error(f"Failed to connect to Supabase: {e}")
        print_info("Please check your SUPABASE_URL and SUPABASE_KEY in .env")
        raise typer.Exit(1)
