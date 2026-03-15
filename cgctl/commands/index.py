"""
cgctl index — Index a codebase into the vector store.

Connected mode (default):
    POST /api/index → job_id, then poll /api/index/status/{job_id}
    with a Rich multi-phase progress display.

Offline mode (--offline):
    Falls back to direct Python imports from the src.* legacy modules.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import typer
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from cgctl.utils.output import (
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
    print_header,
    print_stats,
    print_file_tree,
)
from cgctl.utils.validators import validate_project_path

app = typer.Typer(help="Index a codebase for semantic search")

# ── Helpers ───────────────────────────────────────────────────────────────


def _read_project_id(project_path: str) -> Optional[str]:
    """Read project_id from .codeguardian/config.toml or legacy .codeguardian file."""
    cg_dir = Path(project_path) / ".codeguardian"

    # New-style config.toml
    config = cg_dir / "config.toml"
    if config.exists():
        for line in config.read_text().splitlines():
            line = line.strip()
            if line.startswith("project_id"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    # Legacy flat file
    flat = Path(project_path) / ".codeguardian"
    if flat.is_file():
        for line in flat.read_text().splitlines():
            if line.startswith("project_id"):
                return line.split("=", 1)[1].strip().strip('"')

    # Fallback: use directory name (same as server convention)
    return os.path.basename(project_path)


_PHASE_STYLE = {
    "pending":   ("[dim]pending[/dim]",  "dim"),
    "running":   ("[yellow]running[/yellow]", "yellow"),
    "completed": ("[green]done[/green]",  "green"),
    "failed":    ("[red]failed[/red]",   "red"),
    "skipped":   ("[dim]skipped[/dim]",  "dim"),
}


def _phase_str(status: str) -> str:
    return _PHASE_STYLE.get(status, (f"[dim]{status}[/dim]", "dim"))[0]


def _build_status_table(status: dict) -> Table:
    """Build a Rich table showing 4-phase indexing progress."""
    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column("Phase", style="bold", width=22)
    table.add_column("Status", width=18)
    table.add_column("Detail", style="dim")

    # Phase 1: Code indexing
    fp = status.get("files_processed", 0)
    ft = status.get("files_total", 0)
    cc = status.get("chunks_created", 0)
    p1_det = f"{fp}/{ft} files, {cc} chunks" if ft else f"{cc} chunks"
    table.add_row(
        "1. Code indexing",
        "[green]done[/green]" if fp and fp == ft else "[yellow]running[/yellow]" if fp else "[dim]pending[/dim]",
        p1_det,
    )

    # Phase 2–4
    for label, key_status in (
        ("2. Expertise mapping", "expertise_status"),
        ("3. Decision extraction", "decision_status"),
        ("4. Knowledge graph", "graph_status"),
    ):
        s = status.get(key_status, "pending")
        table.add_row(label, _phase_str(s), "")

    return table


def _poll_index(client, job_id: str, project_id: str) -> bool:
    """Poll the index-status endpoint with a Live display. Returns True on success."""
    url = f"/api/index/status/{job_id}"

    with Live(console=console, refresh_per_second=4) as live:
        while True:
            try:
                status = client.get(url)
            except Exception as exc:
                live.stop()
                print_error(f"Status poll failed: {exc}")
                return False

            job_status = status.get("status", "queued")
            table = _build_status_table(status)
            errors = status.get("errors", [])

            panel_title = {
                "queued":    "[dim]Queued…[/dim]",
                "running":   "[yellow]Indexing…[/yellow]",
                "completed": "[green]Complete[/green]",
                "failed":    "[red]Failed[/red]",
            }.get(job_status, job_status)

            live.update(Panel(table, title=panel_title, border_style="cyan"))

            if job_status == "completed":
                live.stop()
                fp = status.get("files_processed", 0)
                cc = status.get("chunks_created", 0)
                gn = status.get("graph_nodes", 0)
                ge = status.get("graph_edges", 0)
                dn = status.get("decisions_found", 0)
                print_stats({
                    "Files indexed": fp,
                    "Chunks created": cc,
                    "Graph nodes": gn,
                    "Graph edges": ge,
                    "Decisions found": dn,
                })
                if errors:
                    print_warning(f"{len(errors)} error(s) during indexing:")
                    for e in errors[:3]:
                        console.print(f"  [red]•[/red] {e}")
                return True

            if job_status == "failed":
                live.stop()
                msg = status.get("error_message") or "Unknown error"
                print_error(f"Indexing failed: {msg}")
                return False

            time.sleep(1.0)


# ── Commands ──────────────────────────────────────────────────────────────


@app.callback(invoke_without_command=True)
def index_project(
    ctx: typer.Context,
    path: str = typer.Argument(".", help="Path to the project directory"),
    force: bool = typer.Option(False, "--force", "-f", help="Re-index even if already indexed"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be indexed without indexing"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Override project ID"),
):
    """
    Index a codebase into the vector store and knowledge graph.

    Connected mode: delegates to the FastAPI server (POST /api/index),
    then shows a live multi-phase progress display while polling.

    Offline mode (--offline): uses local sentence-transformers and ChromaDB
    directly (legacy behaviour).

    Examples:
        cgctl index
        cgctl index /path/to/project --force
        cgctl index --offline
    """
    from cgctl.client import is_offline, make_client

    project_path = os.path.abspath(os.path.expanduser(path))

    is_valid, error = validate_project_path(project_path)
    if not is_valid:
        print_error(error)
        raise typer.Exit(1)

    pid = project_id or _read_project_id(project_path)

    print_header("CodeGuardian Indexing", f"Project: [cyan]{pid}[/cyan]")
    print_info(f"Path: [cyan]{project_path}[/cyan]")

    # ── Dry run (local file scan, no server needed) ─────────────────────
    if dry_run:
        _dry_run(project_path)
        raise typer.Exit(0)

    # ── Offline mode ─────────────────────────────────────────────────────
    if is_offline():
        _index_offline(project_path, pid, force)
        return

    # ── Connected mode ───────────────────────────────────────────────────
    client = make_client()
    try:
        print_info("Submitting indexing job to server…")
        resp = client.post(
            "/api/index",
            {"project_id": pid, "project_path": project_path, "force": force},
        )
        job_id = resp.get("job_id", "")
        if not job_id:
            print_error(f"Unexpected response: {resp}")
            raise typer.Exit(1)

        print_success(f"Job queued: [dim]{job_id}[/dim]")
        console.print()
        ok = _poll_index(client, job_id, pid)
        if ok:
            print_success("Codebase indexed successfully!")
            print_info("Run [cyan]cgctl ask \"your question\"[/cyan] to start querying.")
        else:
            raise typer.Exit(1)

    except ConnectionError as exc:
        console.print(f"\n[red]✗[/red] {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        print_error(f"Indexing failed: {exc}")
        raise typer.Exit(1)


def _dry_run(project_path: str) -> None:
    exts = {".py", ".js", ".ts", ".jsx", ".tsx"}
    skip = {"node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build"}
    files = []
    for root, dirs, fnames in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in fnames:
            if Path(f).suffix.lower() in exts:
                files.append(os.path.relpath(os.path.join(root, f), project_path))
    print_header("Dry Run — Files to Index")
    print_stats({"Total files": len(files)})
    print_file_tree(files[:60])
    if len(files) > 60:
        print_info(f"… and {len(files) - 60} more files")


def _index_offline(project_path: str, project_id: str, force: bool) -> None:
    """Legacy offline indexing via src.* imports."""
    print_info("Running in [yellow]offline[/yellow] mode (local embeddings)")
    try:
        from src.embedding_generator import EmbeddingGenerator  # type: ignore
        from src.vector_store import VectorStore  # type: ignore
        from src.code_parser import CodeParser  # type: ignore
        from src.text_chunker import TextChunker  # type: ignore
    except ImportError as exc:
        print_error(
            f"Offline mode requires legacy src modules: {exc}\n"
            "Remove --offline to use the server instead."
        )
        raise typer.Exit(1)

    chroma_path = str(Path(project_path) / "chroma_data")
    exts = [".py", ".js", ".ts", ".jsx", ".tsx"]
    skip = {"node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build"}

    files = []
    for root, dirs, fnames in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in fnames:
            if Path(f).suffix.lower() in exts:
                full = os.path.join(root, f)
                files.append({"full_path": full, "path": os.path.relpath(full, project_path)})

    if not files:
        print_warning("No supported files found.")
        return

    print_info(f"Found {len(files)} files. Loading embedding model…")

    try:
        from cgctl.utils.output import create_progress

        embed_gen = EmbeddingGenerator()
        vector_store = VectorStore(persist_directory=chroma_path)
        parser = CodeParser()
        chunker = TextChunker()

        if force:
            try:
                vector_store.delete_collection("codeguardian")
            except Exception:
                pass

        collection = vector_store.create_collection("codeguardian")
        all_chunks: list[dict] = []

        with create_progress() as progress:
            task = progress.add_task("Parsing files…", total=len(files))
            for fi in files:
                try:
                    content = open(fi["full_path"], encoding="utf-8", errors="ignore").read()
                    parsed = parser.parse_file(fi["path"], content)
                    for chunk in chunker.chunk_code(parsed):
                        all_chunks.append({
                            "id": f"{project_id}_{fi['path']}_{chunk.metadata.start_line}",
                            "text": chunk.content,
                            "metadata": {
                                "file_path": fi["path"],
                                "start_line": chunk.metadata.start_line,
                                "end_line": chunk.metadata.end_line,
                                "project_id": project_id,
                            },
                        })
                except Exception:
                    pass
                progress.advance(task)

        with create_progress() as progress:
            task = progress.add_task("Generating embeddings…", total=len(all_chunks))
            batch_size = 32
            for i in range(0, len(all_chunks), batch_size):
                batch = all_chunks[i: i + batch_size]
                texts = [c["text"] for c in batch]
                embeddings = embed_gen.generate_batch_embeddings(texts)
                vector_store.add_embeddings(
                    collection_name="codeguardian",
                    embeddings=embeddings,
                    documents=texts,
                    metadatas=[c["metadata"] for c in batch],
                    ids=[c["id"] for c in batch],
                )
                progress.advance(task, advance=len(batch))

        print_success(f"Offline index complete: {len(all_chunks)} chunks stored in ChromaDB.")

    except Exception as exc:
        print_error(f"Offline indexing failed: {exc}")
        raise typer.Exit(1)


@app.command("status")
def index_status(
    path: str = typer.Option(".", "--path", "-p", help="Project path"),
    job_id: Optional[str] = typer.Option(None, "--job-id", help="Specific job ID to check"),
):
    """Show current indexing status."""
    from cgctl.client import is_offline, make_client

    if is_offline():
        print_info("Status check is not available in offline mode.")
        return

    project_path = os.path.abspath(os.path.expanduser(path))
    pid = _read_project_id(project_path)

    client = make_client()
    try:
        if job_id:
            status = client.get(f"/api/index/status/{job_id}")
        else:
            status = client.get(f"/api/index/status/latest?project_id={pid}")
        console.print(_build_status_table(status))
    except ConnectionError as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        print_error(f"Could not fetch status: {exc}")
        raise typer.Exit(1)
