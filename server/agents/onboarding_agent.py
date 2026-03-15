"""
Onboarding Copilot — LangGraph agent that converts a plain-text task
description into an ordered learning path enriched with knowledge graph
architectural decisions and expertise data.

Graph topology (linear):
    parse_task → find_relevant_code → gather_context → generate_path → END
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TypedDict

from langgraph.graph import StateGraph, END

logger = logging.getLogger("codeguardian.agents.onboarding")

# ── Regex helpers ────────────────────────────────────────────────────────

# Matches a JSON object inside a fenced code block (```json ... ```)
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
# Fallback: bare JSON object anywhere in the text
_JSON_BARE_RE = re.compile(r"\{.*\}", re.DOTALL)

# Matches a JSON array inside a fenced code block
_ARRAY_BLOCK_RE = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL)
# Fallback: bare JSON array anywhere in the text
_ARRAY_BARE_RE = re.compile(r"\[.*\]", re.DOTALL)

# Strip <think>…</think> tags (defensive — llm_client already does this)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


# ── State ────────────────────────────────────────────────────────────────

class OnboardingState(TypedDict):
    project_id: str
    task_description: str
    extracted_concepts: dict       # {key_modules, required_concepts, file_patterns}
    relevant_files: list           # [{file_path, relevance_score, snippet}]
    context_per_file: dict         # {file_path: {decisions, owners, dependencies, dependents}}
    learning_path: list            # list of LearningStep dicts
    error: str | None


# ── JSON extraction helpers ──────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """
    Extract a JSON object from *text*.

    Two-stage:
    1. Try fenced code block (```json ... ```)
    2. Fallback: bare ``{...}`` in text

    Returns a default concepts dict on any parse failure.
    """
    text = _THINK_RE.sub("", text)

    for pattern in (_JSON_BLOCK_RE, _JSON_BARE_RE):
        m = pattern.search(text)
        if m:
            try:
                return json.loads(m.group(1) if pattern is _JSON_BLOCK_RE else m.group(0))
            except (json.JSONDecodeError, IndexError):
                continue

    return {}


def _extract_json_array(text: str, task_description: str = "") -> list:
    """
    Extract a JSON array from *text*.

    Three-stage:
    1. Fenced code block containing an array
    2. Bare ``[...]`` in text
    3. If result is a dict, look for the first list value inside it
       (handles {"steps": [...]})

    Returns a single-step fallback path on failure.
    """
    text = _THINK_RE.sub("", text)

    candidate = None

    # Stage 1: fenced block
    m = _ARRAY_BLOCK_RE.search(text)
    if m:
        try:
            parsed = json.loads(m.group(1))
            if isinstance(parsed, list):
                return parsed
            candidate = parsed
        except json.JSONDecodeError:
            pass

    # Stage 2: bare array
    if candidate is None:
        m = _ARRAY_BARE_RE.search(text)
        if m:
            try:
                parsed = json.loads(m.group(0))
                if isinstance(parsed, list):
                    return parsed
                candidate = parsed
            except json.JSONDecodeError:
                pass

    # Stage 3: unwrap dict
    if isinstance(candidate, dict):
        for v in candidate.values():
            if isinstance(v, list):
                return v

    # Also try parsing the whole text as JSON (bare object with list value)
    try:
        parsed = json.loads(text.strip())
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for v in parsed.values():
                if isinstance(v, list):
                    return v
    except json.JSONDecodeError:
        pass

    # Fallback single step
    return [
        {
            "step_number": 1,
            "action": "read",
            "file_path": "unknown",
            "focus_area": "Start here",
            "context": f"Could not parse learning path. Original task: {task_description[:200]}",
            "related_decisions": [],
            "expert_contact": None,
        }
    ]


# ── Node factories ────────────────────────────────────────────────────────

_PARSE_TASK_SYSTEM = """\
You are a software onboarding assistant. Extract structured information from a task description.
Respond with ONLY a valid JSON object — no markdown, no prose."""

_PARSE_TASK_USER_TMPL = """\
Task: {task_description}
Return exactly: {{"key_modules": [...], "required_concepts": [...], "file_patterns": [...]}}
Rules:
- key_modules = short path prefixes (2-4 items)
- required_concepts = implementation-level concepts (3-6 items)
- file_patterns = keyword fragments to match filenames (2-5 items)"""


def _make_parse_task_node(llm_client):
    async def parse_task(state: OnboardingState) -> dict:
        task = state["task_description"]
        messages = [
            {"role": "system", "content": _PARSE_TASK_SYSTEM},
            {
                "role": "user",
                "content": _PARSE_TASK_USER_TMPL.format(
                    task_description=task[:2000]
                ),
            },
        ]
        try:
            response = await llm_client.complete(messages=messages, stream=False)
            concepts = _extract_json(response.content)
            if not concepts:
                raise ValueError("Empty JSON extracted")
        except Exception as exc:
            logger.warning("parse_task LLM failed (%s); using fallback concepts", exc)
            concepts = {
                "key_modules": [],
                "required_concepts": [task[:200]],
                "file_patterns": [],
            }

        # Ensure all keys exist
        concepts.setdefault("key_modules", [])
        concepts.setdefault("required_concepts", [task[:200]])
        concepts.setdefault("file_patterns", [])

        return {"extracted_concepts": concepts}

    return parse_task


def _make_find_relevant_code_node(embedding_service, vector_service, knowledge_graph):
    async def find_relevant_code(state: OnboardingState) -> dict:
        project_id = state["project_id"]
        task = state["task_description"]
        concepts = state.get("extracted_concepts", {})
        required_concepts = concepts.get("required_concepts", [task[:200]])
        key_modules = concepts.get("key_modules", [])

        # Collect (file_path, relevance_score, snippet) dicts
        file_scores: dict[str, dict] = {}

        async def _search_and_collect(query: str, top_k: int) -> None:
            try:
                embedding = await embedding_service.embed_query(query)
                results = await vector_service.search(
                    project_id=project_id,
                    query_embedding=embedding,
                    top_k=top_k,
                )
                for r in results:
                    fp = (r.metadata or {}).get("file_path", "unknown")
                    score = r.score
                    if fp not in file_scores or file_scores[fp]["relevance_score"] < score:
                        file_scores[fp] = {
                            "file_path": fp,
                            "relevance_score": round(score, 4),
                            "snippet": r.text[:300] if r.text else "",
                        }
            except Exception as exc:
                logger.warning("Vector search failed for query %r: %s", query[:80], exc)

        # Search with each concept (max 5) concurrently
        tasks = [
            _search_and_collect(concept, 5)
            for concept in required_concepts[:5]
        ]
        # Also broad search with full task description
        tasks.append(_search_and_collect(task, 10))
        await asyncio.gather(*tasks)

        # Knowledge graph module overview
        if knowledge_graph is not None and not knowledge_graph.is_empty():
            for module in key_modules:
                try:
                    overview = knowledge_graph.get_module_overview(module)
                    for fp in (overview.get("files") or []):
                        if fp not in file_scores:
                            file_scores[fp] = {
                                "file_path": fp,
                                "relevance_score": 0.5,
                                "snippet": "",
                            }
                except Exception as exc:
                    logger.debug("KG module overview failed for %r: %s", module, exc)

        # Sort by relevance, cap at 20
        sorted_files = sorted(
            file_scores.values(),
            key=lambda x: x["relevance_score"],
            reverse=True,
        )[:20]

        return {"relevant_files": sorted_files}

    return find_relevant_code


def _make_gather_context_node(knowledge_graph):
    async def gather_context(state: OnboardingState) -> dict:
        relevant_files = state.get("relevant_files", [])
        context_per_file: dict[str, dict] = {}

        if knowledge_graph is None or knowledge_graph.is_empty():
            return {"context_per_file": context_per_file}

        for entry in relevant_files[:15]:
            fp = entry.get("file_path", "")
            if not fp or fp == "unknown":
                continue
            try:
                file_ctx = knowledge_graph.get_file_context(fp)
                decisions = []
                try:
                    decisions = knowledge_graph.get_decisions_affecting_file(fp) or []
                except Exception:
                    decisions = file_ctx.get("decisions", [])

                owners = []
                try:
                    owners = knowledge_graph.get_expertise_for_file(fp) or []
                except Exception:
                    owners = file_ctx.get("owners", [])

                context_per_file[fp] = {
                    "decisions": decisions,
                    "owners": owners,
                    "dependencies": file_ctx.get("dependencies", []),
                    "dependents": file_ctx.get("dependents", []),
                }
            except Exception as exc:
                logger.debug("KG context failed for %r: %s", fp, exc)
                context_per_file[fp] = {
                    "decisions": [],
                    "owners": [],
                    "dependencies": [],
                    "dependents": [],
                }

        return {"context_per_file": context_per_file}

    return gather_context


_GENERATE_PATH_SYSTEM = """\
You are a senior engineer creating a learning path for a new developer.
Order steps from foundational → specific.
Use "read" for utility/config files, "understand" for core logic, "review" for decision-heavy files.
Limit to 10 steps. Respond with ONLY a JSON array — no markdown, no prose."""

_GENERATE_PATH_USER_TMPL = """\
Task: {task_description}

Relevant files with context:
{file_context_block}

Produce a JSON array where each element has:
{{
  "step_number": <int>,
  "action": "<read|understand|review>",
  "file_path": "<path>",
  "focus_area": "<what to pay attention to>",
  "context": "<why this file matters for the task>",
  "related_decisions": [<list of decision titles, may be empty>],
  "expert_contact": "<name or null>"
}}"""


def _make_generate_path_node(llm_client):
    async def generate_path(state: OnboardingState) -> dict:
        task = state["task_description"]
        relevant_files = state.get("relevant_files", [])
        context_per_file = state.get("context_per_file", {})

        # Build a context block (max ~3000 chars)
        block_parts: list[str] = []
        char_budget = 3000

        for entry in relevant_files[:15]:
            fp = entry.get("file_path", "unknown")
            score = entry.get("relevance_score", 0.0)
            snippet = entry.get("snippet", "")[:200]
            ctx = context_per_file.get(fp, {})

            decisions = ctx.get("decisions", [])
            dec_titles = [
                d.get("title", "") for d in decisions[:3] if d.get("title")
            ]
            owners = ctx.get("owners", [])
            expert_names = [
                o.get("name", "") for o in owners[:2] if o.get("name")
            ]

            part_lines = [f"- {fp} (relevance={score:.2f})"]
            if snippet:
                part_lines.append(f"  snippet: {snippet}")
            if dec_titles:
                part_lines.append(f"  decisions: {', '.join(dec_titles)}")
            if expert_names:
                part_lines.append(f"  experts: {', '.join(expert_names)}")

            part = "\n".join(part_lines)
            if len("\n".join(block_parts)) + len(part) > char_budget:
                break
            block_parts.append(part)

        file_context_block = "\n".join(block_parts) or "(no files found)"

        messages = [
            {"role": "system", "content": _GENERATE_PATH_SYSTEM},
            {
                "role": "user",
                "content": _GENERATE_PATH_USER_TMPL.format(
                    task_description=task[:2000],
                    file_context_block=file_context_block,
                ),
            },
        ]

        try:
            response = await llm_client.complete(messages=messages, stream=False)
            learning_path = _extract_json_array(response.content, task)
        except Exception as exc:
            logger.warning("generate_path LLM failed (%s); using fallback", exc)
            top_file = relevant_files[0]["file_path"] if relevant_files else "unknown"
            learning_path = [
                {
                    "step_number": 1,
                    "action": "read",
                    "file_path": top_file,
                    "focus_area": "Start here",
                    "context": f"LLM unavailable. Task: {task[:200]}",
                    "related_decisions": [],
                    "expert_contact": None,
                }
            ]

        return {"learning_path": learning_path}

    return generate_path


# ── Graph builder ────────────────────────────────────────────────────────

def _build_graph(llm_client, embedding_service, vector_service, knowledge_graph):
    builder = StateGraph(OnboardingState)

    builder.add_node("parse_task", _make_parse_task_node(llm_client))
    builder.add_node(
        "find_relevant_code",
        _make_find_relevant_code_node(embedding_service, vector_service, knowledge_graph),
    )
    builder.add_node("gather_context", _make_gather_context_node(knowledge_graph))
    builder.add_node("generate_path", _make_generate_path_node(llm_client))

    builder.set_entry_point("parse_task")
    builder.add_edge("parse_task", "find_relevant_code")
    builder.add_edge("find_relevant_code", "gather_context")
    builder.add_edge("gather_context", "generate_path")
    builder.add_edge("generate_path", END)

    return builder.compile()


# ── Public class ─────────────────────────────────────────────────────────

class OnboardingAgent:
    """
    Wraps the compiled LangGraph for the onboarding copilot.

    Usage::

        agent = OnboardingAgent(llm_client, embedding_service, vector_service, knowledge_graph)
        steps = await agent.run(project_id="my-project", task_description="...")
    """

    def __init__(self, llm_client, embedding_service, vector_service, knowledge_graph=None):
        self._app = _build_graph(llm_client, embedding_service, vector_service, knowledge_graph)

    async def run(self, project_id: str, task_description: str) -> list[dict]:
        """
        Run the full onboarding pipeline and return a list of learning steps.

        Raises asyncio.TimeoutError (after 60 s) or any unhandled exception
        from the graph — callers should handle these.
        """
        initial_state: OnboardingState = {
            "project_id": project_id,
            "task_description": task_description,
            "extracted_concepts": {},
            "relevant_files": [],
            "context_per_file": {},
            "learning_path": [],
            "error": None,
        }
        result = await asyncio.wait_for(
            self._app.ainvoke(initial_state), timeout=60.0
        )
        return result.get("learning_path", [])
