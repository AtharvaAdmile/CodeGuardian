"""
Rich console output utilities for CodeGuardian CLI.

Provides styled output, progress bars, and syntax highlighting.
"""

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.syntax import Syntax
from rich.table import Table
from rich.markdown import Markdown
from rich.tree import Tree
from rich import print as rprint
from typing import Optional, List, Dict, Any

# Global console instance
console = Console()


def print_success(message: str) -> None:
    """Print a success message in green."""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print an error message in red."""
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message in yellow."""
    console.print(f"[yellow]⚠[/yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message in blue."""
    console.print(f"[blue]ℹ[/blue] {message}")


def print_header(title: str, subtitle: Optional[str] = None) -> None:
    """Print a styled header."""
    console.print()
    console.print(Panel(
        f"[bold cyan]{title}[/bold cyan]" + 
        (f"\n[dim]{subtitle}[/dim]" if subtitle else ""),
        border_style="cyan"
    ))
    console.print()


def print_code(code: str, language: str = "python", title: Optional[str] = None) -> None:
    """Print syntax-highlighted code."""
    syntax = Syntax(code, language, theme="monokai", line_numbers=True)
    if title:
        console.print(Panel(syntax, title=title, border_style="dim"))
    else:
        console.print(syntax)


def print_source_reference(
    file_path: str,
    start_line: int,
    end_line: int,
    similarity: Optional[float] = None
) -> None:
    """Print a source code reference."""
    sim_text = f" [dim](similarity: {similarity:.2f})[/dim]" if similarity else ""
    console.print(f"  [cyan]📄 {file_path}[/cyan] [dim]lines {start_line}-{end_line}[/dim]{sim_text}")


def print_sources_table(sources: List[Dict[str, Any]]) -> None:
    """Print a table of source references."""
    if not sources:
        return
    
    table = Table(title="Source References", show_header=True, header_style="bold cyan")
    table.add_column("File", style="cyan")
    table.add_column("Lines", justify="center")
    table.add_column("Similarity", justify="right")
    
    for source in sources:
        table.add_row(
            source.get("file_path", "unknown"),
            f"{source.get('start_line', 0)}-{source.get('end_line', 0)}",
            f"{source.get('similarity', 0):.2f}" if source.get('similarity') else "-"
        )
    
    console.print(table)


def print_markdown(text: str) -> None:
    """Print markdown-formatted text."""
    console.print(Markdown(text))


def print_stats(stats: Dict[str, Any], title: str = "Statistics") -> None:
    """Print a stats table."""
    table = Table(title=title, show_header=False, border_style="dim")
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="bold")
    
    for key, value in stats.items():
        table.add_row(key.replace("_", " ").title(), str(value))
    
    console.print(table)


def create_progress() -> Progress:
    """Create a styled progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


def print_file_tree(files: List[str], title: str = "Files") -> None:
    """Print a file tree structure."""
    tree = Tree(f"[bold cyan]{title}[/bold cyan]")
    
    # Group by directory
    dirs: Dict[str, List[str]] = {}
    for file in files:
        parts = file.split("/")
        if len(parts) > 1:
            dir_path = "/".join(parts[:-1])
            if dir_path not in dirs:
                dirs[dir_path] = []
            dirs[dir_path].append(parts[-1])
        else:
            if "" not in dirs:
                dirs[""] = []
            dirs[""].append(file)
    
    for dir_path, filenames in sorted(dirs.items()):
        if dir_path:
            branch = tree.add(f"[blue]📁 {dir_path}[/blue]")
            for filename in sorted(filenames):
                branch.add(f"[dim]📄 {filename}[/dim]")
        else:
            for filename in sorted(filenames):
                tree.add(f"[dim]📄 {filename}[/dim]")
    
    console.print(tree)
