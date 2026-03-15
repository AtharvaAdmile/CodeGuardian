"""
Code Review Assistant — multi-node LangGraph pipeline.

Graph topology (linear):
    parse_input → pattern_check → impact_analysis → security_scan → synthesize → END

Modes
-----
Snippet mode : ``input_code`` is set; ``file_path``/``diff`` are None.
PR mode      : ``file_path`` + ``diff`` are set; ``input_code`` may hold the
               raw diff text or be empty.
"""

from __future__ import annotations

import ast as stdlib_ast
import asyncio
import json
import logging
import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

logger = logging.getLogger("codeguardian.agents.review")

# ── Severity ordering (lower index = higher priority) ────────────────────
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# ── Strip <think> tags (defensive) ──────────────────────────────────────
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

# ─────────────────────────────────────────────────────────────────────────
# Security scan patterns
# ─────────────────────────────────────────────────────────────────────────

_SECRET_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (
        re.compile(
            r'(?:api[_\-]?key|apikey|secret[_\-]?key|access[_\-]?token|'
            r'auth[_\-]?token|private[_\-]?key)\s*=\s*["\'][\w\-\/\+\.]{10,}["\']',
            re.IGNORECASE,
        ),
        "Hardcoded API key / secret",
        "critical",
    ),
    (
        re.compile(
            r'(?:password|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']',
            re.IGNORECASE,
        ),
        "Hardcoded password",
        "critical",
    ),
    (
        re.compile(r'(?i)bearer\s+[a-zA-Z0-9\-._~+\/]{20,}'),
        "Hardcoded bearer token",
        "high",
    ),
]

_SQL_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            # Matches execute/query call where the first arg contains % interpolation
            r'(?:execute|cursor\.execute|query)\s*\(.*?%\s*\w',
            re.IGNORECASE | re.DOTALL,
        ),
        "SQL injection risk: % string interpolation in query (use parameterised queries)",
    ),
    (
        re.compile(
            r'(?:execute|cursor\.execute|query)\s*\(\s*f["\']',
            re.IGNORECASE,
        ),
        "SQL injection risk: f-string used to build query string",
    ),
    (
        re.compile(
            r'(?:execute|cursor\.execute|query)\s*\(.*?\.format\s*\(',
            re.IGNORECASE | re.DOTALL,
        ),
        "SQL injection risk: .format() used to build query string",
    ),
]

_PATH_TRAVERSAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r'open\s*\(\s*(?:request\b|body\b|params\b|args\b|data\b|user_input)',
            re.IGNORECASE,
        ),
        "Path traversal risk: user-controlled value passed directly to open()",
    ),
    (
        re.compile(
            r'os\.path\.(?:join|abspath)\s*\([^)]*(?:request\b|params\b|user_input)',
            re.IGNORECASE,
        ),
        "Path traversal risk: user-controlled value in os.path operation",
    ),
]

_PII_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r'(?:log(?:ger)?\.(?:info|debug|warning|error|critical)|print)\s*'
            r'\([^)]*(?:email|phone|ssn|social[_\s]security|credit[_\s]card)',
            re.IGNORECASE,
        ),
        "PII exposure: sensitive field logged or printed",
    ),
    (
        re.compile(
            r'(?:log(?:ger)?\.(?:info|debug|warning|error|critical))\s*'
            r'\([^)]*\b(?:password|passwd|token|secret)\b',
            re.IGNORECASE,
        ),
        "PII exposure: credential-like value in log call",
    ),
]

# Async function that contains await but no try/except block
_ASYNC_DEF_RE = re.compile(r"async\s+def\s+(\w+)")
_TRY_RE = re.compile(r"\btry\s*:")
_AWAIT_RE = re.compile(r"\bawait\s+")

# JS / TS function name patterns
_JS_FUNC_RE = re.compile(
    r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*\(|"
    r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\s*\(|"
    r"(?:export\s+)?(?:default\s+)?class\s+(\w+)",
    re.MULTILINE,
)

# Python function/class definition
_PY_DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)|^\s*class\s+(\w+)", re.MULTILINE)

# Unified diff file header
_DIFF_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)
_DIFF_HUNK_RE = re.compile(r"^@@ .+\+(\d+)(?:,\d+)? @@", re.MULTILINE)


# ─────────────────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────────────────

class ReviewState(TypedDict):
    project_id: str
    project_path: str              # needed for blast radius; may be ""
    input_code: str                # snippet OR raw diff text
    file_path: str | None          # PR mode: file being reviewed
    diff: str | None               # PR mode: unified diff
    changed_functions: list        # [{name, code, start_line, file_path, language}]
    pattern_findings: list         # [{severity, category, message, file_path, line, suggestion, confidence}]
    impact_report: dict            # blast radius data; {} if unavailable
    security_findings: list        # same structure as pattern_findings
    final_review: dict             # {summary, findings, severity_counts}
    error: str | None


# ─────────────────────────────────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────────────────────────────────

def _detect_language(file_path: str | None, code: str) -> str:
    if file_path:
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        if ext == "py":
            return "python"
        if ext in {"js", "jsx", "ts", "tsx", "mjs", "cjs"}:
            return "javascript"
    # Heuristic: Python has `def ` and `import`
    if "def " in code or "import " in code:
        return "python"
    return "javascript"


def _extract_python_functions(code: str, file_path: str) -> list[dict]:
    """Extract top-level and nested function/class defs from Python code."""
    functions: list[dict] = []
    try:
        tree = stdlib_ast.parse(code)
    except SyntaxError:
        # Fallback: regex
        lines = code.splitlines()
        for m in _PY_DEF_RE.finditer(code):
            name = m.group(1) or m.group(2)
            lineno = code[: m.start()].count("\n") + 1
            end = min(lineno + 30, len(lines))
            functions.append({
                "name": name,
                "code": "\n".join(lines[lineno - 1: end]),
                "start_line": lineno,
                "file_path": file_path,
                "language": "python",
            })
        return functions

    lines = code.splitlines()
    for node in stdlib_ast.walk(tree):
        if isinstance(node, (stdlib_ast.FunctionDef, stdlib_ast.AsyncFunctionDef, stdlib_ast.ClassDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start + 20)
            body = "\n".join(lines[start - 1: end])
            functions.append({
                "name": node.name,
                "code": body,
                "start_line": start,
                "file_path": file_path,
                "language": "python",
            })
    return functions


def _extract_js_functions(code: str, file_path: str) -> list[dict]:
    """Extract function/class names from JS/TS using regex."""
    functions: list[dict] = []
    lines = code.splitlines()
    for m in _JS_FUNC_RE.finditer(code):
        name = m.group(1) or m.group(2) or m.group(3) or "anonymous"
        lineno = code[: m.start()].count("\n") + 1
        end = min(lineno + 30, len(lines))
        functions.append({
            "name": name,
            "code": "\n".join(lines[lineno - 1: end]),
            "start_line": lineno,
            "file_path": file_path,
            "language": "javascript",
        })
    return functions


def _extract_functions(code: str, file_path: str) -> list[dict]:
    lang = _detect_language(file_path, code)
    if lang == "python":
        fns = _extract_python_functions(code, file_path)
    else:
        fns = _extract_js_functions(code, file_path)
    # Cap at 20 functions to avoid runaway state
    return fns[:20]


def _parse_diff(diff: str) -> list[dict]:
    """
    Return a list of changed-function dicts derived from a unified diff.

    Extracts added/modified lines per file and locates function definitions
    within them.
    """
    functions: list[dict] = []
    current_file = ""
    hunk_start = 1
    added_lines: list[tuple[int, str]] = []  # (lineno, text)
    current_lineno = 1

    for raw_line in diff.splitlines():
        m_file = _DIFF_FILE_RE.match(raw_line)
        if m_file:
            # Flush previous file
            if current_file and added_lines:
                code_block = "\n".join(t for _, t in added_lines)
                functions.extend(_extract_functions(code_block, current_file))
            current_file = m_file.group(1)
            added_lines = []
            current_lineno = 1
            continue

        m_hunk = _DIFF_HUNK_RE.match(raw_line)
        if m_hunk:
            current_lineno = int(m_hunk.group(1))
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            added_lines.append((current_lineno, raw_line[1:]))
            current_lineno += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            pass  # removed line, don't advance new lineno
        else:
            current_lineno += 1

    # Flush last file
    if current_file and added_lines:
        code_block = "\n".join(t for _, t in added_lines)
        functions.extend(_extract_functions(code_block, current_file))

    return functions


# ─────────────────────────────────────────────────────────────────────────
# Pattern analysis helpers
# ─────────────────────────────────────────────────────────────────────────

def _has_error_handling(code: str, language: str) -> bool:
    if language == "python":
        return bool(re.search(r"\btry\s*:", code))
    return bool(re.search(r"\btry\s*\{|\bcatch\s*\(", code))


def _has_logging(code: str) -> bool:
    return bool(re.search(r"\blog(?:ger)?\.(?:info|debug|warning|error|warn)\s*\(", code, re.IGNORECASE))


def _is_snake_case(name: str) -> bool:
    return bool(re.match(r"^[a-z][a-z0-9_]*$", name))


def _is_camel_case(name: str) -> bool:
    return bool(re.match(r"^[a-z][a-zA-Z0-9]*$", name) and any(c.isupper() for c in name))


# ─────────────────────────────────────────────────────────────────────────
# Finding helpers
# ─────────────────────────────────────────────────────────────────────────

def _finding(
    severity: str,
    category: str,
    message: str,
    file_path: str = "",
    line: int | None = None,
    suggestion: str = "",
    confidence: float = 0.8,
) -> dict:
    return {
        "severity": severity,
        "category": category,
        "message": message,
        "file_path": file_path,
        "line": line,
        "suggestion": suggestion,
        "confidence": round(confidence, 2),
    }


# ─────────────────────────────────────────────────────────────────────────
# Node: parse_input
# ─────────────────────────────────────────────────────────────────────────

def _make_parse_input_node():
    async def parse_input(state: ReviewState) -> dict:
        diff = state.get("diff")
        input_code = state.get("input_code", "")
        file_path = state.get("file_path")

        if diff:
            # PR mode: parse the diff
            changed_functions = _parse_diff(diff)
            if not changed_functions and input_code:
                # Diff produced nothing useful — fall back to snippet
                changed_functions = _extract_functions(
                    input_code, file_path or "snippet"
                )
        elif input_code:
            # Snippet mode
            changed_functions = _extract_functions(input_code, file_path or "snippet")
        else:
            changed_functions = []

        if not changed_functions:
            # Last resort: treat whole input as one opaque chunk
            changed_functions = [{
                "name": "input",
                "code": (input_code or diff or "")[:2000],
                "start_line": 1,
                "file_path": file_path or "snippet",
                "language": _detect_language(file_path, input_code or ""),
            }]

        return {"changed_functions": changed_functions}

    return parse_input


# ─────────────────────────────────────────────────────────────────────────
# Node: pattern_check
# ─────────────────────────────────────────────────────────────────────────

def _make_pattern_check_node(embedding_service, vector_service):
    async def pattern_check(state: ReviewState) -> dict:
        findings: list[dict] = []

        if embedding_service is None or vector_service is None:
            return {"pattern_findings": findings}

        project_id = state["project_id"]
        changed_functions = state.get("changed_functions", [])

        for fn in changed_functions[:5]:  # cap to avoid rate limits
            name = fn["name"]
            code = fn["code"]
            fp = fn.get("file_path", "")
            start_line = fn.get("start_line", 1)
            language = fn.get("language", "python")

            # Embed and retrieve similar functions
            try:
                embedding = await embedding_service.embed_query(code[:800])
                results = await vector_service.search(
                    project_id=project_id,
                    query_embedding=embedding,
                    top_k=10,
                )
            except Exception as exc:
                logger.warning("pattern_check vector search failed: %s", exc)
                continue

            if not results:
                continue

            similar_codes = [r.text for r in results if r.text]
            total = len(similar_codes)

            # ── Error-handling pattern ────────────────────────────────────
            has_eh = _has_error_handling(code, language)
            eh_count = sum(1 for c in similar_codes if _has_error_handling(c, language))
            if not has_eh and eh_count >= total * 0.6 and total >= 3:
                ref_files = [
                    (r.metadata or {}).get("file_path", "")
                    for r in results[:3]
                    if (r.metadata or {}).get("file_path")
                ]
                ref_str = ", ".join(f"`{f}`" for f in ref_files[:2]) if ref_files else "similar functions"
                findings.append(_finding(
                    severity="medium",
                    category="pattern",
                    message=(
                        f"`{name}` lacks error handling, but "
                        f"{eh_count}/{total} similar functions use try/except "
                        f"(see {ref_str})"
                    ),
                    file_path=fp,
                    line=start_line,
                    suggestion="Add try/except (or try/catch) around external calls and IO.",
                    confidence=round(eh_count / total, 2),
                ))

            # ── Logging pattern ──────────────────────────────────────────
            has_log = _has_logging(code)
            log_count = sum(1 for c in similar_codes if _has_logging(c))
            if not has_log and log_count >= total * 0.7 and total >= 3:
                findings.append(_finding(
                    severity="low",
                    category="pattern",
                    message=(
                        f"`{name}` has no logging, but "
                        f"{log_count}/{total} similar functions emit log statements."
                    ),
                    file_path=fp,
                    line=start_line,
                    suggestion="Add appropriate logging for observability.",
                    confidence=round(log_count / total, 2),
                ))

            # ── Naming convention ────────────────────────────────────────
            if language == "python" and name not in {"__init__", "__str__", "__repr__"}:
                if not _is_snake_case(name) and not name.startswith("_") and not name[0].isupper():
                    findings.append(_finding(
                        severity="low",
                        category="pattern",
                        message=f"`{name}` does not follow Python snake_case naming convention.",
                        file_path=fp,
                        line=start_line,
                        suggestion=f"Rename to `{re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()}`.",
                        confidence=0.9,
                    ))

        return {"pattern_findings": findings}

    return pattern_check


# ─────────────────────────────────────────────────────────────────────────
# Node: impact_analysis
# ─────────────────────────────────────────────────────────────────────────

def _make_impact_analysis_node(knowledge_graph):
    async def impact_analysis(state: ReviewState) -> dict:
        file_path = state.get("file_path")
        project_path = state.get("project_path", "")

        if not file_path or not project_path:
            return {"impact_report": {}}

        from server.services.impact_engine import BlastRadiusCalculator, build_dependency_graph

        try:
            if knowledge_graph is not None and not knowledge_graph.is_empty():
                graph = knowledge_graph._graph
            else:
                graph = await asyncio.to_thread(build_dependency_graph, project_path)

            calc = BlastRadiusCalculator()
            git_service = None  # not available in agent context
            report = await asyncio.to_thread(
                calc.calculate_blast_radius,
                file_path,
                graph,
                git_service,
                knowledge_graph,
            )
            return {
                "impact_report": {
                    "changed_file": report.changed_file,
                    "total_affected": report.total_affected,
                    "high_risk": [
                        {"file_path": f.file_path, "risk_score": f.risk_score, "reason": f.reason}
                        for f in report.high_risk[:5]
                    ],
                    "medium_risk": [
                        {"file_path": f.file_path, "risk_score": f.risk_score, "reason": f.reason}
                        for f in report.medium_risk[:5]
                    ],
                    "low_risk": [
                        {"file_path": f.file_path, "risk_score": f.risk_score, "reason": f.reason}
                        for f in report.low_risk[:5]
                    ],
                    "affected_modules": report.affected_modules,
                    "suggested_reviewers": report.suggested_reviewers,
                }
            }
        except Exception as exc:
            logger.warning("impact_analysis failed (non-fatal): %s", exc)
            return {"impact_report": {"error": str(exc)}}

    return impact_analysis


# ─────────────────────────────────────────────────────────────────────────
# Node: security_scan
# ─────────────────────────────────────────────────────────────────────────

def _make_security_scan_node():
    async def security_scan(state: ReviewState) -> dict:
        findings: list[dict] = []

        code = state.get("input_code") or state.get("diff") or ""
        file_path = state.get("file_path") or "snippet"
        changed_functions = state.get("changed_functions", [])

        # Run all pattern checks across the full code block
        lines = code.splitlines()

        def _line_of(match: re.Match) -> int:
            return code[: match.start()].count("\n") + 1

        # ── Hardcoded secrets ────────────────────────────────────────────
        for pattern, msg, severity in _SECRET_PATTERNS:
            for m in pattern.finditer(code):
                findings.append(_finding(
                    severity=severity,
                    category="security",
                    message=msg,
                    file_path=file_path,
                    line=_line_of(m),
                    suggestion=(
                        "Store secrets in environment variables and load via os.environ "
                        "or a secrets manager."
                    ),
                    confidence=0.9,
                ))

        # ── SQL injection ────────────────────────────────────────────────
        for pattern, msg in _SQL_INJECTION_PATTERNS:
            for m in pattern.finditer(code):
                findings.append(_finding(
                    severity="high",
                    category="security",
                    message=msg,
                    file_path=file_path,
                    line=_line_of(m),
                    suggestion="Use parameterised queries (?, %s, or ORM) instead of string building.",
                    confidence=0.85,
                ))

        # ── Path traversal ───────────────────────────────────────────────
        for pattern, msg in _PATH_TRAVERSAL_PATTERNS:
            for m in pattern.finditer(code):
                findings.append(_finding(
                    severity="high",
                    category="security",
                    message=msg,
                    file_path=file_path,
                    line=_line_of(m),
                    suggestion=(
                        "Validate and sanitise the path; use "
                        "pathlib.Path.resolve() and check it stays within the "
                        "allowed base directory."
                    ),
                    confidence=0.8,
                ))

        # ── PII in logs ──────────────────────────────────────────────────
        for pattern, msg in _PII_PATTERNS:
            for m in pattern.finditer(code):
                findings.append(_finding(
                    severity="high",
                    category="security",
                    message=msg,
                    file_path=file_path,
                    line=_line_of(m),
                    suggestion="Mask or omit sensitive fields before logging.",
                    confidence=0.75,
                ))

        # ── Cyclomatic complexity (Python, radon) ────────────────────────
        lang = _detect_language(file_path, code)
        if lang == "python":
            try:
                import radon.complexity as radon_cc  # type: ignore[import]

                for fn in changed_functions:
                    fn_code = fn.get("code", "")
                    fn_name = fn.get("name", "?")
                    fn_line = fn.get("start_line", 1)
                    fn_fp = fn.get("file_path", file_path)
                    try:
                        blocks = radon_cc.cc_visit(fn_code)
                        for block in blocks:
                            if block.complexity > 10:
                                findings.append(_finding(
                                    severity="medium",
                                    category="complexity",
                                    message=(
                                        f"`{fn_name}` has cyclomatic complexity "
                                        f"{block.complexity} (threshold: 10). "
                                        "High complexity makes code hard to test and maintain."
                                    ),
                                    file_path=fn_fp,
                                    line=fn_line,
                                    suggestion=(
                                        "Extract helper functions or simplify branching "
                                        "to bring complexity below 10."
                                    ),
                                    confidence=1.0,
                                ))
                    except Exception:
                        pass
            except ImportError:
                logger.debug("radon not available — skipping complexity check")

        # ── Async without error handling ────────────────────────────────
        if lang == "python":
            for fn in changed_functions:
                fn_code = fn.get("code", "")
                fn_name = fn.get("name", "?")
                fn_line = fn.get("start_line", 1)
                fn_fp = fn.get("file_path", file_path)
                is_async = bool(_ASYNC_DEF_RE.search(fn_code[:100]))
                has_await = bool(_AWAIT_RE.search(fn_code))
                has_try = bool(_TRY_RE.search(fn_code))
                if is_async and has_await and not has_try:
                    findings.append(_finding(
                        severity="medium",
                        category="security",
                        message=(
                            f"Async function `{fn_name}` uses `await` but has no "
                            "error handling. Unhandled coroutine exceptions may "
                            "silently propagate or crash the event loop."
                        ),
                        file_path=fn_fp,
                        line=fn_line,
                        suggestion="Wrap await calls in try/except and handle exceptions explicitly.",
                        confidence=0.8,
                    ))

        return {"security_findings": findings}

    return security_scan


# ─────────────────────────────────────────────────────────────────────────
# Node: synthesize
# ─────────────────────────────────────────────────────────────────────────

_SYNTHESIZE_SYSTEM = """\
You are a senior code reviewer summarising automated review findings for a developer.
Write a concise, developer-friendly paragraph (3-5 sentences) that:
1. States the overall risk level of this change.
2. Calls out the most important issues by category.
3. Notes if the change has significant downstream impact.
4. Ends with one actionable recommendation.
Respond with ONLY the summary paragraph — no headers, no bullet points."""


def _make_synthesize_node(llm_client):
    async def synthesize(state: ReviewState) -> dict:
        pattern_findings: list[dict] = state.get("pattern_findings", [])
        security_findings: list[dict] = state.get("security_findings", [])
        impact_report: dict = state.get("impact_report", {})

        # ── Merge and deduplicate ─────────────────────────────────────────
        all_findings = pattern_findings + security_findings
        seen: set[str] = set()
        deduped: list[dict] = []
        for f in all_findings:
            key = f"{f.get('category','')}|{(f.get('message') or '')[:60]}|{f.get('line', '')}"
            if key not in seen:
                seen.add(key)
                deduped.append(f)

        # ── Sort by severity ──────────────────────────────────────────────
        deduped.sort(key=lambda x: _SEVERITY_ORDER.get(x.get("severity", "low"), 3))

        # ── Severity counts ───────────────────────────────────────────────
        counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in deduped:
            sev = f.get("severity", "low")
            counts[sev] = counts.get(sev, 0) + 1

        # ── Build LLM prompt context ──────────────────────────────────────
        summary = ""
        if llm_client is not None:
            findings_text = "\n".join(
                f"[{f['severity'].upper()}] ({f['category']}) {f['message']}"
                for f in deduped[:15]
            )
            impact_text = ""
            if impact_report and not impact_report.get("error"):
                total = impact_report.get("total_affected", 0)
                if total:
                    impact_text = f"\nImpact: this change affects {total} downstream file(s)."

            user_content = (
                f"Findings ({len(deduped)} total):\n{findings_text or 'No issues found.'}"
                f"{impact_text}"
            )
            try:
                response = await llm_client.complete(
                    messages=[
                        {"role": "system", "content": _SYNTHESIZE_SYSTEM},
                        {"role": "user", "content": user_content},
                    ],
                    stream=False,
                )
                raw = _THINK_RE.sub("", response.content).strip()
                summary = raw
            except Exception as exc:
                logger.warning("synthesize LLM call failed: %s", exc)

        if not summary:
            # Fallback summary
            if not deduped:
                summary = "No issues found. The change looks clean."
            else:
                top = deduped[0]
                summary = (
                    f"Found {len(deduped)} issue(s): "
                    f"{counts['critical']} critical, {counts['high']} high, "
                    f"{counts['medium']} medium, {counts['low']} low. "
                    f"Most severe: [{top['severity'].upper()}] {top['message']}"
                )

        return {
            "final_review": {
                "summary": summary,
                "findings": deduped,
                "severity_counts": counts,
            }
        }

    return synthesize


# ─────────────────────────────────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────────────────────────────────

def _build_graph(llm_client, embedding_service, vector_service, knowledge_graph):
    builder = StateGraph(ReviewState)

    builder.add_node("parse_input", _make_parse_input_node())
    builder.add_node(
        "pattern_check",
        _make_pattern_check_node(embedding_service, vector_service),
    )
    builder.add_node("impact_analysis", _make_impact_analysis_node(knowledge_graph))
    builder.add_node("security_scan", _make_security_scan_node())
    builder.add_node("synthesize", _make_synthesize_node(llm_client))

    builder.set_entry_point("parse_input")
    builder.add_edge("parse_input", "pattern_check")
    builder.add_edge("pattern_check", "impact_analysis")
    builder.add_edge("impact_analysis", "security_scan")
    builder.add_edge("security_scan", "synthesize")
    builder.add_edge("synthesize", END)

    return builder.compile()


# ─────────────────────────────────────────────────────────────────────────
# Public class
# ─────────────────────────────────────────────────────────────────────────

class ReviewAgent:
    """
    Multi-node LangGraph code review pipeline.

    Usage::

        agent = ReviewAgent(llm_client, embedding_service, vector_service, kg)
        result = await agent.run(
            project_id="my-project",
            project_path="/abs/path",
            input_code="def foo(): ...",
        )
        # result: {"summary": "...", "findings": [...], "severity_counts": {...}}
    """

    def __init__(
        self,
        llm_client,
        embedding_service=None,
        vector_service=None,
        knowledge_graph=None,
    ):
        self._app = _build_graph(llm_client, embedding_service, vector_service, knowledge_graph)

    async def run(
        self,
        project_id: str,
        project_path: str = "",
        input_code: str = "",
        file_path: str | None = None,
        diff: str | None = None,
    ) -> dict[str, Any]:
        """
        Run the review pipeline. Raises asyncio.TimeoutError after 90 s.

        Returns the ``final_review`` dict:
        ``{"summary": str, "findings": [...], "severity_counts": {...}}``
        plus ``"impact_report"`` for caller convenience.
        """
        initial_state: ReviewState = {
            "project_id": project_id,
            "project_path": project_path,
            "input_code": input_code,
            "file_path": file_path,
            "diff": diff,
            "changed_functions": [],
            "pattern_findings": [],
            "impact_report": {},
            "security_findings": [],
            "final_review": {},
            "error": None,
        }
        result = await asyncio.wait_for(
            self._app.ainvoke(initial_state), timeout=90.0
        )
        out = result.get("final_review", {})
        out["impact_report"] = result.get("impact_report", {})
        return out
