"""
Analysis routes — structure scoring, file health, and dependency parsing.

POST /api/analyze/structure      → project organisation score
POST /api/analyze/health         → complexity + churn health metrics
POST /api/analyze/dependencies   → import / call-graph analysis
"""

from __future__ import annotations

import logging
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

    Uses ``src.structure_analyzer.StructureAnalyzer``.
    """
    pp = _validate_project(body.project_path)

    try:
        from src.structure_analyzer import StructureAnalyzer

        analyzer = StructureAnalyzer(str(pp))
        result = analyzer.analyze_structure()

        return StructureResponse(
            project_path=str(pp),
            score=result.get("score", 0.0),
            has_git=result.get("has_git", False),
            total_files=result.get("total_files", 0),
            root_files=result.get("root_files", 0),
            folders_count=result.get("folders_count", 0),
            error=result.get("error"),
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

    Uses ``src.structure_analyzer.StructureAnalyzer.get_file_health()``.
    """
    _validate_project(body.project_path)
    fp = _resolve_file(body.project_path, body.file_path)

    try:
        from src.structure_analyzer import StructureAnalyzer

        analyzer = StructureAnalyzer(body.project_path)
        result = analyzer.get_file_health(str(fp))

        return HealthResponse(
            file_path=str(fp),
            health_score=result.get("health_score", 0.0),
            complexity=result.get("complexity", {}),
            churn=result.get("churn", {}),
            recommendation=result.get("recommendation", {}),
            is_hotspot=result.get("is_hotspot", False),
            error=result.get("error"),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error analysing file health")
        raise HTTPException(500, f"Health analysis failed: {exc}") from exc


@router.post("/dependencies", response_model=DependencyResponse)
async def analyze_dependencies(body: DependencyRequest) -> DependencyResponse:
    """
    Parse imports using AST (Python) or regex (JS/TS) and return
    the dependency list for the given file.

    Uses ``src.code_parser.CodeParser`` and
    ``src.documentation.dependency_analyzer.DependencyAnalyzer``.
    """
    _validate_project(body.project_path)
    fp = _resolve_file(body.project_path, body.file_path)

    try:
        content = fp.read_text(encoding="utf-8")

        ext = fp.suffix.lower()
        language = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
        }.get(ext, "unknown")

        from src.documentation.dependency_analyzer import DependencyAnalyzer
        from src.models.documentation_models import CodeElement

        element = CodeElement(
            element_id=str(fp),
            element_type="file",
            name=fp.name,
            file_path=str(fp),
            start_line=1,
            end_line=len(content.splitlines()),
            language=language,
            code_content=content,
            existing_doc=None,
        )

        analyzer = DependencyAnalyzer()
        deps = analyzer.analyze_dependencies(element, [])

        imports = [d.name for d in deps if d.dependency_type == "import"]
        calls = [d.name for d in deps if d.dependency_type == "function_call"]
        inheritance = [d.name for d in deps if d.dependency_type == "inheritance"]

        return DependencyResponse(
            file_path=str(fp),
            language=language,
            imports=imports,
            function_calls=calls,
            inheritance=inheritance,
            total_dependencies=len(deps),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error analysing dependencies")
        raise HTTPException(500, f"Dependency analysis failed: {exc}") from exc
