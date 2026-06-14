"""
Dashboard routes — aggregated project metrics for the Dashboard UI.

GET /api/dashboard/{project_path}  → returns computed metrics:
  - Files indexed (from vector store count or indexing status)
  - Last indexed at (timestamp from index history)
  - Recent commits (from git service)
  - Hotspots (files with health_score < 0.5)
  - Graph stats (nodes, edges from knowledge graph)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("codeguardian.routes.dashboard")

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_HISTORY_DIR = ".codeguardian/index_history"


def _load_last_index_history(project_id: str) -> dict | None:
    """Load the most recent index history entry for a project."""
    path = Path(_HISTORY_DIR) / f"{project_id}.json"
    if not path.exists():
        return None
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
        if entries:
            return entries[-1]
    except (json.JSONDecodeError, OSError):
        pass
    return None


class RecentCommit(BaseModel):
    sha: str
    message: str
    author: str
    date: str
    files_changed: list[str] = Field(default_factory=list)


class DashboardHotspot(BaseModel):
    file_path: str
    health_score: float
    reason: str


class RecentQuestion(BaseModel):
    session_id: str
    title: str = ""
    preview: str = ""
    created_at: str = ""
    updated_at: str = ""
    message_count: int = 0


class DashboardResponse(BaseModel):
    project_path: str
    files_indexed: int = 0
    graph_nodes: int = 0
    graph_edges: int = 0
    last_indexed_at: str | None = None
    hotspots: list[DashboardHotspot] = Field(default_factory=list)
    recent_commits: list[RecentCommit] = Field(default_factory=list)
    is_indexing: bool = False
    index_status: str = ""
    index_job_id: str | None = None
    recent_questions: list[RecentQuestion] = Field(default_factory=list)
    error: str | None = None


@router.get("/{project_path:path}", response_model=DashboardResponse)
async def get_dashboard_metrics(project_path: str, request: Request) -> DashboardResponse:
    """
    Aggregate metrics from knowledge_graph, git, and index status for the dashboard.
    """
    pp = Path(project_path)
    if not pp.exists() or not pp.is_dir():
        raise HTTPException(404, f"Project path not found: {project_path}")

    result = DashboardResponse(project_path=project_path)
    project_id = pp.name

    try:
        knowledge_graph = getattr(request.app.state, "knowledge_graph", None)
        index_jobs: dict = getattr(request.app.state, "index_jobs", {})

        if knowledge_graph and not knowledge_graph.is_empty():
            stats = knowledge_graph.get_stats()
            result.graph_nodes = stats.get("total_nodes", 0)
            result.graph_edges = stats.get("total_edges", 0)

            hotspots: list[DashboardHotspot] = []
            for node_id, node_data in knowledge_graph._graph.nodes(data=True):
                if node_data.get("type") == "file":
                    health = node_data.get("health_score", 0.0)
                    if health < 0.5:
                        reason = "Low health score - consider refactoring" if health > 0 else "Missing health score"
                        hotspots.append(DashboardHotspot(
                            file_path=node_id,
                            health_score=round(health, 2),
                            reason=reason,
                        ))
            result.hotspots = sorted(hotspots, key=lambda h: h.health_score)[:10]

        vector_service = getattr(request.app.state, "vector_service", None)

        # ── Active index job takes priority (in-memory, real-time) ────
        if index_jobs:
            for job_id, status in index_jobs.items():
                result.index_job_id = job_id
                result.index_status = status.status
                if status.status == "running":
                    result.is_indexing = True
                    result.files_indexed = status.files_processed or 0
                    break
                elif status.status == "completed":
                    result.files_indexed = status.files_processed or 0
                    break

        # ── No active job — read from vector store (persists restarts) ─
        if not result.is_indexing and result.files_indexed == 0:
            if vector_service and vector_service.has_project_index(project_id):
                result.files_indexed = vector_service.get_indexed_file_count(project_id)
                result.index_status = "completed"
            else:
                last_entry = _load_last_index_history(project_id)
                if last_entry:
                    result.files_indexed = last_entry.get("files", 0)
                    result.index_status = last_entry.get("status", "completed")

        # ── Last indexed timestamp ────────────────────────────────────
        last_entry = _load_last_index_history(project_id)
        if last_entry and last_entry.get("date"):
            result.last_indexed_at = last_entry["date"]

        # ── Recent commits via on-the-fly GitService ──────────────────
        try:
            from server.services.git_service import GitService

            git_svc = GitService(str(pp))
            commits = git_svc.get_recent_commits(limit=10)
            result.recent_commits = [
                RecentCommit(
                    sha=c.sha,
                    message=c.message.split("\n")[0] if c.message else "",
                    author=c.author,
                    date=c.date.isoformat() if c.date else "",
                    files_changed=c.files_changed,
                )
                for c in commits
            ]
        except Exception as exc:
            logger.debug("Failed to load recent commits: %s", exc)

        # ── Recent CG-pilot questions ─────────────────────────────────
        chat_history = getattr(request.app.state, "chat_history_service", None)
        if chat_history:
            try:
                recent = chat_history.get_recent(project_id, limit=5)
                result.recent_questions = [
                    RecentQuestion(**q) for q in recent
                ]
            except Exception as exc:
                logger.debug("Failed to load recent questions: %s", exc)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error getting dashboard metrics")
        result.error = str(exc)

    return result