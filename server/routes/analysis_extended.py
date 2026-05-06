"""
Extended analysis routes — compliance, expert, history, runtime,
project-dependencies, documentation-gaps, testability, testing,
test-generation, and generated-test execution.

POST /api/analyze/compliance              → PII / secret scan
POST /api/analyze/regulatory-compliance   → FDA / ISO / IEC audit (stub)
POST /api/analyze/expert                  → code-owner lookup
POST /api/analyze/history                 → git blame history
POST /api/analyze/runtime                 → production telemetry (stub)
POST /api/analyze/project-dependencies    → full dependency graph
POST /api/analyze/documentation-gaps      → undocumented code
POST /api/analyze/testability             → testable elements
POST /api/analyze/tests                   → run pytest
POST /api/analyze/generate-test           → AI test generation
POST /api/analyze/run-test                → execute generated test
"""

from __future__ import annotations

import ast as stdlib_ast
import asyncio
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

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

_VALID_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx"}
_SKIP_DIRS = {"node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build", "chroma_data"}


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


# ── Compliance patterns ────────────────────────────────────────────────

_COMPLIANCE_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (
        re.compile(
            r'(?:api[_\-]?key|apikey|secret[_\-]?key|access[_\-]?token|'
            r'auth[_\-]?token|private[_\-]?key)\s*=\s*["\'][\w\-\/\+\.]{10,}["\']',
            re.IGNORECASE,
        ),
        "Hardcoded API key or secret detected",
        "secret",
    ),
    (
        re.compile(
            r'(?:password|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']',
            re.IGNORECASE,
        ),
        "Hardcoded password detected",
        "secret",
    ),
    (
        re.compile(r'(?i)bearer\s+[a-zA-Z0-9\-._~+\/]{20,}'),
        "Hardcoded bearer token detected",
        "secret",
    ),
    (
        re.compile(
            r'(?:log(?:ger)?\.(?:info|debug|warning|error|critical)|print)\s*'
            r'\([^)]*(?:email|phone|ssn|social[_\s]security|credit[_\s]card)',
            re.IGNORECASE,
        ),
        "PII exposure: sensitive field logged or printed",
        "pii",
    ),
    (
        re.compile(r'\beval\s*\(', re.IGNORECASE),
        "Use of eval() is a code injection risk",
        "dangerous_call",
    ),
    (
        re.compile(
            r'(?:execute|cursor\.execute|query)\s*\(\s*f["\']',
            re.IGNORECASE,
        ),
        "SQL injection risk: f-string used in query",
        "sql_injection",
    ),
]


# ── Compliance ──────────────────────────────────────────────────────────


@router.post("/compliance", response_model=ComplianceResponse)
async def check_compliance(body: ComplianceRequest) -> ComplianceResponse:
    """Scan a code snippet for PII exposure, hardcoded secrets, or dangerous calls."""
    try:
        violations: list[dict] = []
        lines = body.code_snippet.splitlines()

        for pattern, message, category in _COMPLIANCE_PATTERNS:
            for m in pattern.finditer(body.code_snippet):
                line_num = body.code_snippet[: m.start()].count("\n") + 1
                violations.append({
                    "line": line_num,
                    "message": message,
                    "category": category,
                    "matched_text": m.group(0)[:80],
                })

        passed = len(violations) == 0
        summary = (
            "No compliance issues found."
            if passed
            else f"Found {len(violations)} compliance violation(s)."
        )

        return ComplianceResponse(
            passed=passed,
            violations=violations,
            summary=summary,
        )
    except Exception as exc:
        logger.exception("Compliance scan failed")
        raise HTTPException(500, f"Compliance scan failed: {exc}") from exc


@router.post("/regulatory-compliance", response_model=RegulatoryComplianceResponse)
async def check_regulatory_compliance(
    body: RegulatoryComplianceRequest,
) -> RegulatoryComplianceResponse:
    """Evaluate code against regulatory standards. Not yet implemented."""
    return RegulatoryComplianceResponse(
        passed=False,
        score=0.0,
        violations=[],
        summary="Regulatory compliance scanning is not yet implemented.",
    )


# ── Expert ──────────────────────────────────────────────────────────────


@router.post("/expert", response_model=ExpertResponse)
async def find_expert(body: ExpertRequest) -> ExpertResponse:
    """Identify code owners for a file via git blame expertise mapping."""
    pp = _validate_project(body.project_path)
    fp = _resolve_file(body.project_path, body.file_path)

    try:
        from server.services.git_service import GitService

        git_svc = GitService(str(pp))
        rel_path = str(fp.relative_to(pp.resolve()))
        expertise_map = await asyncio.to_thread(
            git_svc.build_expertise_map, [rel_path]
        )

        entries = expertise_map.get(rel_path, [])
        experts_out: list[dict] = []
        for entry in entries:
            experts_out.append({
                "name": entry.author,
                "email": entry.email,
                "commit_count": entry.commit_count,
                "last_active": entry.last_active.isoformat(),
            })

        primary = experts_out[0]["name"] if experts_out else None
        backup = experts_out[1]["name"] if len(experts_out) > 1 else None
        last_active = experts_out[0]["last_active"] if experts_out else None

        return ExpertResponse(
            primary_expert=primary,
            backup=backup,
            experts=experts_out,
            last_active=last_active,
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
    """Retrieve git commit history and blame for a file."""
    pp = _validate_project(body.project_path)
    fp = _resolve_file(body.project_path, body.file_path)

    try:
        from server.services.git_service import GitService

        git_svc = GitService(str(pp))
        rel_path = str(fp.relative_to(pp.resolve()))

        # Get commit history
        commits = await asyncio.to_thread(git_svc.get_file_history, rel_path, 20)
        history_out: list[dict] = []
        for c in commits:
            history_out.append({
                "sha": c.sha,
                "author": c.author,
                "email": c.email,
                "message": c.message,
                "date": c.date.isoformat(),
            })

        # Get blame data for churn analysis
        blame_entries = await asyncio.to_thread(git_svc.get_file_blame, rel_path)
        churn_data: dict = {
            "count": len(commits),
            "risk_level": (
                "high" if len(commits) > 30
                else "medium" if len(commits) > 10
                else "low"
            ),
        }

        summary = (
            f"File has {len(commits)} commits from "
            f"{len({c.author for c in commits})} author(s)."
            if commits
            else "No commit history found."
        )

        return HistoryResponse(
            file_path=str(fp),
            history=history_out,
            summary=summary,
            churn=churn_data,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("File history lookup failed")
        raise HTTPException(500, f"History lookup failed: {exc}") from exc


# ── Runtime ─────────────────────────────────────────────────────────────


@router.post("/runtime", response_model=RuntimeResponse)
async def runtime_stats(body: RuntimeRequest) -> RuntimeResponse:
    """Get production runtime statistics. No runtime telemetry is available."""
    return RuntimeResponse(
        file_path=body.file_path,
        available=False,
        alert_level="none",
    )


# ── Project Dependencies ────────────────────────────────────────────────


@router.post("/project-dependencies", response_model=ProjectDependenciesResponse)
async def project_dependencies(
    body: ProjectDependenciesRequest,
) -> ProjectDependenciesResponse:
    """Build a full dependency graph of all files in the project."""
    pp = _validate_project(body.project_path)

    try:
        from server.services.impact_engine import build_dependency_graph

        graph = await asyncio.to_thread(build_dependency_graph, str(pp))

        nodes: list[dict] = []
        for node_id in graph.nodes:
            name = Path(node_id).name
            ext = Path(node_id).suffix.lower().replace(".", "")
            nodes.append({
                "id": node_id,
                "name": name,
                "group": ext,
            })

        links: list[dict] = []
        for src, dst in graph.edges:
            links.append({"source": src, "target": dst})

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
        content = fp.read_text(encoding="utf-8")
        ext = fp.suffix.lower()
        elements: list[dict] = []
        gaps: list[dict] = []

        if ext == ".py":
            # Use stdlib ast to find functions/classes and check docstrings
            try:
                tree = stdlib_ast.parse(content)
            except SyntaxError:
                return DocumentationGapsResponse(
                    file_path=str(fp),
                    error="Could not parse Python file (syntax error).",
                )

            for node in stdlib_ast.walk(tree):
                if isinstance(node, (stdlib_ast.FunctionDef, stdlib_ast.AsyncFunctionDef)):
                    docstring = stdlib_ast.get_docstring(node)
                    has_doc = bool(docstring)
                    # Quality: 100 if docstring exists & > 20 chars, else 0
                    quality = 100.0 if has_doc and len(docstring) > 20 else (50.0 if has_doc else 0.0)
                    info = {
                        "name": node.name,
                        "type": "function",
                        "start_line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno),
                        "quality_score": quality,
                        "has_gap": quality < 70.0,
                        "has_docstring": has_doc,
                    }
                    elements.append(info)
                    if info["has_gap"]:
                        gaps.append(info)

                elif isinstance(node, stdlib_ast.ClassDef):
                    docstring = stdlib_ast.get_docstring(node)
                    has_doc = bool(docstring)
                    quality = 100.0 if has_doc and len(docstring) > 20 else (50.0 if has_doc else 0.0)
                    info = {
                        "name": node.name,
                        "type": "class",
                        "start_line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno),
                        "quality_score": quality,
                        "has_gap": quality < 70.0,
                        "has_docstring": has_doc,
                    }
                    elements.append(info)
                    if info["has_gap"]:
                        gaps.append(info)

        elif ext in {".js", ".ts", ".jsx", ".tsx"}:
            # Regex-based: find function/class declarations and check for JSDoc
            func_re = re.compile(
                r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)|"
                r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\s*\(|"
                r"(?:export\s+)?(?:default\s+)?class\s+(\w+)",
                re.MULTILINE,
            )
            lines = content.splitlines()
            for m in func_re.finditer(content):
                name = m.group(1) or m.group(2) or m.group(3)
                line_num = content[: m.start()].count("\n") + 1
                # Check for JSDoc comment above
                has_doc = False
                if line_num > 1:
                    prev_line = lines[line_num - 2].strip() if line_num - 1 < len(lines) else ""
                    has_doc = prev_line.endswith("*/")
                quality = 100.0 if has_doc else 0.0
                info = {
                    "name": name,
                    "type": "function",
                    "start_line": line_num,
                    "end_line": min(line_num + 20, len(lines)),
                    "quality_score": quality,
                    "has_gap": quality < 70.0,
                    "has_docstring": has_doc,
                }
                elements.append(info)
                if info["has_gap"]:
                    gaps.append(info)

        avg_score = (
            sum(e["quality_score"] for e in elements) / len(elements)
            if elements
            else 100.0
        )

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
        content = fp.read_text(encoding="utf-8")
        elements_out: list[dict] = []

        if fp.suffix.lower() == ".py":
            try:
                tree = stdlib_ast.parse(content)
            except SyntaxError:
                return TestabilityResponse(file_path=str(fp), error="Syntax error in file.")

            lines = content.splitlines()

            # Get complexity per function via radon if available
            complexity_map: dict[str, int] = {}
            try:
                import radon.complexity as radon_cc
                blocks = radon_cc.cc_visit(content)
                for b in blocks:
                    complexity_map[b.name] = b.complexity
            except Exception:
                pass

            for node in stdlib_ast.walk(tree):
                if isinstance(node, (stdlib_ast.FunctionDef, stdlib_ast.AsyncFunctionDef)):
                    end_line = getattr(node, "end_lineno", node.lineno + 10)
                    func_content = "\n".join(lines[node.lineno - 1 : end_line])
                    elements_out.append({
                        "element_id": f"{fp}:{node.name}:{node.lineno}",
                        "name": node.name,
                        "element_type": "function",
                        "file_path": str(fp),
                        "start_line": node.lineno,
                        "end_line": end_line,
                        "content": func_content[:500],
                        "complexity_score": complexity_map.get(node.name, 1),
                    })
        else:
            # JS/TS — regex extraction
            func_re = re.compile(
                r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)|"
                r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\s*\(",
                re.MULTILINE,
            )
            lines = content.splitlines()
            for m in func_re.finditer(content):
                name = m.group(1) or m.group(2)
                line_num = content[: m.start()].count("\n") + 1
                end_line = min(line_num + 30, len(lines))
                func_content = "\n".join(lines[line_num - 1 : end_line])
                elements_out.append({
                    "element_id": f"{fp}:{name}:{line_num}",
                    "name": name,
                    "element_type": "function",
                    "file_path": str(fp),
                    "start_line": line_num,
                    "end_line": end_line,
                    "content": func_content[:500],
                    "complexity_score": 1,
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
        if body.file_path:
            fp = _resolve_file(body.project_path, body.file_path)
            target = str(fp)
        else:
            target = str(pp / body.test_dir)

        result = await asyncio.to_thread(
            subprocess.run,
            ["python", "-m", "pytest", target, "-v", "--tb=short", "--no-header"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(pp),
        )

        passed = result.returncode == 0
        output = (result.stdout + "\n" + result.stderr).strip()

        return RunTestsResponse(
            passed=passed,
            output=output[:5000],
            results={
                target: {
                    "passed": passed,
                    "output": output[:2000],
                }
            },
        )
    except subprocess.TimeoutExpired:
        return RunTestsResponse(
            passed=False,
            output="Test execution timed out after 120 seconds.",
            error="timeout",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Test execution failed")
        raise HTTPException(500, f"Test execution failed: {exc}") from exc


# ── Generate Test ───────────────────────────────────────────────────────


@router.post("/generate-test", response_model=GenerateTestResponse)
async def generate_test(body: GenerateTestRequest, request: Request) -> GenerateTestResponse:
    """Generate a unit test for a source file using AI."""
    try:
        llm_client = getattr(request.app.state, "llm_client", None)
        if llm_client is None:
            return GenerateTestResponse(
                success=False,
                error="LLM client is not initialised. Cannot generate tests.",
            )

        ext = Path(body.file_path).suffix.lower()
        language = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".jsx": "javascript", ".tsx": "typescript",
        }.get(ext, "unknown")

        framework = "pytest" if language == "python" else "jest"

        # Truncate content to avoid token limits
        content_truncated = body.file_content[:4000]

        messages = [
            {
                "role": "system",
                "content": (
                    f"You are a test-generation assistant. Write a comprehensive "
                    f"unit test file using {framework} for the provided source code. "
                    f"Language: {language}. Output ONLY the test code — no prose."
                ),
            },
            {
                "role": "user",
                "content": f"File: {body.file_path}\n\n```\n{content_truncated}\n```",
            },
        ]

        response = await llm_client.complete(messages=messages, stream=False)
        test_code = response.content.strip()

        # Strip markdown code fences if present
        if test_code.startswith("```"):
            lines = test_code.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            test_code = "\n".join(lines)

        # Suggest test path
        src_path = Path(body.file_path)
        if language == "python":
            suggested = f"tests/test_{src_path.stem}.py"
        else:
            suggested = f"__tests__/{src_path.stem}.test{ext}"

        return GenerateTestResponse(
            test_code=test_code,
            language=language,
            framework=framework,
            suggested_test_path=suggested,
            success=True,
        )
    except Exception as exc:
        logger.exception("Test generation failed")
        raise HTTPException(500, f"Test generation failed: {exc}") from exc


# ── Run Generated Test ──────────────────────────────────────────────────


@router.post("/run-test", response_model=RunGeneratedTestResponse)
async def run_generated_test(body: RunGeneratedTestRequest) -> RunGeneratedTestResponse:
    """Execute a previously generated test file."""
    pp = _validate_project(body.project_path)
    test_fp = Path(body.test_file_path)
    if not test_fp.is_absolute():
        test_fp = pp / test_fp

    if not test_fp.exists():
        return RunGeneratedTestResponse(
            passed=False,
            file_path=str(test_fp),
            error_message=f"Test file not found: {test_fp}",
        )

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["python", "-m", "pytest", str(test_fp), "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(pp),
        )

        return RunGeneratedTestResponse(
            passed=result.returncode == 0,
            file_path=str(test_fp),
            output=(result.stdout + "\n" + result.stderr).strip()[:5000],
            error_message=None if result.returncode == 0 else "Tests failed.",
        )
    except subprocess.TimeoutExpired:
        return RunGeneratedTestResponse(
            passed=False,
            file_path=str(test_fp),
            output="Test execution timed out after 120 seconds.",
            error_message="timeout",
        )
    except Exception as exc:
        logger.exception("Generated test execution failed")
        raise HTTPException(500, f"Generated test execution failed: {exc}") from exc
