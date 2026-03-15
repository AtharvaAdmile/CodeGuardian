"""
Impact analysis routes.

POST /api/impact/analyze
    Compute the blast radius of a changed file: which other files are
    affected, how risky each is, and who should review the change.

POST /api/impact/breaking-changes
    Detect API-level breaking changes between two versions of a file using
    AST comparison (Python) or regex (JS/TS).  No LLM involved.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Request

from server.models.route_schemas import (
    AffectedFileSchema,
    BreakingChangeSchema,
    BreakingChangesRequest,
    BreakingChangesResponse,
    ImpactAnalyzeRequest,
    ImpactAnalyzeResponse,
)

logger = logging.getLogger("codeguardian.routes.impact")

router = APIRouter(prefix="/api/impact", tags=["impact"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _to_rel(project_path: str, file_path: str) -> str:
    """
    Normalise *file_path* to a project-relative POSIX string.

    Accepts absolute or relative inputs; strips the project root prefix when
    absolute.
    """
    fp = Path(file_path)
    if fp.is_absolute():
        try:
            return fp.relative_to(project_path).as_posix()
        except ValueError:
            return fp.as_posix()
    return fp.as_posix()


def _affected_schema(af: object) -> AffectedFileSchema:
    return AffectedFileSchema(
        file_path=af.file_path,
        risk_score=af.risk_score,
        distance=af.distance,
        reason=af.reason,
    )


# ── POST /api/impact/analyze ──────────────────────────────────────────────────


@router.post("/analyze", response_model=ImpactAnalyzeResponse)
async def analyze_impact(body: ImpactAnalyzeRequest, request: Request) -> ImpactAnalyzeResponse:
    """
    Compute the blast radius of changing *file_path* inside *project_path*.

    Uses the in-memory knowledge graph when available (populated by the
    indexing pipeline).  Falls back to building a fresh dependency graph
    on-the-fly when the knowledge graph is empty.

    The optional *diff* field is reserved for future breaking-change
    integration at the route layer (not yet used in risk scoring).
    """
    from server.services.impact_engine import (
        BlastRadiusCalculator,
        build_dependency_graph,
    )

    project_path: str = body.project_path
    rel_file: str = _to_rel(project_path, body.file_path)

    # ── Choose graph source ────────────────────────────────────────────
    kg = getattr(request.app.state, "knowledge_graph", None)
    git_service = getattr(request.app.state, "git_service", None)

    try:
        if kg is not None and not kg.is_empty():
            # Use the KG's internal graph directly; it already has import edges.
            graph = kg._graph
        else:
            # Build a fresh dependency graph (CPU-bound → run in thread).
            logger.info(
                "Knowledge graph empty — building dep graph for %s", project_path
            )
            graph = await asyncio.to_thread(build_dependency_graph, project_path)

        calc = BlastRadiusCalculator()
        report = await asyncio.to_thread(
            calc.calculate_blast_radius,
            rel_file,
            graph,
            git_service,
            kg,
        )

        return ImpactAnalyzeResponse(
            changed_file=report.changed_file,
            total_affected=report.total_affected,
            high_risk=[_affected_schema(f) for f in report.high_risk],
            medium_risk=[_affected_schema(f) for f in report.medium_risk],
            low_risk=[_affected_schema(f) for f in report.low_risk],
            affected_modules=report.affected_modules,
            suggested_reviewers=report.suggested_reviewers,
        )

    except Exception as exc:
        logger.exception("Impact analysis failed for %s: %s", rel_file, exc)
        return ImpactAnalyzeResponse(
            changed_file=rel_file,
            error=str(exc),
        )


# ── POST /api/impact/breaking-changes ────────────────────────────────────────


@router.post("/breaking-changes", response_model=BreakingChangesResponse)
async def check_breaking_changes(
    body: BreakingChangesRequest,
) -> BreakingChangesResponse:
    """
    Detect API-level breaking changes between *old_content* and *new_content*.

    Uses AST comparison for Python, regex for JS/TS.  Deterministic — no LLM.

    Returns every detected change classified as "breaking" or "non-breaking",
    along with old/new signature strings and a human-readable description.
    """
    from server.services.impact_engine import detect_breaking_changes

    try:
        raw_changes = await asyncio.to_thread(
            detect_breaking_changes,
            body.old_content,
            body.new_content,
            body.language,
        )

        changes = [
            BreakingChangeSchema(
                symbol=c.symbol,
                change_type=c.change_type,
                severity=c.severity,
                old_signature=c.old_signature,
                new_signature=c.new_signature,
                description=c.description,
            )
            for c in raw_changes
        ]

        return BreakingChangesResponse(
            changes=changes,
            total_breaking=sum(1 for c in changes if c.severity == "breaking"),
            total_non_breaking=sum(1 for c in changes if c.severity == "non-breaking"),
        )

    except Exception as exc:
        logger.exception("Breaking-change detection failed: %s", exc)
        return BreakingChangesResponse(error=str(exc))
