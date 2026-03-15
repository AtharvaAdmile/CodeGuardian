"""
CodeGuardian MCP Server

Exposes CodeGuardian's Q&A and context features as MCP tools so that AI
coding assistants (Claude Code, OpenCode, etc.) can invoke them directly.

Transport modes
---------------
stdio (default) — for Claude Code and local assistants
    python -m server.mcp_server

SSE             — for web-based assistants
    python -m server.mcp_server --sse [--host 127.0.0.1] [--port 8743]

All tools are thin HTTP wrappers around the CodeGuardian FastAPI server
running on localhost:8742.  The MCP server never touches the database or
knowledge graph directly.

project_id convention
---------------------
project_id is derived from project_path using Path(project_path).name,
which matches the convention used by the indexing pipeline.  If you indexed
a project with a custom project_id, pass it explicitly via the optional
parameter exposed on each tool.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

import httpx
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

logger = logging.getLogger("codeguardian.mcp")

# ── Configuration ────────────────────────────────────────────────────────
_API_BASE = "http://localhost:8742"
_HTTP_TIMEOUT = 60.0  # seconds — LLM calls can take a while

# ── MCP server instance ──────────────────────────────────────────────────
server = Server("codeguardian")


# ── Helpers ──────────────────────────────────────────────────────────────

def _project_id(project_path: str) -> str:
    """Derive a project_id from a path — mirrors the indexing convention."""
    return Path(project_path).name


async def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    POST *payload* to the CodeGuardian API and return the JSON response.

    Raises a descriptive RuntimeError on HTTP or connection errors so that
    MCP tool handlers can surface a clean message to the assistant.
    """
    url = f"{_API_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        raise RuntimeError(
            f"Cannot reach CodeGuardian server at {_API_BASE}. "
            "Make sure it is running: uvicorn server.app:app --port 8742"
        )
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:400]
        raise RuntimeError(
            f"CodeGuardian API returned {exc.response.status_code}: {body}"
        ) from exc


# ── Tool: query_codebase ─────────────────────────────────────────────────

async def _query_codebase(question: str, project_path: str, project_id: str) -> str:
    """
    Call /api/ask and format the enriched response as markdown.

    The response now includes KG-derived decisions and expert attribution
    (as of the enhanced /api/ask endpoint).
    """
    data = await _post(
        "/api/ask",
        {
            "project_id": project_id,
            "question": question,
            "conversation_history": [],
        },
    )

    lines: list[str] = []

    answer = data.get("answer", "").strip()
    lines.append(answer)

    # Decisions referenced in the answer
    decisions = data.get("decisions_referenced", [])
    if decisions:
        lines.append("\n---\n### Architectural Decisions Referenced")
        for d in decisions:
            title = d.get("title") or "Untitled"
            body = d.get("decision", "")
            ref = d.get("source_ref", "")
            lines.append(f"\n**{title}**")
            if body:
                lines.append(f"> {body}")
            if ref:
                lines.append(f"*Source: {ref}*")

    # Experts
    experts = data.get("experts", [])
    if experts:
        names = ", ".join(
            e.get("name", "") for e in experts if e.get("name")
        )
        if names:
            lines.append(f"\n*File owners: {names}*")

    # Sources
    sources = data.get("sources", [])
    if sources:
        lines.append("\n---\n### Sources")
        seen: set[str] = set()
        for s in sources:
            fp = s.get("file_path", "")
            start = s.get("start_line")
            end = s.get("end_line")
            score = s.get("relevance_score", 0.0)
            if fp in seen:
                continue
            seen.add(fp)
            ref = fp
            if start:
                ref += f":{start}"
                if end and end != start:
                    ref += f"-{end}"
            lines.append(f"- `{ref}` (relevance: {score:.2f})")

    confidence = data.get("confidence", 0.0)
    lines.append(f"\n*Confidence: {confidence:.2f}*")

    return "\n".join(lines)


# ── Tool: get_context_for_file ───────────────────────────────────────────

async def _get_context_for_file(
    file_path: str, project_path: str, project_id: str
) -> str:
    """
    Ask the /api/ask endpoint a structured context question for a specific
    file.  The enriched pipeline automatically attaches KG decisions, owner,
    and module information — so we get all of that for free.
    """
    question = (
        f"Explain the purpose, architecture, and key functions of `{file_path}`. "
        "Who are the primary owners? What architectural decisions affect this file? "
        "What other files depend on it?"
    )

    data = await _post(
        "/api/ask",
        {
            "project_id": project_id,
            "question": question,
            "conversation_history": [],
        },
    )

    lines: list[str] = [f"## Context: `{file_path}`\n"]

    answer = data.get("answer", "").strip()
    lines.append(answer)

    # Experts / owners
    experts = data.get("experts", [])
    if experts:
        lines.append("\n### Owners")
        for e in experts:
            name = e.get("name", "")
            email = e.get("email", "")
            score = e.get("expertise_score", 0.0)
            if name:
                entry = f"- **{name}**"
                if email:
                    entry += f" `<{email}>`"
                entry += f" — expertise score: {score:.1f}"
                lines.append(entry)

    # Decisions
    decisions = data.get("decisions_referenced", [])
    if decisions:
        lines.append("\n### Architectural Decisions")
        for d in decisions:
            title = d.get("title") or "Untitled"
            body = d.get("decision", "")
            ref = d.get("source_ref", "")
            lines.append(f"\n**{title}**")
            if body:
                lines.append(f"> {body}")
            if ref:
                lines.append(f"*Source: {ref}*")

    # Source chunks from this file
    sources = [
        s for s in data.get("sources", [])
        if s.get("file_path", "") == file_path
    ]
    if sources:
        lines.append("\n### Retrieved Code Chunks")
        for s in sources:
            start = s.get("start_line")
            end = s.get("end_line")
            chunk_type = s.get("chunk_type", "")
            ref = file_path
            if start:
                ref += f":{start}"
                if end and end != start:
                    ref += f"-{end}"
            entry = f"- `{ref}`"
            if chunk_type:
                entry += f" ({chunk_type})"
            lines.append(entry)

    confidence = data.get("confidence", 0.0)
    lines.append(f"\n*Confidence: {confidence:.2f}*")

    return "\n".join(lines)


# ── Tool: get_decision_history ───────────────────────────────────────────

async def _get_decision_history(
    file_path: str, project_path: str, project_id: str
) -> str:
    """
    Surface all architectural decisions for a file via two parallel calls:
    - /api/ask with a decision-focused question (triggers KG + semantic search)
    - /api/analyze/history for git timeline context
    """
    ask_payload = {
        "project_id": project_id,
        "question": (
            f"What architectural decisions affect `{file_path}`? "
            "List every decision with its full context, reasoning, and who made it. "
            "Why was each design choice made?"
        ),
        "conversation_history": [],
    }
    history_payload = {
        "project_path": project_path,
        "file_path": file_path,
    }

    ask_data, history_data = await asyncio.gather(
        _post("/api/ask", ask_payload),
        _post("/api/analyze/history", history_payload),
        return_exceptions=True,
    )

    lines: list[str] = [f"## Decision History: `{file_path}`\n"]

    # ── Architectural decisions (KG + semantic) ──────────────────────
    if isinstance(ask_data, Exception):
        lines.append(f"> Could not retrieve decisions: {ask_data}")
    else:
        decisions = ask_data.get("decisions_referenced", [])
        if decisions:
            lines.append("### Architectural Decisions\n")
            for i, d in enumerate(decisions, 1):
                title = d.get("title") or "Untitled"
                body = d.get("decision", "")
                ref = d.get("source_ref", "")
                lines.append(f"#### {i}. {title}")
                if body:
                    lines.append(f"\n{body}\n")
                if ref:
                    lines.append(f"*Source: {ref}*\n")
        else:
            # Fall back to the answer text which may contain decision info
            answer = ask_data.get("answer", "").strip()
            if answer:
                lines.append("### Decisions\n")
                lines.append(answer)

    # ── Git commit timeline ──────────────────────────────────────────
    if isinstance(history_data, Exception):
        lines.append(f"\n> Git history unavailable: {history_data}")
    else:
        history = history_data.get("history", [])
        summary = history_data.get("summary", "")
        if summary:
            lines.append(f"\n### Git Summary\n{summary}")
        if history:
            lines.append("\n### Commit Timeline")
            # Show the most recent 10 commits
            for entry in history[:10]:
                sha = (entry.get("sha") or entry.get("hash") or "")[:8]
                msg = entry.get("message") or entry.get("summary") or ""
                author = entry.get("author") or ""
                date = entry.get("date") or entry.get("authored_date") or ""
                line = f"- `{sha}` {msg}"
                if author:
                    line += f" — *{author}*"
                if date:
                    line += f" ({date[:10]})"
                lines.append(line)

    return "\n".join(lines)


# ── Tool: get_expertise ──────────────────────────────────────────────────

async def _get_expertise(
    file_path: str, project_path: str, project_id: str
) -> str:
    """
    Return who knows this file best, combining:
    - /api/analyze/expert  — primary expert from git blame / commit analysis
    - /api/analyze/history — commit timeline for recency signal
    """
    expert_payload = {"project_path": project_path, "file_path": file_path}
    history_payload = {"project_path": project_path, "file_path": file_path}

    expert_data, history_data = await asyncio.gather(
        _post("/api/analyze/expert", expert_payload),
        _post("/api/analyze/history", history_payload),
        return_exceptions=True,
    )

    lines: list[str] = [f"## Expertise: `{file_path}`\n"]

    # ── Expert breakdown ─────────────────────────────────────────────
    if isinstance(expert_data, Exception):
        lines.append(f"> Could not retrieve expert data: {expert_data}")
    else:
        if expert_data.get("error"):
            lines.append(f"> {expert_data['error']}")
        else:
            primary = expert_data.get("primary_expert")
            backup = expert_data.get("backup")
            experts = expert_data.get("experts", [])
            last_active = expert_data.get("last_active")

            if primary:
                lines.append(f"**Primary Expert:** {primary}")
            if backup:
                lines.append(f"**Backup:** {backup}")
            if last_active:
                lines.append(f"**Last Active:** {last_active}")

            if experts:
                lines.append("\n### All Contributors")
                for e in experts:
                    name = e.get("name") or e.get("author") or ""
                    commits = e.get("commit_count") or e.get("commits") or 0
                    pct = e.get("ownership_pct") or e.get("percentage") or 0
                    if name:
                        entry = f"- **{name}**"
                        if commits:
                            entry += f" — {commits} commits"
                        if pct:
                            entry += f" ({pct:.0f}% ownership)"
                        lines.append(entry)

    # ── Recency signal from git history ─────────────────────────────
    if isinstance(history_data, Exception):
        lines.append(f"\n> Git history unavailable: {history_data}")
    else:
        churn = history_data.get("churn", {})
        history = history_data.get("history", [])

        if churn:
            total = churn.get("total_commits") or churn.get("commits", 0)
            additions = churn.get("additions", 0)
            deletions = churn.get("deletions", 0)
            if total or additions or deletions:
                lines.append(
                    f"\n### Activity\n"
                    f"- Total commits: {total}\n"
                    f"- Lines added: {additions}  /  deleted: {deletions}"
                )

        if history:
            latest = history[0]
            date = latest.get("date") or latest.get("authored_date") or ""
            author = latest.get("author", "")
            msg = latest.get("message") or latest.get("summary") or ""
            if date or author or msg:
                lines.append(f"\n**Most recent change:** {msg[:80]}")
                if author:
                    lines.append(f"*by {author}*", )
                if date:
                    lines.append(f"*on {date[:10]}*")

    return "\n".join(lines)


# ── Tool: generate_onboarding_path ───────────────────────────────────────

async def _generate_onboarding_path(
    task_description: str,
    project_path: str,
    project_id: str,
) -> str:
    """
    Call /api/onboard/generate and format the learning path as markdown.
    """
    data = await _post(
        "/api/onboard/generate",
        {
            "project_id": project_id,
            "task_description": task_description,
        },
    )

    if data.get("error"):
        return f"**Error:** {data['error']}"

    steps = data.get("learning_path", [])
    if not steps:
        return "No learning path generated."

    lines: list[str] = [f"## Onboarding Path\n\n**Task:** {task_description[:200]}\n"]
    for step in steps:
        num = step.get("step_number", "?")
        action = step.get("action", "read")
        fp = step.get("file_path", "unknown")
        focus = step.get("focus_area", "")
        context = step.get("context", "")
        decisions = step.get("related_decisions", [])
        expert = step.get("expert_contact")

        lines.append(f"### {num}. `{action}` — `{fp}`")
        if focus:
            lines.append(f"**Focus:** {focus}")
        if context:
            lines.append(f"\n{context}")
        if decisions:
            lines.append(f"\n*Decisions:* {', '.join(decisions)}")
        if expert:
            lines.append(f"\n*Expert:* {expert}")
        lines.append("")

    return "\n".join(lines)


# ── Tool: analyze_impact ─────────────────────────────────────────────────

async def _analyze_impact(
    file_path: str,
    project_path: str,
    diff: str | None,
) -> str:
    """Call /api/impact/analyze and format the BlastRadiusReport as markdown."""
    payload: dict[str, Any] = {
        "project_path": project_path,
        "file_path": file_path,
    }
    if diff:
        payload["diff"] = diff

    data = await _post("/api/impact/analyze", payload)

    if data.get("error"):
        return f"**Error:** {data['error']}"

    changed = data.get("changed_file", file_path)
    total = data.get("total_affected", 0)
    lines: list[str] = [f"## Impact Analysis: `{changed}`\n"]
    lines.append(f"**{total} file(s) affected** by this change.\n")

    def _fmt_bucket(label: str, files: list[dict[str, Any]]) -> None:
        if not files:
            return
        lines.append(f"### {label} ({len(files)})")
        for f in files:
            fp = f.get("file_path", "")
            score = f.get("risk_score", 0.0)
            dist = f.get("distance", "?")
            reason = f.get("reason", "")
            lines.append(
                f"- `{fp}`  risk={score:.3f}  distance={dist}"
                + (f"  — {reason}" if reason else "")
            )

    _fmt_bucket("High Risk (≥0.7)", data.get("high_risk", []))
    _fmt_bucket("Medium Risk (0.3–0.7)", data.get("medium_risk", []))
    _fmt_bucket("Low Risk (<0.3)", data.get("low_risk", []))

    modules = data.get("affected_modules", [])
    if modules:
        lines.append(f"\n**Affected modules:** {', '.join(f'`{m}`' for m in modules)}")

    reviewers = data.get("suggested_reviewers", [])
    if reviewers:
        lines.append(f"\n**Suggested reviewers:** {', '.join(reviewers)}")

    return "\n".join(lines)


# ── Tool: check_breaking_changes ─────────────────────────────────────────

async def _check_breaking_changes(
    old_content: str,
    new_content: str,
    language: str,
) -> str:
    """Call /api/impact/breaking-changes and format results as markdown."""
    data = await _post(
        "/api/impact/breaking-changes",
        {
            "old_content": old_content,
            "new_content": new_content,
            "language": language,
        },
    )

    if data.get("error"):
        return f"**Error:** {data['error']}"

    changes: list[dict[str, Any]] = data.get("changes", [])
    total_b = data.get("total_breaking", 0)
    total_nb = data.get("total_non_breaking", 0)

    if not changes:
        return "No API changes detected between the two versions."

    lines: list[str] = [
        f"## Breaking-Change Analysis\n",
        f"**{total_b} breaking** / **{total_nb} non-breaking** change(s) detected.\n",
    ]

    breaking = [c for c in changes if c.get("severity") == "breaking"]
    non_breaking = [c for c in changes if c.get("severity") == "non-breaking"]

    if breaking:
        lines.append("### Breaking Changes")
        for c in breaking:
            lines.append(f"\n#### `{c.get('symbol', '?')}` — {c.get('change_type', '')}")
            lines.append(c.get("description", ""))
            if c.get("old_signature"):
                lines.append(f"- **Before:** `{c['old_signature']}`")
            if c.get("new_signature"):
                lines.append(f"- **After:**  `{c['new_signature']}`")

    if non_breaking:
        lines.append("\n### Non-Breaking Changes")
        for c in non_breaking:
            lines.append(
                f"- `{c.get('symbol', '?')}`: {c.get('description', '')}"
            )

    return "\n".join(lines)


# ── Tool: review_code ────────────────────────────────────────────────────

async def _review_code(
    project_id: str,
    project_path: str,
    code: str | None,
    file_path: str | None,
    diff: str | None,
) -> str:
    """Call /api/review and format the ReviewReport as markdown."""
    payload: dict[str, Any] = {
        "project_id": project_id,
        "project_path": project_path,
    }
    if code:
        payload["code"] = code
    if file_path:
        payload["file_path"] = file_path
    if diff:
        payload["diff"] = diff

    data = await _post("/api/review", payload)

    if data.get("error"):
        return f"**Error:** {data['error']}"

    lines: list[str] = []

    summary = data.get("summary", "").strip()
    if summary:
        lines.append(f"## Code Review\n\n{summary}\n")

    counts = data.get("severity_counts", {})
    if any(counts.values()):
        parts = " | ".join(
            f"**{k.capitalize()}:** {v}"
            for k, v in counts.items()
            if v > 0
        )
        lines.append(f"**Severity summary:** {parts}\n")

    findings = data.get("findings", [])
    if findings:
        lines.append("### Findings\n")
        for i, f in enumerate(findings, 1):
            sev = f.get("severity", "low").upper()
            cat = f.get("category", "")
            msg = f.get("message", "")
            fp = f.get("file_path", "")
            lineno = f.get("line")
            suggestion = f.get("suggestion", "")
            conf = f.get("confidence", 0.0)

            loc = fp
            if lineno:
                loc += f":{lineno}"

            lines.append(f"#### {i}. [{sev}] {msg}")
            if loc and loc != ":":
                lines.append(f"- **Location:** `{loc}`")
            if cat:
                lines.append(f"- **Category:** {cat}")
            if suggestion:
                lines.append(f"- **Fix:** {suggestion}")
            lines.append(f"- **Confidence:** {conf:.0%}\n")
    else:
        lines.append("\n✅ No issues found.")

    impact = data.get("impact_report", {})
    if impact and not impact.get("error") and impact.get("total_affected", 0):
        total = impact["total_affected"]
        lines.append(f"\n### Impact\n**{total} file(s) affected** by this change.")
        high = impact.get("high_risk", [])
        if high:
            lines.append("**High-risk dependents:**")
            for f in high[:3]:
                lines.append(f"- `{f['file_path']}` (risk={f['risk_score']:.2f})")

    return "\n".join(lines)


# ── Tool: check_compliance ────────────────────────────────────────────────

async def _check_compliance(
    project_id: str,
    project_path: str,
    code: str,
    file_path: str | None,
) -> str:
    """
    Run /api/review focused on security and compliance findings only.
    Filters the full review to security + complexity categories.
    """
    payload: dict[str, Any] = {
        "project_id": project_id,
        "project_path": project_path,
        "code": code,
    }
    if file_path:
        payload["file_path"] = file_path

    data = await _post("/api/review", payload)

    if data.get("error"):
        return f"**Error:** {data['error']}"

    # Filter to security + complexity only
    findings = [
        f for f in data.get("findings", [])
        if f.get("category") in {"security", "complexity"}
    ]

    if not findings:
        return "✅ No security or compliance issues detected."

    lines: list[str] = ["## Compliance & Security Scan\n"]

    critical_high = [f for f in findings if f.get("severity") in {"critical", "high"}]
    if critical_high:
        lines.append(f"⚠️  **{len(critical_high)} critical/high severity issue(s) found.**\n")

    for i, f in enumerate(findings, 1):
        sev = f.get("severity", "low").upper()
        msg = f.get("message", "")
        fp = f.get("file_path", "")
        lineno = f.get("line")
        suggestion = f.get("suggestion", "")

        loc = fp
        if lineno:
            loc += f":{lineno}"

        lines.append(f"### {i}. [{sev}] {msg}")
        if loc and loc != ":":
            lines.append(f"- **Location:** `{loc}`")
        if suggestion:
            lines.append(f"- **Remediation:** {suggestion}")
        lines.append("")

    return "\n".join(lines)


# ── Tool registry ────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="query_codebase",
            description=(
                "Ask any natural-language question about the indexed codebase. "
                "Returns an answer grounded in code chunks, architectural decisions, "
                "and author expertise. Cite specific files and line numbers."
            ),
            inputSchema={
                "type": "object",
                "required": ["question", "project_path"],
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Natural-language question about the codebase.",
                    },
                    "project_path": {
                        "type": "string",
                        "description": "Absolute path to the project root.",
                    },
                    "project_id": {
                        "type": "string",
                        "description": (
                            "Optional project ID override. "
                            "Defaults to the directory name of project_path."
                        ),
                    },
                },
            },
        ),
        types.Tool(
            name="get_context_for_file",
            description=(
                "Get full context for a specific file: what it does, "
                "who owns it, which architectural decisions affect it, "
                "and what other files depend on it."
            ),
            inputSchema={
                "type": "object",
                "required": ["file_path", "project_path"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "File path relative to the project root, "
                            "e.g. 'server/routes/query.py'."
                        ),
                    },
                    "project_path": {
                        "type": "string",
                        "description": "Absolute path to the project root.",
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Optional project ID override.",
                    },
                },
            },
        ),
        types.Tool(
            name="get_decision_history",
            description=(
                "Return all architectural decisions that affect a file, "
                "formatted as a timeline with context and reasoning. "
                "Also includes the git commit history for the file."
            ),
            inputSchema={
                "type": "object",
                "required": ["file_path", "project_path"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "File path relative to the project root.",
                    },
                    "project_path": {
                        "type": "string",
                        "description": "Absolute path to the project root.",
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Optional project ID override.",
                    },
                },
            },
        ),
        types.Tool(
            name="get_expertise",
            description=(
                "Return who knows a file best: primary expert, backup, "
                "all contributors ranked by commit count and ownership percentage, "
                "and recency signals from the git history."
            ),
            inputSchema={
                "type": "object",
                "required": ["file_path", "project_path"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "File path relative to the project root.",
                    },
                    "project_path": {
                        "type": "string",
                        "description": "Absolute path to the project root.",
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Optional project ID override.",
                    },
                },
            },
        ),
        types.Tool(
            name="analyze_impact",
            description=(
                "Calculate the blast radius of changing a file: which files "
                "transitively depend on it, a risk score for each (based on "
                "graph centrality and recent churn), and suggested reviewers. "
                "Use this before merging to understand the scope of a change."
            ),
            inputSchema={
                "type": "object",
                "required": ["file_path", "project_path"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "File that was changed "
                            "(absolute or project-relative path)."
                        ),
                    },
                    "project_path": {
                        "type": "string",
                        "description": "Absolute path to the project root.",
                    },
                    "diff": {
                        "type": "string",
                        "description": (
                            "Optional unified diff of the change. "
                            "Enables automatic breaking-change detection."
                        ),
                    },
                },
            },
        ),
        types.Tool(
            name="review_code",
            description=(
                "Run a multi-stage code review on a snippet or PR diff. "
                "Checks security vulnerabilities (hardcoded secrets, SQL injection, "
                "path traversal, PII logging), code patterns (error handling, naming, "
                "logging consistency vs similar functions), cyclomatic complexity, "
                "and blast-radius impact. Returns ranked findings with suggested fixes."
            ),
            inputSchema={
                "type": "object",
                "required": ["project_id", "project_path"],
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier (must be indexed).",
                    },
                    "project_path": {
                        "type": "string",
                        "description": "Absolute path to the project root.",
                    },
                    "code": {
                        "type": "string",
                        "description": "Code snippet to review (snippet mode).",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "File path relative to project root (PR mode).",
                    },
                    "diff": {
                        "type": "string",
                        "description": "Unified diff of changes (PR mode).",
                    },
                },
            },
        ),
        types.Tool(
            name="check_compliance",
            description=(
                "Security and compliance scan of a code snippet. "
                "Checks for hardcoded secrets, SQL injection, path traversal, "
                "PII in logs, and high cyclomatic complexity. "
                "Returns only security/compliance findings (no pattern or impact data)."
            ),
            inputSchema={
                "type": "object",
                "required": ["project_id", "project_path", "code"],
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier.",
                    },
                    "project_path": {
                        "type": "string",
                        "description": "Absolute path to the project root.",
                    },
                    "code": {
                        "type": "string",
                        "description": "Source code to scan.",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Optional file path for language detection.",
                    },
                },
            },
        ),
        types.Tool(
            name="generate_onboarding_path",
            description=(
                "Generate an ordered learning path for a developer picking up a new task. "
                "Returns a numbered sequence of files to read/understand/review, enriched "
                "with architectural decisions and expert contacts from the knowledge graph."
            ),
            inputSchema={
                "type": "object",
                "required": ["task_description", "project_path"],
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Plain-text description of the task the developer needs to implement.",
                    },
                    "project_path": {
                        "type": "string",
                        "description": "Absolute path to the project root.",
                    },
                    "project_id": {
                        "type": "string",
                        "description": (
                            "Optional project ID override. "
                            "Defaults to the directory name of project_path."
                        ),
                    },
                },
            },
        ),
        types.Tool(
            name="check_breaking_changes",
            description=(
                "Detect API-level breaking changes between two versions of a "
                "source file using AST comparison (Python) or regex (JS/TS). "
                "Identifies removed functions, added required parameters, "
                "removed parameters, and changed return types. "
                "Deterministic — no LLM involved."
            ),
            inputSchema={
                "type": "object",
                "required": ["old_content", "new_content", "language"],
                "properties": {
                    "old_content": {
                        "type": "string",
                        "description": "Source code of the original version.",
                    },
                    "new_content": {
                        "type": "string",
                        "description": "Source code of the modified version.",
                    },
                    "language": {
                        "type": "string",
                        "description": (
                            "Source language: 'python', 'javascript', "
                            "'typescript', 'js', 'ts', 'jsx', or 'tsx'."
                        ),
                    },
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict[str, Any]
) -> list[types.TextContent]:
    try:
        project_path: str = arguments.get("project_path", "")
        pid: str = arguments.get("project_id") or _project_id(project_path)

        if name == "review_code":
            result = await _review_code(
                project_id=arguments.get("project_id", pid),
                project_path=project_path,
                code=arguments.get("code"),
                file_path=arguments.get("file_path"),
                diff=arguments.get("diff"),
            )
        elif name == "check_compliance":
            result = await _check_compliance(
                project_id=arguments.get("project_id", pid),
                project_path=project_path,
                code=arguments["code"],
                file_path=arguments.get("file_path"),
            )
        elif name == "query_codebase":
            result = await _query_codebase(
                question=arguments["question"],
                project_path=project_path,
                project_id=pid,
            )
        elif name == "get_context_for_file":
            result = await _get_context_for_file(
                file_path=arguments["file_path"],
                project_path=project_path,
                project_id=pid,
            )
        elif name == "get_decision_history":
            result = await _get_decision_history(
                file_path=arguments["file_path"],
                project_path=project_path,
                project_id=pid,
            )
        elif name == "get_expertise":
            result = await _get_expertise(
                file_path=arguments["file_path"],
                project_path=project_path,
                project_id=pid,
            )
        elif name == "generate_onboarding_path":
            result = await _generate_onboarding_path(
                task_description=arguments["task_description"],
                project_path=project_path,
                project_id=pid,
            )
        elif name == "analyze_impact":
            result = await _analyze_impact(
                file_path=arguments["file_path"],
                project_path=project_path,
                diff=arguments.get("diff"),
            )
        elif name == "check_breaking_changes":
            result = await _check_breaking_changes(
                old_content=arguments["old_content"],
                new_content=arguments["new_content"],
                language=arguments["language"],
            )
        else:
            result = f"Unknown tool: {name}"

    except RuntimeError as exc:
        result = f"**Error:** {exc}"
    except KeyError as exc:
        result = f"**Missing required argument:** {exc}"

    return [types.TextContent(type="text", text=result)]


# ── Transports ───────────────────────────────────────────────────────────

async def _run_stdio() -> None:
    """Run the MCP server over stdio (for Claude Code / local assistants)."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def _run_sse(host: str, port: int) -> None:
    """
    Run the MCP server over SSE transport embedded in a minimal Starlette app.
    Used by web-based assistants that speak HTTP.
    """
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.routing import Mount, Route

    sse_transport = SseServerTransport("/messages/")
    init_options = server.create_initialization_options()

    async def handle_sse(request: Request) -> None:
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send  # type: ignore[attr-defined]
        ) as streams:
            await server.run(streams[0], streams[1], init_options)

    starlette_app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
        ]
    )

    config = uvicorn.Config(
        starlette_app,
        host=host,
        port=port,
        log_level="info",
    )
    await uvicorn.Server(config).serve()


# ── Entry point ──────────────────────────────────────────────────────────

def main() -> None:
    global _API_BASE  # noqa: PLW0603

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stderr,  # MCP stdio uses stdout; keep logs on stderr
    )

    parser = argparse.ArgumentParser(
        description="CodeGuardian MCP Server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--sse",
        action="store_true",
        help="Run SSE transport instead of stdio.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind when running SSE transport.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8743,
        help="Port to bind when running SSE transport.",
    )
    parser.add_argument(
        "--api-base",
        default=_API_BASE,
        help="Base URL of the CodeGuardian FastAPI server.",
    )
    args = parser.parse_args()

    # Allow overriding the API base at runtime
    _API_BASE = args.api_base

    if args.sse:
        logger.info("Starting MCP server (SSE) on %s:%d", args.host, args.port)
        asyncio.run(_run_sse(args.host, args.port))
    else:
        logger.info("Starting MCP server (stdio)")
        asyncio.run(_run_stdio())


if __name__ == "__main__":
    main()
