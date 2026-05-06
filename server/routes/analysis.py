"""
Analysis routes — structure scoring, file health, and dependency parsing.

POST /api/analyze/structure      → project organisation score
POST /api/analyze/health         → complexity + churn health metrics
POST /api/analyze/dependencies   → import / call-graph analysis
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from server.models.route_schemas import (
    DependencyRequest,
    DependencyResponse,
    HealthRequest,
    HealthResponse,
    StructureRequest,
    StructureResponse,
)

logger = logging.getLogger("codeguardian.routes.analysis")

router = APIRouter(prefix="/api/analyze", tags=["analysis"])

# Indexed file extensions (same as CLAUDE.md)
_VALID_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx"}
_SKIP_DIRS = {"node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build", "chroma_data"}


# ── Helpers ─────────────────────────────────────────────────────────────


def _resolve_file(project_path: str, file_path: str) -> Path:
    """Resolve *file_path* against *project_path* and validate it exists."""
    fp = Path(file_path)
    if not fp.is_absolute():
        fp = Path(project_path) / fp

    if not fp.exists():
        raise HTTPException(404, f"File not found: {fp}")
    if not fp.is_file():
        raise HTTPException(400, f"Path is not a file: {fp}")

    return fp


def _validate_project(project_path: str) -> Path:
    """Ensure the project directory exists."""
    pp = Path(project_path)
    if not pp.exists() or not pp.is_dir():
        raise HTTPException(404, f"Project path not found: {project_path}")
    return pp


# ── Endpoints ───────────────────────────────────────────────────────────


@router.post("/structure", response_model=StructureResponse)
async def analyze_structure(body: StructureRequest) -> StructureResponse:
    """
    Walk the project directory, count files by type, check for git, and
    return an organisation score (0-10).
    """
    pp = _validate_project(body.project_path)

    try:
        total_files = 0
        root_files = 0
        folders: set[str] = set()
        has_git = (pp / ".git").is_dir()

        for dirpath, dirnames, filenames in os.walk(pp):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
            rel = os.path.relpath(dirpath, pp)
            if rel != ".":
                folders.add(rel)
            for fname in filenames:
                ext = Path(fname).suffix.lower()
                if ext in _VALID_EXTENSIONS:
                    total_files += 1
                    if rel == ".":
                        root_files += 1

        folders_count = len(folders)

        # Simple organisation score heuristic (0-10):
        # Penalise if too many files are in root (should be in subdirs).
        # Reward having git, having subdirectories, and having a reasonable structure.
        score = 5.0
        if has_git:
            score += 1.5
        if folders_count >= 3:
            score += 1.5
        elif folders_count >= 1:
            score += 0.5
        if total_files > 0:
            root_ratio = root_files / total_files
            if root_ratio < 0.3:
                score += 2.0  # well organised
            elif root_ratio < 0.6:
                score += 1.0
            else:
                score -= 1.0  # too flat
        score = max(0.0, min(10.0, score))

        return StructureResponse(
            project_path=str(pp),
            score=round(score, 1),
            has_git=has_git,
            total_files=total_files,
            root_files=root_files,
            folders_count=folders_count,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error analysing structure")
        raise HTTPException(500, f"Structure analysis failed: {exc}") from exc


@router.post("/health", response_model=HealthResponse)
async def analyze_health(body: HealthRequest) -> HealthResponse:
    """
    Compute file-level health score combining radon cyclomatic complexity
    and git churn.
    """
    _validate_project(body.project_path)
    fp = _resolve_file(body.project_path, body.file_path)

    try:
        content = fp.read_text(encoding="utf-8")
        complexity_data: dict = {}
        churn_data: dict = {}

        # ── Cyclomatic complexity via radon ──────────────────────────
        if fp.suffix.lower() == ".py":
            try:
                import radon.complexity as radon_cc

                blocks = radon_cc.cc_visit(content)
                if blocks:
                    avg_cc = sum(b.complexity for b in blocks) / len(blocks)
                    max_cc = max(b.complexity for b in blocks)
                    complexity_data = {
                        "average": round(avg_cc, 2),
                        "max": max_cc,
                        "functions_analyzed": len(blocks),
                        "details": [
                            {"name": b.name, "complexity": b.complexity, "rank": b.letter}
                            for b in sorted(blocks, key=lambda x: -x.complexity)[:10]
                        ],
                    }
            except Exception as exc:
                logger.debug("Radon complexity failed: %s", exc)

        # ── Git churn ────────────────────────────────────────────────
        churn_error: str | None = None
        try:
            from server.services.git_service import GitService

            git_svc = GitService(body.project_path)
            rel_path = str(fp.relative_to(Path(body.project_path).resolve()))
            history = await asyncio.to_thread(git_svc.get_file_history, rel_path, 50)
            churn_data = {
                "total_commits": len(history),
                "recent_commits": len(history[:20]),
            }
            if history:
                churn_data["last_modified"] = history[0].date.isoformat()
                authors = {c.author for c in history}
                churn_data["unique_authors"] = len(authors)
        except Exception as exc:
            logger.warning("Git churn lookup failed for %s: %s", fp, exc)
            churn_error = str(exc)
            churn_data = {"error": churn_error, "total_commits": 0, "recent_commits": 0}

        # ── Health score ─────────────────────────────────────────────
        health_score = 10.0
        avg_cc = complexity_data.get("average", 0)
        if avg_cc > 15:
            health_score -= 4.0
        elif avg_cc > 10:
            health_score -= 2.5
        elif avg_cc > 5:
            health_score -= 1.0

        total_commits = churn_data.get("total_commits", 0)
        if total_commits > 100:
            health_score -= 2.0
        elif total_commits > 50:
            health_score -= 1.0

        health_score = max(0.0, min(10.0, health_score))
        is_hotspot = avg_cc > 10 and total_commits > 30

        recommendation: dict = {}
        if avg_cc > 10:
            recommendation["complexity"] = "Consider breaking down complex functions."
        if total_commits > 50:
            recommendation["churn"] = "High churn file — review for stability."

        return HealthResponse(
            file_path=str(fp),
            health_score=round(health_score, 1),
            complexity=complexity_data,
            churn=churn_data,
            recommendation=recommendation,
            is_hotspot=is_hotspot,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error analysing file health")
        raise HTTPException(500, f"Health analysis failed: {exc}") from exc


@router.post("/dependencies", response_model=DependencyResponse)
async def analyze_dependencies(body: DependencyRequest) -> DependencyResponse:
    """
    Parse imports using the existing DependencyAnalyzer (AST for Python,
    regex for JS/TS) and return the dependency list for the given file.
    """
    _validate_project(body.project_path)
    fp = _resolve_file(body.project_path, body.file_path)

    try:
        ext = fp.suffix.lower()
        language = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
        }.get(ext, "unknown")

        rel_path = str(fp.relative_to(Path(body.project_path).resolve()))

        from server.services.impact_engine import DependencyAnalyzer

        analyzer = DependencyAnalyzer()
        content = fp.read_text(encoding="utf-8")
        records = analyzer.extract_imports(content, rel_path)

        imports = [r.raw_specifier for r in records]

        return DependencyResponse(
            file_path=str(fp),
            language=language,
            imports=imports,
            function_calls=[],
            inheritance=[],
            total_dependencies=len(records),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error analysing dependencies")
        raise HTTPException(500, f"Dependency analysis failed: {exc}") from exc
