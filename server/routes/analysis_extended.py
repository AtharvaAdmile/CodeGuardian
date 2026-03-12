"""
Extended analysis routes — compliance, expert, history, runtime,
project-dependencies, documentation-gaps, testability, testing,
test-generation, and generated-test execution.

POST /api/analyze/compliance              → PII / secret scan
POST /api/analyze/regulatory-compliance   → FDA / ISO / IEC audit
POST /api/analyze/expert                  → code-owner lookup
POST /api/analyze/history                 → git blame history
POST /api/analyze/runtime                 → production telemetry
POST /api/analyze/project-dependencies    → full dependency graph
POST /api/analyze/documentation-gaps      → undocumented code
POST /api/analyze/testability             → testable elements
POST /api/analyze/tests                   → run pytest
POST /api/analyze/generate-test           → AI test generation
POST /api/analyze/run-test                → execute generated test
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from server.models.route_schemas import (
    ComplianceRequest,
    ComplianceResponse,
    DocumentationGapsRequest,
    DocumentationGapsResponse,
    ExpertRequest,
    ExpertResponse,
    GenerateTestRequest,
    GenerateTestResponse,
    HistoryRequest,
    HistoryResponse,
    ProjectDependenciesRequest,
    ProjectDependenciesResponse,
    RegulatoryComplianceRequest,
    RegulatoryComplianceResponse,
    RunGeneratedTestRequest,
    RunGeneratedTestResponse,
    RunTestsRequest,
    RunTestsResponse,
    RuntimeRequest,
    RuntimeResponse,
    TestabilityRequest,
    TestabilityResponse,
)

logger = logging.getLogger("codeguardian.routes.analysis_extended")

router = APIRouter(prefix="/api/analyze", tags=["analysis-extended"])


# ── Helpers ─────────────────────────────────────────────────────────────


def _validate_project(project_path: str) -> Path:
    pp = Path(project_path)
    if not pp.exists() or not pp.is_dir():
        raise HTTPException(404, f"Project path not found: {project_path}")
    return pp


def _resolve_file(project_path: str, file_path: str) -> Path:
    fp = Path(file_path)
    if not fp.is_absolute():
        fp = Path(project_path) / fp
    if not fp.exists():
        raise HTTPException(404, f"File not found: {fp}")
    if not fp.is_file():
        raise HTTPException(400, f"Path is not a file: {fp}")
    return fp


# ── Compliance ──────────────────────────────────────────────────────────


@router.post("/compliance", response_model=ComplianceResponse)
async def check_compliance(body: ComplianceRequest) -> ComplianceResponse:
    """Scan a code snippet for PII exposure, hardcoded secrets, or dangerous calls."""
    try:
        from src.analysis.compliance import ComplianceScanner

        scanner = ComplianceScanner()
        result = scanner.scan_code(body.code_snippet)

        return ComplianceResponse(
            passed=result.get("passed", True),
            violations=result.get("violations", []),
            summary=result.get("summary", ""),
        )
    except Exception as exc:
        logger.exception("Compliance scan failed")
        raise HTTPException(500, f"Compliance scan failed: {exc}") from exc


@router.post("/regulatory-compliance", response_model=RegulatoryComplianceResponse)
async def check_regulatory_compliance(
    body: RegulatoryComplianceRequest,
) -> RegulatoryComplianceResponse:
    """Evaluate code against FDA, ISO 13485, IEC 62304, HIPAA standards."""
    try:
        from src.analysis.regulatory_scanner import get_regulatory_scanner

        scanner = get_regulatory_scanner()
        result = scanner.scan_file(body.file_path, body.file_content)

        return RegulatoryComplianceResponse(
            passed=result.get("passed", False),
            score=result.get("score", 0.0),
            violations=result.get("violations", []),
            summary=result.get("summary", ""),
        )
    except Exception as exc:
        logger.exception("Regulatory compliance scan failed")
        raise HTTPException(500, f"Regulatory scan failed: {exc}") from exc


# ── Expert ──────────────────────────────────────────────────────────────


@router.post("/expert", response_model=ExpertResponse)
async def find_expert(body: ExpertRequest) -> ExpertResponse:
    """Identify code owners for a file via recency-weighted git blame."""
    pp = _validate_project(body.project_path)
    fp = _resolve_file(body.project_path, body.file_path)

    try:
        from src.analysis.expertise import ExpertiseTracker

        tracker = ExpertiseTracker(str(pp))
        result = tracker.find_owners(str(fp))

        return ExpertResponse(
            primary_expert=result.get("primary_expert"),
            backup=result.get("backup"),
            experts=result.get("experts", []),
            last_active=result.get("last_active"),
            file_path=str(fp),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Expert lookup failed")
        raise HTTPException(500, f"Expert lookup failed: {exc}") from exc


# ── History ─────────────────────────────────────────────────────────────


@router.post("/history", response_model=HistoryResponse)
async def file_history(body: HistoryRequest) -> HistoryResponse:
    """Retrieve git commit history for specific lines in a file."""
    pp = _validate_project(body.project_path)
    fp = _resolve_file(body.project_path, body.file_path)

    try:
        from src.analysis.git_context import GitContextAnalyzer

        analyzer = GitContextAnalyzer(str(pp))
        result = analyzer.get_history(str(fp), body.line_start, body.line_end)

        churn = analyzer.get_churn(str(fp))
        result["churn"] = {
            "count": churn.get("churn_count", 0),
            "risk_level": churn.get("risk_level", "unknown"),
        }

        return HistoryResponse(
            file_path=str(fp),
            history=result.get("history", []),
            summary=result.get("summary", ""),
            churn=result.get("churn", {}),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("File history lookup failed")
        raise HTTPException(500, f"History lookup failed: {exc}") from exc


# ── Runtime ─────────────────────────────────────────────────────────────


@router.post("/runtime", response_model=RuntimeResponse)
async def runtime_stats(body: RuntimeRequest) -> RuntimeResponse:
    """Get production runtime statistics for a file."""
    try:
        from src.analysis.runtime import RuntimeLoader

        loader = RuntimeLoader()
        result = loader.get_stats(body.file_path)

        return RuntimeResponse(
            file_path=body.file_path,
            available=result.get("available", False),
            error_rate=result.get("error_rate"),
            avg_latency_ms=result.get("avg_latency_ms"),
            alert_level=result.get("alert_level", "none"),
            last_error=result.get("last_error"),
        )
    except Exception as exc:
        logger.exception("Runtime stats lookup failed")
        raise HTTPException(500, f"Runtime stats failed: {exc}") from exc


# ── Project Dependencies ────────────────────────────────────────────────


@router.post("/project-dependencies", response_model=ProjectDependenciesResponse)
async def project_dependencies(
    body: ProjectDependenciesRequest,
) -> ProjectDependenciesResponse:
    """Build a full dependency graph of all files in the project."""
    pp = _validate_project(body.project_path)

    try:
        from src.documentation.dependency_analyzer import DependencyAnalyzer
        from src.models.documentation_models import CodeElement

        valid_extensions = {".py", ".js", ".ts", ".jsx", ".tsx"}
        skip_dirs = {"node_modules", "__pycache__", ".git", "venv", "dist", "build", "chroma_data"}

        nodes: list[dict] = []
        links: list[dict] = []
        node_ids: set[str] = set()

        for root, dirs, files in os.walk(pp):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in skip_dirs]
            for fname in files:
                fp = Path(root) / fname
                if fp.suffix.lower() not in valid_extensions:
                    continue
                rel_path = str(fp.relative_to(pp))
                nodes.append({
                    "id": rel_path,
                    "name": fname,
                    "group": fp.suffix.lower().replace(".", ""),
                })
                node_ids.add(rel_path)

        analyzer = DependencyAnalyzer()
        seen_links: set[str] = set()

        for node in nodes:
            file_path = pp / node["id"]
            try:
                content = file_path.read_text(encoding="utf-8")
                language = {
                    ".py": "python", ".js": "javascript", ".ts": "typescript",
                    ".jsx": "javascript", ".tsx": "typescript",
                }.get(file_path.suffix.lower(), "unknown")

                element = CodeElement(
                    element_id=node["id"],
                    element_type="file",
                    name=node["name"],
                    file_path=str(file_path),
                    start_line=1,
                    end_line=100,
                    language=language,
                    code_content=content,
                    existing_doc=None,
                )

                deps = analyzer.analyze_dependencies(element, [])
                for dep in deps:
                    if dep.dependency_type == "import":
                        for pot in nodes:
                            pot_name = pot["name"].split(".")[0]
                            if (
                                dep.name == pot_name
                                or dep.name.replace(".", "/") in pot["id"]
                            ):
                                if node["id"] != pot["id"]:
                                    key = f"{node['id']}:{pot['id']}"
                                    if key not in seen_links:
                                        seen_links.add(key)
                                        links.append({
                                            "source": node["id"],
                                            "target": pot["id"],
                                        })
                                break
            except Exception as e:
                logger.warning("Skip file %s: %s", file_path, e)

        return ProjectDependenciesResponse(
            nodes=nodes,
            links=links,
            total_files=len(nodes),
            total_links=len(links),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Project dependency analysis failed")
        raise HTTPException(500, f"Dependency analysis failed: {exc}") from exc


# ── Documentation Gaps ──────────────────────────────────────────────────


@router.post("/documentation-gaps", response_model=DocumentationGapsResponse)
async def documentation_gaps(body: DocumentationGapsRequest) -> DocumentationGapsResponse:
    """Find undocumented or poorly documented code elements in a file."""
    _validate_project(body.project_path)
    fp = _resolve_file(body.project_path, body.file_path)

    try:
        from src.code_parser import CodeParser
        from src.documentation.gap_detector import GapDetector
        from src.models.documentation_models import CodeElement

        content = fp.read_text(encoding="utf-8")
        parser = CodeParser()
        parsed = parser.parse_file(str(fp), content)

        ext = fp.suffix.lower()
        language = {".py": "python", ".js": "javascript", ".ts": "typescript"}.get(ext, "unknown")

        gap_detector = GapDetector(quality_threshold=70.0)
        elements: list[dict] = []
        gaps: list[dict] = []
        total_score = 0.0

        for func in parsed.functions:
            element = CodeElement(
                element_id=f"{fp}:{func.name}:{func.start_line}",
                element_type="function",
                name=func.name,
                file_path=str(fp),
                start_line=func.start_line,
                end_line=func.end_line,
                language=language,
                code_content=func.content,
                existing_doc=func.docstring,
            )
            score = gap_detector.calculate_quality_score(element)
            has_gap = gap_detector.has_documentation_gap(score)
            info = {
                "name": func.name,
                "type": "function",
                "start_line": func.start_line,
                "end_line": func.end_line,
                "quality_score": score,
                "has_gap": has_gap,
                "has_docstring": bool(func.docstring),
            }
            elements.append(info)
            total_score += score
            if has_gap:
                gaps.append(info)

        for cls in parsed.classes:
            element = CodeElement(
                element_id=f"{fp}:{cls.name}:{cls.start_line}",
                element_type="class",
                name=cls.name,
                file_path=str(fp),
                start_line=cls.start_line,
                end_line=cls.end_line,
                language=language,
                code_content=cls.content,
                existing_doc=cls.docstring,
            )
            score = gap_detector.calculate_quality_score(element)
            has_gap = gap_detector.has_documentation_gap(score)
            info = {
                "name": cls.name,
                "type": "class",
                "start_line": cls.start_line,
                "end_line": cls.end_line,
                "quality_score": score,
                "has_gap": has_gap,
                "has_docstring": bool(cls.docstring),
            }
            elements.append(info)
            total_score += score
            if has_gap:
                gaps.append(info)

        avg_score = total_score / len(elements) if elements else 100.0

        return DocumentationGapsResponse(
            file_path=str(fp),
            elements=elements,
            gaps=gaps,
            total_elements=len(elements),
            elements_with_gaps=len(gaps),
            average_score=round(avg_score, 1),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Documentation gap detection failed")
        raise HTTPException(500, f"Gap detection failed: {exc}") from exc


# ── Testability ─────────────────────────────────────────────────────────


@router.post("/testability", response_model=TestabilityResponse)
async def analyze_testability(body: TestabilityRequest) -> TestabilityResponse:
    """Identify testable functions/classes and their complexity."""
    _validate_project(body.project_path)
    fp = _resolve_file(body.project_path, body.file_path)

    try:
        from src.testing.test_analyzer import TestAnalyzer

        content = fp.read_text(encoding="utf-8")
        analyzer = TestAnalyzer()
        testable = analyzer.analyze_file(str(fp), content)

        elements_out = []
        for el in testable:
            elements_out.append({
                "element_id": el.element_id,
                "name": el.name,
                "element_type": el.element_type,
                "file_path": el.file_path,
                "start_line": el.start_line,
                "end_line": el.end_line,
                "content": el.content,
                "complexity_score": el.complexity_score,
            })

        return TestabilityResponse(
            file_path=str(fp),
            testable_elements=elements_out,
            total_elements=len(elements_out),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Testability analysis failed")
        raise HTTPException(500, f"Testability analysis failed: {exc}") from exc


# ── Run Tests ───────────────────────────────────────────────────────────


@router.post("/tests", response_model=RunTestsResponse)
async def run_tests(body: RunTestsRequest) -> RunTestsResponse:
    """Execute pytest on a specific file or directory."""
    pp = _validate_project(body.project_path)

    try:
        from src.testing.test_runner import TestRunner

        runner = TestRunner()

        if body.file_path:
            fp = _resolve_file(body.project_path, body.file_path)
            result = runner.run_file(str(fp))
            return RunTestsResponse(
                passed=result.passed,
                output=result.output or "",
                results={
                    str(fp): {
                        "passed": result.passed,
                        "output": result.output,
                    }
                },
            )
        else:
            test_path = pp / body.test_dir
            results = runner.run_all(str(test_path))
            all_passed = all(r.passed for r in results.values()) if results else True
            return RunTestsResponse(
                passed=all_passed,
                results={
                    p: {
                        "passed": r.passed,
                        "output": (r.output or "")[:500],
                        "error": r.error_message,
                    }
                    for p, r in results.items()
                },
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Test execution failed")
        raise HTTPException(500, f"Test execution failed: {exc}") from exc


# ── Generate Test ───────────────────────────────────────────────────────


@router.post("/generate-test", response_model=GenerateTestResponse)
async def generate_test(body: GenerateTestRequest) -> GenerateTestResponse:
    """Generate a unit test for a source file using AI."""
    try:
        from src.testing.test_generator import TestGenerator

        generator = TestGenerator()
        result = generator.generate_test(body.file_path, body.file_content)

        return GenerateTestResponse(
            test_code=result.get("test_code"),
            language=result.get("language", "unknown"),
            framework=result.get("framework", ""),
            suggested_test_path=result.get("suggested_test_path", ""),
            success=result.get("success", False),
        )
    except Exception as exc:
        logger.exception("Test generation failed")
        raise HTTPException(500, f"Test generation failed: {exc}") from exc


# ── Run Generated Test ──────────────────────────────────────────────────


@router.post("/run-test", response_model=RunGeneratedTestResponse)
async def run_generated_test(body: RunGeneratedTestRequest) -> RunGeneratedTestResponse:
    """Execute a previously generated test file."""
    pp = _validate_project(body.project_path)

    try:
        from src.testing.test_runner import TestRunner

        runner = TestRunner(project_root=str(pp))
        result = runner.run_generated_test(body.test_file_path)

        return RunGeneratedTestResponse(
            passed=result.passed,
            file_path=result.file_path or "",
            output=result.output or "",
            error_message=result.error_message,
        )
    except Exception as exc:
        logger.exception("Generated test execution failed")
        raise HTTPException(500, f"Generated test execution failed: {exc}") from exc
