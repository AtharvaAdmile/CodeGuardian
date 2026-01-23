"""
Audit command for CodeGuardian CLI.

Runs all advanced context analyzers on a file and produces a rich report
showing experts, health score, compliance risks, and runtime stats.
"""

import typer
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

# Import analyzers
from src.analysis.git_context import GitContextAnalyzer
from src.analysis.expertise import ExpertiseTracker
from src.analysis.compliance import ComplianceScanner
from src.analysis.runtime import RuntimeLoader
from src.structure_analyzer import StructureAnalyzer

app = typer.Typer(help="Run code audits and analysis")
console = Console()


def get_project_root() -> Path:
    """Get project root from .codeguardian or current directory."""
    cwd = Path.cwd()
    marker = cwd / ".codeguardian"
    if marker.exists():
        return cwd
    return cwd


@app.command("file")
def audit_file(
    file_path: str = typer.Argument(..., help="Path to file to audit"),
    show_git: bool = typer.Option(True, "--git/--no-git", help="Show git history"),
    show_compliance: bool = typer.Option(True, "--compliance/--no-compliance", help="Run compliance scan"),
    show_runtime: bool = typer.Option(True, "--runtime/--no-runtime", help="Show runtime stats"),
):
    """
    Run a comprehensive audit on a single file.
    
    Analyzes expertise, health score, compliance, and runtime statistics.
    """
    path = Path(file_path)
    if not path.is_absolute():
        path = get_project_root() / path
        
    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {file_path}")
        raise typer.Exit(1)
    
    if not path.is_file():
        console.print(f"[red]Error:[/red] Not a file: {file_path}")
        raise typer.Exit(1)
    
    project_root = get_project_root()
    
    # Header
    console.print()
    console.print(Panel(
        f"[bold blue]📋 CODE AUDIT REPORT[/bold blue]\n[dim]{path.name}[/dim]",
        box=box.DOUBLE,
        expand=False
    ))
    console.print()
    
    # 1. Expertise Analysis
    console.print("[bold cyan]👤 EXPERTISE[/bold cyan]")
    try:
        tracker = ExpertiseTracker(str(project_root))
        expertise = tracker.find_owners(str(path))
        
        if "error" in expertise:
            console.print(f"  [dim]Could not analyze: {expertise['error']}[/dim]")
        else:
            primary = expertise.get("primary_expert", "Unknown")
            primary_score = expertise.get("primary_score", 0)
            backup = expertise.get("backup", "None")
            backup_score = expertise.get("backup_score", 0)
            last_active = expertise.get("last_active", "Unknown")
            
            console.print(f"  ├── Primary: [green]{primary}[/green] (score: {primary_score})")
            console.print(f"  ├── Backup: [yellow]{backup}[/yellow] (score: {backup_score})")
            console.print(f"  └── Last modified: [dim]{last_active}[/dim]")
    except Exception as e:
        console.print(f"  [red]Error:[/red] {e}")
    console.print()
    
    # 2. Health Score
    console.print("[bold cyan]📊 HEALTH SCORE[/bold cyan]")
    try:
        analyzer = StructureAnalyzer(str(project_root))
        health = analyzer.get_file_health(str(path))
        
        if "error" in health:
            console.print(f"  [dim]Could not analyze: {health['error']}[/dim]")
        else:
            score = health.get("health_score", 0)
            
            # Color based on score
            if score >= 80:
                score_color = "green"
                score_emoji = "✅"
            elif score >= 60:
                score_color = "yellow"
                score_emoji = "⚠️"
            elif score >= 40:
                score_color = "orange1"
                score_emoji = "⚠️"
            else:
                score_color = "red"
                score_emoji = "🔴"
            
            complexity = health.get("complexity", {})
            churn = health.get("churn", {})
            recommendation = health.get("recommendation", {})
            
            console.print(f"  {score_emoji} Score: [{score_color}]{score}/100[/{score_color}]")
            console.print(f"  ├── Complexity: {complexity.get('score', 0)} (Rank: {complexity.get('rank', 'N/A')})")
            console.print(f"  ├── Churn: {churn.get('score', 0)} edits in {churn.get('period_months', 6)} months ({churn.get('rank', 'N/A')})")
            console.print(f"  └── Recommendation: {recommendation.get('message', 'N/A')}")
            
            # Show complex functions if any
            functions = complexity.get("functions", [])
            if functions:
                console.print()
                console.print("  [dim]Most complex functions:[/dim]")
                for func in functions[:3]:
                    console.print(f"    • {func['name']} (complexity: {func['complexity']}, line {func['line']})")
    except Exception as e:
        console.print(f"  [red]Error:[/red] {e}")
    console.print()
    
    # 3. Compliance Scan
    if show_compliance:
        console.print("[bold cyan]🔒 COMPLIANCE[/bold cyan]")
        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
            scanner = ComplianceScanner()
            compliance = scanner.scan_code(content)
            
            if compliance.get("passed"):
                console.print("  [green]✅ No violations detected[/green]")
            else:
                violations = compliance.get("violations", [])
                severity_counts = compliance.get("severity_counts", {})
                
                status = "🛑 VIOLATIONS FOUND" if severity_counts.get("critical") else "⚠️ Warnings"
                console.print(f"  [{status}]")
                console.print(f"  ├── Critical: {severity_counts.get('critical', 0)}")
                console.print(f"  ├── High: {severity_counts.get('high', 0)}")
                console.print(f"  ├── Medium: {severity_counts.get('medium', 0)}")
                console.print(f"  └── Low: {severity_counts.get('low', 0)}")
                
                # Show first 5 violations
                if violations:
                    console.print()
                    console.print("  [dim]Top violations:[/dim]")
                    for v in violations[:5]:
                        severity_color = {
                            "critical": "red",
                            "high": "orange1",
                            "medium": "yellow",
                            "low": "dim"
                        }.get(v.get("severity", "low"), "dim")
                        console.print(f"    Line {v['line']}: [{severity_color}]{v['message']}[/{severity_color}]")
        except Exception as e:
            console.print(f"  [red]Error:[/red] {e}")
        console.print()
    
    # 4. Runtime Stats
    if show_runtime:
        console.print("[bold cyan]⚡ RUNTIME[/bold cyan]")
        try:
            loader = RuntimeLoader()
            runtime = loader.get_stats(str(path))
            
            if not runtime.get("available"):
                console.print("  [dim]No runtime data available for this file[/dim]")
            else:
                alert_level = runtime.get("alert_level", "none")
                error_rate = runtime.get("error_rate", 0)
                avg_latency = runtime.get("avg_latency_ms", 0)
                last_error = runtime.get("last_error")
                
                if alert_level == "critical":
                    console.print("  [red]🔴 CRITICAL ALERT[/red]")
                elif alert_level == "warning":
                    console.print("  [yellow]⚠️ WARNING[/yellow]")
                else:
                    console.print("  [green]✅ Healthy[/green]")
                
                console.print(f"  ├── Error Rate: {error_rate:.2f}%")
                console.print(f"  ├── Avg Latency: {avg_latency:.0f}ms")
                if last_error:
                    console.print(f"  └── Last Error: [dim]{last_error[:50]}...[/dim]")
                else:
                    console.print("  └── Last Error: [dim]None in 24h[/dim]")
        except Exception as e:
            console.print(f"  [red]Error:[/red] {e}")
        console.print()
    
    # 5. Git History (optional)
    if show_git:
        console.print("[bold cyan]📜 GIT HISTORY[/bold cyan]")
        try:
            git_analyzer = GitContextAnalyzer(str(project_root))
            history = git_analyzer.get_history(str(path))
            
            if "error" in history:
                console.print(f"  [dim]{history['error']}[/dim]")
            else:
                entries = history.get("history", [])[:5]
                if entries:
                    for entry in entries:
                        author = entry.get("author", "Unknown")
                        message = entry.get("message", "No message")[:50]
                        date = entry.get("date", "")[:10]
                        console.print(f"  • [{date}] [green]{author}[/green]: {message}")
                else:
                    console.print("  [dim]No git history available[/dim]")
                    
                # Churn info
                churn = git_analyzer.get_churn(str(path))
                if churn:
                    risk = churn.get("risk_level", "unknown")
                    count = churn.get("churn_count", 0)
                    console.print(f"\n  Churn: {count} commits in 6 months (risk: {risk})")
        except Exception as e:
            console.print(f"  [red]Error:[/red] {e}")
        console.print()
    
    console.print("[dim]Audit complete.[/dim]\n")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    file_path: Optional[str] = typer.Argument(None, help="Path to file to audit")
):
    """
    Run code audits and analysis on files.
    
    Usage:
        cgctl audit <file_path>
        cgctl audit file <file_path> [options]
    """
    if ctx.invoked_subcommand is None:
        if file_path:
            # Direct invocation: cgctl audit <file>
            audit_file(file_path)
        else:
            console.print("Usage: cgctl audit <file_path>")
            console.print("\nRun 'cgctl audit --help' for options.")
            raise typer.Exit(0)


if __name__ == "__main__":
    app()
