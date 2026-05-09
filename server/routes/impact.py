"""
Impact analysis routes.

POST /api/impact/analyze
    Compute blast radius, synthesize an LLM-backed impact analysis, and
    persist it for the selected file.

POST /api/impact/saved
    Return a previously generated impact analysis without re-analyzing.

POST /api/impact/breaking-changes
    Detect API-level breaking changes between two versions of a file using
    AST comparison (Python) or regex (JS/TS).  No LLM involved.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

_CACHE_FILENAME = "impact_analysis.json"
_FILE_CONTEXT_LIMIT = 12000


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


def _cache_path(project_path: str) -> Path:
    root = Path(project_path).expanduser().resolve()
    return root / ".codeguardian" / _CACHE_FILENAME


def _load_cache(project_path: str) -> dict[str, Any]:
    path = _cache_path(project_path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read impact cache %s: %s", path, exc)
        return {}


def _save_cache(project_path: str, cache: dict[str, Any]) -> None:
    path = _cache_path(project_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write impact cache %s: %s", path, exc)


def _response_from_cache(project_path: str, rel_file: str) -> ImpactAnalyzeResponse | None:
    payload = _load_cache(project_path).get(rel_file)
    if not payload:
        return None
    try:
        return ImpactAnalyzeResponse.model_validate(payload)
    except Exception as exc:
        logger.warning("Ignoring invalid cached impact analysis for %s: %s", rel_file, exc)
        return None


def _store_response(project_path: str, rel_file: str, response: ImpactAnalyzeResponse) -> None:
    cache = _load_cache(project_path)
    cache[rel_file] = response.model_dump()
    _save_cache(project_path, cache)


def _read_file_excerpt(project_path: str, rel_file: str) -> str:
    root = Path(project_path).expanduser().resolve()
    target = (root / rel_file).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return ""
    if not target.is_file():
        return ""
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return content[:_FILE_CONTEXT_LIMIT]


def _extract_dependency_context(project_path: str, rel_file: str) -> dict[str, Any]:
    from server.services.impact_engine import DependencyAnalyzer

    excerpt = _read_file_excerpt(project_path, rel_file)
    if not excerpt:
        return {"imports": [], "function_calls": [], "inheritance": []}

    analyzer = DependencyAnalyzer()
    imports = [
        {
            "specifier": item.raw_specifier,
            "type": item.import_type,
            "line": item.line_number,
            "resolved_path": item.resolved_path,
        }
        for item in analyzer.extract_imports(excerpt, rel_file)
    ]
    return {"imports": imports[:40], "function_calls": [], "inheritance": []}


def _git_history_context(project_path: str, rel_file: str) -> list[dict[str, Any]]:
    try:
        from server.services.git_service import GitService

        service = GitService(project_path)
        history = service.get_file_history(rel_file, limit=8)
    except Exception as exc:
        logger.debug("Impact git history lookup failed for %s: %s", rel_file, exc)
        return []

    return [
        {
            "sha": item.sha[:7],
            "author": item.author,
            "date": item.date.isoformat(),
            "message": item.message,
        }
        for item in history
    ]


def _report_payload(report: ImpactAnalyzeResponse) -> dict[str, Any]:
    return {
        "changed_file": report.changed_file,
        "total_affected": report.total_affected,
        "high_risk": [item.model_dump() for item in report.high_risk],
        "medium_risk": [item.model_dump() for item in report.medium_risk],
        "low_risk": [item.model_dump() for item in report.low_risk],
        "affected_modules": report.affected_modules,
        "suggested_reviewers": report.suggested_reviewers,
    }


def _fallback_synthesis(report: ImpactAnalyzeResponse) -> dict[str, Any]:
    high = len(report.high_risk)
    medium = len(report.medium_risk)
    low = len(report.low_risk)
    return {
        "agent_summary": (
            f"{report.changed_file} has {report.total_affected} downstream file(s): "
            f"{high} high risk, {medium} medium risk, and {low} low risk."
        ),
        "risk_assessment": "Review the high-risk downstream files first, then validate affected modules with targeted tests.",
        "recommendations": [
            "Inspect direct dependents before changing public interfaces.",
            "Run tests covering the affected modules.",
            "Ask suggested reviewers to check risky downstream usage.",
        ],
        "validation_steps": [
            "Run the file's unit tests.",
            "Run integration tests for affected modules.",
            "Search for runtime references not captured by static imports.",
        ],
    }


def _parse_llm_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_string_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned or fallback


async def _synthesize_with_llm(
    *,
    llm_client: object | None,
    project_path: str,
    rel_file: str,
    report: ImpactAnalyzeResponse,
) -> tuple[dict[str, Any], list[str]]:
    tools_used = [
        "blast_radius_graph",
        "dependency_context",
        "git_history",
        "file_excerpt",
    ]
    dependency_context = _extract_dependency_context(project_path, rel_file)
    git_history = _git_history_context(project_path, rel_file)
    file_excerpt = _read_file_excerpt(project_path, rel_file)

    if llm_client is None:
        synthesis = _fallback_synthesis(report)
        synthesis["tools_used"] = tools_used
        return synthesis, tools_used

    payload = {
        "target_file": rel_file,
        "blast_radius": _report_payload(report),
        "dependency_context": dependency_context,
        "git_history": git_history,
        "file_excerpt": file_excerpt,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You are CodeGuardian's impact-analysis agent. Use only the provided tool outputs. "
                "Return strict JSON with keys: agent_summary, risk_assessment, recommendations, validation_steps. "
                "Keep recommendations specific and actionable."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False),
        },
    ]

    try:
        response = await llm_client.complete(
            messages,
            temperature=0.2,
            max_tokens=1200,
            thinking_mode=False,
        )
    except Exception as exc:
        logger.warning("LLM impact synthesis failed for %s: %s", rel_file, exc)
        synthesis = _fallback_synthesis(report)
        synthesis["tools_used"] = tools_used
        return synthesis, tools_used

    parsed = _parse_llm_json(getattr(response, "content", ""))
    fallback = _fallback_synthesis(report)
    synthesis = {
        "agent_summary": str(parsed.get("agent_summary") or fallback["agent_summary"]),
        "risk_assessment": str(parsed.get("risk_assessment") or fallback["risk_assessment"]),
        "recommendations": _as_string_list(
            parsed.get("recommendations"), fallback["recommendations"]
        )[:8],
        "validation_steps": _as_string_list(
            parsed.get("validation_steps"), fallback["validation_steps"]
        )[:8],
        "tools_used": tools_used + ["llm_synthesis"],
    }
    return synthesis, synthesis["tools_used"]


# ── POST /api/impact/analyze ──────────────────────────────────────────────────


@router.post("/analyze", response_model=ImpactAnalyzeResponse)
async def analyze_impact(body: ImpactAnalyzeRequest, request: Request) -> ImpactAnalyzeResponse:
    """
    Compute and persist the agentic impact analysis for *file_path*.

    Uses the in-memory knowledge graph when available (populated by the
    indexing pipeline).  Falls back to building a fresh dependency graph
    on-the-fly when the knowledge graph is empty, then asks the configured
    LLM to synthesize the tool outputs into developer-facing guidance.
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

        base_response = ImpactAnalyzeResponse(
            changed_file=report.changed_file,
            total_affected=report.total_affected,
            high_risk=[_affected_schema(f) for f in report.high_risk],
            medium_risk=[_affected_schema(f) for f in report.medium_risk],
            low_risk=[_affected_schema(f) for f in report.low_risk],
            affected_modules=report.affected_modules,
            suggested_reviewers=report.suggested_reviewers,
        )

        synthesis, tools_used = await _synthesize_with_llm(
            llm_client=getattr(request.app.state, "llm_client", None),
            project_path=project_path,
            rel_file=rel_file,
            report=base_response,
        )
        response = base_response.model_copy(
            update={
                "agent_summary": synthesis.get("agent_summary", ""),
                "risk_assessment": synthesis.get("risk_assessment", ""),
                "recommendations": synthesis.get("recommendations", []),
                "validation_steps": synthesis.get("validation_steps", []),
                "tools_used": tools_used,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "persisted": True,
            }
        )
        _store_response(project_path, rel_file, response)
        return response

    except Exception as exc:
        logger.exception("Impact analysis failed for %s: %s", rel_file, exc)
        return ImpactAnalyzeResponse(
            changed_file=rel_file,
            error=str(exc),
        )


@router.post("/saved", response_model=ImpactAnalyzeResponse)
async def get_saved_impact_analysis(body: ImpactAnalyzeRequest) -> ImpactAnalyzeResponse:
    """Return persisted impact analysis for a file without re-running analysis."""
    project_path: str = body.project_path
    rel_file: str = _to_rel(project_path, body.file_path)
    cached = _response_from_cache(project_path, rel_file)
    if cached is None:
        return ImpactAnalyzeResponse(
            changed_file=rel_file,
            persisted=False,
            error="No saved impact analysis for this file.",
        )
    return cached


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
