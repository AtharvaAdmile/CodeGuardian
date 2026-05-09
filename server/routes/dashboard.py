"""
Dashboard routes — aggregated project metrics for the Dashboard UI.

GET /api/dashboard/{project_path}  → returns computed metrics:
  - Files indexed (from vector store count or indexing status)
  - Avg health score (from knowledge graph file health)
  - Hotspots (files with health_score < 0.5)
  - Graph stats (nodes, edges from knowledge graph)
  - Decisions count (from decision service, 0 if none)
  - Expert count (from KG author nodes, 0 if none)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("codeguardian.routes.dashboard")

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_SKIP_DIRS = frozenset(
    {"node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build",
     "chroma_data", "generated_test_cases", ".codeguardian", "coverage"}
)
_VALID_EXTENSIONS = frozenset({".py", ".js", ".ts", ".jsx", ".tsx"})


class DashboardHotspot(BaseModel):
    file_path: str
    health_score: float
    reason: str


class DashboardResponse(BaseModel):
    project_path: str
    files_indexed: int = 0
    decisions_count: int = 0
    avg_health_score: float = 0.0
    expertise_count: int = 0
    hotspots: list[DashboardHotspot] = Field(default_factory=list)
    graph_nodes: int = 0
    graph_edges: int = 0
    is_indexing: bool = False
    index_status: str = ""
    index_job_id: str | None = None
    error: str | None = None


def _count_source_files(project_path: str) -> int:
    """Count source files in the project directory."""
    count = 0
    root = Path(project_path)
    if not root.exists():
        return 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for fname in filenames:
            if Path(fname).suffix.lower() in _VALID_EXTENSIONS:
                count += 1
    return count


@router.get("/{project_path:path}", response_model=DashboardResponse)
async def get_dashboard_metrics(project_path: str, request: Request) -> DashboardResponse:
    """
    Aggregate metrics from knowledge_graph and index status for the dashboard.

    Returns comprehensive project health metrics including:
    - Total files indexed (from vector store)
    - Average health score (from knowledge graph)
    - Hotspots (files with health score < 0.5)
    - Knowledge graph stats (nodes, edges)
    """
    pp = Path(project_path)
    if not pp.exists() or not pp.is_dir():
        raise HTTPException(404, f"Project path not found: {project_path}")

    result = DashboardResponse(project_path=project_path)

    try:
        knowledge_graph = getattr(request.app.state, "knowledge_graph", None)
        decision_service = getattr(request.app.state, "decision_service", None)
        index_jobs: dict = getattr(request.app.state, "index_jobs", {})

        if knowledge_graph and not knowledge_graph.is_empty():
            stats = knowledge_graph.get_stats()
            result.graph_nodes = stats.get("total_nodes", 0)
            result.graph_edges = stats.get("total_edges", 0)

            expertise_count = 0
            for node_id, node_data in knowledge_graph._graph.nodes(data=True):
                if node_data.get("type") == "author":
                    expertise_count += 1
            result.expertise_count = expertise_count

            hotspots: list[DashboardHotspot] = []
            total_health = 0.0
            file_count = 0

            for node_id, node_data in knowledge_graph._graph.nodes(data=True):
                if node_data.get("type") == "file":
                    health = node_data.get("health_score", 1.0)
                    total_health += health
                    file_count += 1

                    if health < 0.5:
                        hotspots.append(DashboardHotspot(
                            file_path=node_id,
                            health_score=round(health, 2),
                            reason="Low health score - consider refactoring"
                        ))

            if file_count > 0:
                result.avg_health_score = round(total_health / file_count, 2)

            result.hotspots = sorted(hotspots, key=lambda h: h.health_score)[:10]

        if decision_service:
            project_id = pp.name
            try:
                decisions = decision_service.get_decisions_by_project(project_id)
                result.decisions_count = len(decisions)
            except Exception:
                result.decisions_count = 0

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

        if not result.is_indexing and result.files_indexed == 0:
            result.files_indexed = _count_source_files(project_path)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error getting dashboard metrics")
        result.error = str(exc)

    return result