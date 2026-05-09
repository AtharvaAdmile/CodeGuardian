"""
cgctl hooks — Install git hooks for CodeGuardian context updates.

Generates pre-commit and post-commit hooks that automatically update
.context.yaml files when code changes are committed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from cgctl.utils.output import console, print_error, print_info, print_success

app = typer.Typer(help="Install and manage git hooks for context updates")
console = Console()

PRE_COMMIT_HOOK = '''#!/bin/bash
# CodeGuardian pre-commit hook
# Automatically updates .context.yaml files for changed directories

CODEGUARDIAN_PORT="${CODEGUARDIAN_PORT:-8742}"
REPO_ROOT="$(git rev-parse --show-toplevel)"

# Get staged files
STAGED_FILES=$(git diff --cached --name-only)

if [ -z "$STAGED_FILES" ]; then
    exit 0
fi

# Get unique directories from staged files
DIRECTORIES=$(echo "$STAGED_FILES" | xargs -I{} dirname {} | sort -u)

for dir in $DIRECTORIES; do
    # Skip .git directory
    if [ "$dir" = ".git" ]; then
        continue
    fi

    # Make sure directory exists
    if [ ! -d "$REPO_ROOT/$dir" ]; then
        continue
    fi

    # Skip directories without .context.yaml
    if [ ! -f "$REPO_ROOT/$dir/.context.yaml" ]; then
        continue
    fi

    # Update context for staged changes
    curl -s -X POST "http://localhost:$CODEGUARDIAN_PORT/api/context/update" \\
        -H "Content-Type: application/json" \\
        -d "{\\"repo_path\\": \\"$REPO_ROOT\\", \\"directory\\": \\"$dir\\", \\"change_type\\": \\"staged\\"}" > /dev/null 2>&1 || true
done

exit 0
'''

POST_COMMIT_HOOK = '''#!/bin/bash
# CodeGuardian post-commit hook
# Automatically updates .context.yaml files after commits

CODEGUARDIAN_PORT="${CODEGUARDIAN_PORT:-8742}"
REPO_ROOT="$(git rev-parse --show-toplevel)"

# Get files changed in the last commit
COMMIT_FILES=$(git diff-tree --no-commit-id -r --name-only HEAD)

if [ -z "$COMMIT_FILES" ]; then
    exit 0
fi

# Get unique directories
DIRECTORIES=$(echo "$COMMIT_FILES" | xargs -I{} dirname {} | sort -u)

for dir in $DIRECTORIES; do
    # Skip .git directory
    if [ "$dir" = ".git" ]; then
        continue
    fi

    # Make sure directory exists
    if [ ! -d "$REPO_ROOT/$dir" ]; then
        continue
    fi

    # Skip directories without .context.yaml
    if [ ! -f "$REPO_ROOT/$dir/.context.yaml" ]; then
        continue
    fi

    # Update context with committed changes
    curl -s -X POST "http://localhost:$CODEGUARDIAN_PORT/api/context/update" \\
        -H "Content-Type: application/json" \\
        -d "{\\"repo_path\\": \\"$REPO_ROOT\\", \\"directory\\": \\"$dir\\", \\"change_type\\": \\"committed\\"}" > /dev/null 2>&1 || true
done

exit 0
'''


@app.command()
def install(
    path: str = typer.Option(".", "--path", "-p", help="Repository path"),
    port: int = typer.Option(8742, "--port", help="CodeGuardian server port"),
):
    """
    Install git hooks for CodeGuardian context updates.

    This will create pre-commit and post-commit hooks that automatically
    update .context.yaml files when code changes are committed.

    Requires the CodeGuardian server to be running.

    Examples:
        cgctl hooks install
        cgctl hooks install --path /my/project
        cgctl hooks install --port 9000
    """
    repo_path = Path(path).resolve()
    hooks_dir = repo_path / ".git" / "hooks"

    if not repo_path.exists():
        print_error(f"Repository not found: {path}")
        raise typer.Exit(1)

    if not (repo_path / ".git").exists():
        print_error("Not a git repository. Run 'git init' first.")
        raise typer.Exit(1)

    hooks_dir.mkdir(parents=True, exist_ok=True)

    env_note = f"CODEGUARDIAN_PORT={port}"

    pre_commit_path = hooks_dir / "pre-commit"
    post_commit_path = hooks_dir / "post-commit"

    pre_commit_path.write_text(PRE_COMMIT_HOOK, encoding="utf-8")
    post_commit_path.write_text(POST_COMMIT_HOOK, encoding="utf-8")

    os.chmod(pre_commit_path, 0o755)
    os.chmod(post_commit_path, 0o755)

    print_success(f"Installed hooks to {hooks_dir}")
    console.print()
    console.print(Panel(
        "[dim]Environment variable to change server port:[/dim]\n"
        f"[cyan]{env_note}[/cyan]",
        title="[bold]Hook Installed[/bold]",
        border_style="green",
    ))
    console.print()
    console.print("[dim]Pre-commit hook:[/dim] Updates .context.yaml for staged changes")
    console.print("[dim]Post-commit hook:[/dim] Updates .context.yaml for committed changes")
    console.print()
    console.print(
        "[yellow]Note:[/yellow] Make sure CodeGuardian server is running on "
        f"[cyan]port {port}[/cyan] for hooks to work."
    )


@app.command()
def uninstall(
    path: str = typer.Option(".", "--path", "-p", help="Repository path"),
):
    """
    Remove CodeGuardian git hooks.

    Examples:
        cgctl hooks uninstall
        cgctl hooks uninstall --path /my/project
    """
    repo_path = Path(path).resolve()
    hooks_dir = repo_path / ".git" / "hooks"

    if not hooks_dir.exists():
        print_error("No hooks directory found.")
        raise typer.Exit(1)

    removed = []

    for hook_name in ["pre-commit", "post-commit"]:
        hook_path = hooks_dir / hook_name
        if hook_path.exists():
            content = hook_path.read_text(encoding="utf-8")
            if "CodeGuardian" in content:
                hook_path.unlink()
                removed.append(hook_name)

    if removed:
        print_success(f"Removed hooks: {', '.join(removed)}")
    else:
        print_info("No CodeGuardian hooks found.")


@app.command()
def status(
    path: str = typer.Option(".", "--path", "-p", help="Repository path"),
):
    """
    Check if CodeGuardian hooks are installed.

    Examples:
        cgctl hooks status
        cgctl hooks status --path /my/project
    """
    repo_path = Path(path).resolve()
    hooks_dir = repo_path / ".git" / "hooks"

    installed = []
    missing = []

    for hook_name in ["pre-commit", "post-commit"]:
        hook_path = hooks_dir / hook_name
        if hook_path.exists():
            content = hook_path.read_text(encoding="utf-8")
            if "CodeGuardian" in content:
                installed.append(hook_name)
            else:
                missing.append(hook_name)
        else:
            missing.append(hook_name)

    if installed:
        print_success(f"Installed: {', '.join(installed)}")
    if missing:
        console.print(f"[dim]Not installed:[/dim] {', '.join(missing)}")


@app.command()
def show(
    hook: str = typer.Argument(..., help="Hook name (pre-commit or post-commit)"),
    path: str = typer.Option(".", "--path", "-p", help="Repository path"),
):
    """
    Show the content of a CodeGuardian hook.

    Examples:
        cgctl hooks show pre-commit
        cgctl hooks show post-commit
    """
    repo_path = Path(path).resolve()
    hooks_dir = repo_path / ".git" / "hooks"
    hook_path = hooks_dir / hook

    if not hook_path.exists():
        print_error(f"Hook not found: {hook}")
        raise typer.Exit(1)

    content = hook_path.read_text(encoding="utf-8")

    if "CodeGuardian" not in content:
        print_error(f"File is not a CodeGuardian hook: {hook}")
        raise typer.Exit(1)

    syntax = Syntax(content, "bash", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"[bold]{hook}[/bold]", border_style="cyan"))