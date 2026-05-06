"""
Query routes — RAG-powered Q&A over indexed codebases.

POST /api/ask         → JSON answer with sources, decisions, experts
POST /api/ask/stream  → Server-Sent Events stream
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from server.models.route_schemas import (
    AskRequest,
    AskResponse,
    DecisionRef,
    ExpertRef,
    SourceRef,
)

logger = logging.getLogger("codeguardian.routes.query")

router = APIRouter(prefix="/api", tags=["query"])

# ── Constants ────────────────────────────────────────────────────────────
_TOP_K = 10
_DECISION_TRIGGER_WORDS = frozenset({"why", "who", "decision", "reason"})

_SYSTEM_PROMPT = """\
You are CodeGuardian, an AI assistant with deep knowledge of this codebase.
You have access to:
- Code snippets from the indexed codebase
- Architectural decisions — the "why" behind design choices
- Author expertise — who knows what

When answering:
- Cite specific files and line numbers
- If architectural decisions are relevant, mention them
- If you reference a decision, name who made it and when
- Provide a confidence score (0.0-1.0) based on how well the retrieved \
context covers the question
- If you're uncertain, say so explicitly

FORMAT your answer as:
[Answer text with citations like (file.py:23-45)]
Confidence: [0.0-1.0]

### Retrieved Code Context
{code_context}{decisions_context}{graph_context}"""

# Matches "Confidence: 0.85" anywhere in the response
_CONFIDENCE_RE = re.compile(r"[Cc]onfidence:\s*([0-1](?:\.\d+)?)")
# Matches citations like (server/app.py:23-45) or (app.py:10)
_CITATION_RE = re.compile(
    r"\(([^)\s]+\.(?:py|ts|tsx|js|jsx)):(\d+)(?:-(\d+))?\)"
)


# ── Service access ───────────────────────────────────────────────────────

def _get_services(request: Request):
    """Extract shared services from app.state, raising 503 if unavailable."""
    embedding = getattr(request.app.state, "embedding_service", None)
    vector = getattr(request.app.state, "vector_service", None)
    llm = getattr(request.app.state, "llm_client", None)

    if embedding is None:
        raise HTTPException(503, "Embedding service is not initialised.")
    if vector is None:
        raise HTTPException(503, "Vector service is not initialised.")
    if llm is None:
        raise HTTPException(503, "LLM client is not initialised.")

    # Optional — degrade gracefully when unavailable
    kg = getattr(request.app.state, "knowledge_graph", None)
    decision_svc = getattr(request.app.state, "decision_service", None)

    return embedding, vector, llm, kg, decision_svc


# ── Step 1-2: Vector retrieval ───────────────────────────────────────────

async def _retrieve_chunks(
    embedding_service,
    vector_service,
    project_id: str,
    question: str,
) -> tuple[list[SourceRef], list[str], str, list[float], float]:
    """
    Embed *question* and search the vector store.

    Returns:
        (sources, unique_file_paths, code_context_text, query_embedding, base_confidence)
    """
    query_embedding: list[float] = await embedding_service.embed_query(question)

    results = await vector_service.search(
        project_id=project_id,
        query_embedding=query_embedding,
        top_k=_TOP_K,
    )

    sources: list[SourceRef] = []
    context_parts: list[str] = []
    seen_paths: dict[str, bool] = {}  # dict preserves insertion order

    for r in results:
        meta = r.metadata or {}
        fp = meta.get("file_path", "unknown")
        sources.append(
            SourceRef(
                file_path=fp,
                start_line=meta.get("start_line"),
                end_line=meta.get("end_line"),
                chunk_type=meta.get("chunk_type"),
                relevance_score=round(r.score, 4),
            )
        )
        header = fp
        if meta.get("start_line"):
            header += f":{meta['start_line']}"
        context_parts.append(f"```\n# {header}\n{r.text}\n```")
        seen_paths[fp] = True

    code_context = (
        "\n\n".join(context_parts) if context_parts else "(no context found)"
    )
    base_confidence = (
        round(sum(s.relevance_score for s in sources) / len(sources), 4)
        if sources
        else 0.0
    )

    return sources, list(seen_paths), code_context, query_embedding, base_confidence


# ── Step 3: Knowledge graph enrichment ──────────────────────────────────

def _enrich_with_kg(
    kg,
    file_paths: list[str],
) -> tuple[str, list[dict], list[ExpertRef]]:
    """
    For each retrieved file, pull decisions, owners, and module from the
    knowledge graph.

    Returns:
        (graph_context_block, kg_decisions_list, experts_list)
    """
    if kg is None or kg.is_empty():
        return "", [], []

    all_decisions: list[dict] = []
    all_experts: list[ExpertRef] = []
    seen_decision_ids: set[str] = set()
    seen_expert_names: set[str] = set()
    graph_lines: list[str] = []

    for fp in file_paths:
        ctx = kg.get_file_context(fp)

        # Collect decisions affecting this file
        for dec in ctx.get("decisions", []):
            key = dec.get("decision_id") or dec.get("title", "")
            if key and key not in seen_decision_ids:
                seen_decision_ids.add(key)
                all_decisions.append(dec)

        # Collect primary owners
        for owner in ctx.get("owners", []):
            name = owner.get("name", "")
            if name and name not in seen_expert_names:
                seen_expert_names.add(name)
                all_experts.append(
                    ExpertRef(
                        name=name,
                        email=owner.get("email", ""),
                        expertise_score=0.8,
                    )
                )

        # Module name derived from directory
        mod_name = str(Path(fp).parent) or "<root>"

        parts = [f"File: {fp}", f"Module: {mod_name}"]
        if ctx.get("owners"):
            names = ", ".join(
                o.get("name", "") for o in ctx["owners"] if o.get("name")
            )
            if names:
                parts.append(f"Owner: {names}")
        if ctx.get("decisions"):
            titles = ", ".join(
                d.get("title", "") for d in ctx["decisions"] if d.get("title")
            )
            if titles:
                parts.append(f"Decisions: {titles}")
        graph_lines.append(" | ".join(parts))

    graph_context = ""
    if graph_lines:
        graph_context = "\n\n### Knowledge Graph Context\n" + "\n".join(graph_lines)

    return graph_context, all_decisions, all_experts


# ── Step 4: Semantic decision search ────────────────────────────────────

async def _maybe_search_decisions(
    decision_svc,
    project_id: str,
    question: str,
    query_embedding: list[float],
    exclude_ids: set[str],
) -> list[dict]:
    """
    If the question contains a trigger word (why/who/decision/reason),
    perform a semantic search over the decisions store and return up to 3
    results not already in *exclude_ids*.
    """
    q_lower = question.lower()
    if not any(w in q_lower for w in _DECISION_TRIGGER_WORDS):
        return []
    if decision_svc is None:
        return []

    try:
        results = await decision_svc.search_decisions(
            project_id=project_id,
            query_embedding=query_embedding,
            top_k=5,
        )
        out: list[dict] = []
        for r in results:
            key = str(r.id or r.title or "")
            if key in exclude_ids:
                continue
            out.append(
                {
                    "title": r.title or "",
                    "decision": r.decision or "",
                    "reasoning": r.reasoning or "",
                    "source_ref": "",
                    "similarity": round(r.similarity or 0.0, 4),
                }
            )
            if len(out) >= 3:
                break
        return out
    except Exception as exc:
        logger.warning("Decision semantic search failed (non-fatal): %s", exc)
        return []


# ── Context assembly ─────────────────────────────────────────────────────

def _format_decisions_block(
    kg_decisions: list[dict],
    semantic_decisions: list[dict],
) -> str:
    """Render all decisions into a text block for the system prompt."""
    combined = kg_decisions + semantic_decisions
    if not combined:
        return ""

    lines = ["\n\n### Architectural Decisions"]
    for d in combined:
        title = d.get("title") or "Untitled"
        lines.append(f"\n**{title}**")
        if d.get("context"):
            lines.append(f"  Context: {d['context']}")
        body = d.get("decision") or d.get("reasoning") or ""
        if body:
            lines.append(f"  Decision: {body}")
        if d.get("source_ref"):
            lines.append(f"  Source: {d['source_ref']}")
    return "\n".join(lines)


def _build_messages(
    code_context: str,
    decisions_context: str,
    graph_context: str,
    question: str,
    conversation_history: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Build LLM messages with system prompt and conversation history."""
    system_content = _SYSTEM_PROMPT.format(
        code_context=code_context,
        decisions_context=decisions_context,
        graph_context=graph_context,
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": question})
    return messages


# ── Response parsing ─────────────────────────────────────────────────────

def _parse_llm_response(
    raw: str,
    vector_sources: list[SourceRef],
) -> tuple[str, float, list[SourceRef]]:
    """
    Extract the answer text, confidence score, and any additional file
    citations from the raw LLM output.

    Returns:
        (answer_text, confidence, merged_sources)
    """
    # Extract confidence score
    confidence = 0.0
    m = _CONFIDENCE_RE.search(raw)
    if m:
        try:
            confidence = min(1.0, max(0.0, float(m.group(1))))
        except ValueError:
            pass

    # Remove only the "Confidence: X.XX" line(s) from the displayed answer
    # Split into lines, filter out confidence lines, rejoin
    lines = raw.split('\n')
    filtered_lines = [line for line in lines if not _CONFIDENCE_RE.match(line.strip())]
    answer = '\n'.join(filtered_lines).strip()

    # Collect any cited file:line references not already in vector sources
    existing_paths = {s.file_path for s in vector_sources}
    extra: list[SourceRef] = []
    for cm in _CITATION_RE.finditer(raw):
        fp = cm.group(1)
        start = int(cm.group(2))
        end = int(cm.group(3)) if cm.group(3) else start
        if fp not in existing_paths:
            extra.append(SourceRef(file_path=fp, start_line=start, end_line=end))
            existing_paths.add(fp)

    return answer, confidence, vector_sources + extra


def _to_decision_refs(
    kg_decisions: list[dict],
    semantic_decisions: list[dict],
) -> list[DecisionRef]:
    """Convert decision dicts to DecisionRef objects."""
    return [
        DecisionRef(
            title=d.get("title", ""),
            decision=d.get("decision") or d.get("reasoning", ""),
            source_ref=d.get("source_ref", ""),
        )
        for d in kg_decisions + semantic_decisions
    ]


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, request: Request) -> AskResponse:
    """
    Embed the question, retrieve relevant code chunks, enrich with knowledge
    graph context and architectural decisions, then generate an LLM answer.
    """
    embedding_service, vector_service, llm_client, kg, decision_svc = _get_services(
        request
    )

    try:
        # 1 & 2: Embed + vector search
        sources, file_paths, code_context, query_embedding, base_confidence = (
            await _retrieve_chunks(
                embedding_service, vector_service, body.project_id, body.question
            )
        )

        # 3: Knowledge graph enrichment per retrieved file
        graph_context, kg_decisions, experts = _enrich_with_kg(kg, file_paths)

        # 4: Optional semantic decision search
        kg_decision_ids = {
            d.get("decision_id") or d.get("title", "") for d in kg_decisions
        }
        semantic_decisions = await _maybe_search_decisions(
            decision_svc,
            body.project_id,
            body.question,
            query_embedding,
            kg_decision_ids,
        )

        # 5: Build prompt and call LLM
        decisions_context = _format_decisions_block(kg_decisions, semantic_decisions)
        messages = _build_messages(
            code_context,
            decisions_context,
            graph_context,
            body.question,
            body.conversation_history,
        )
        response = await llm_client.complete(messages=messages, stream=False)

        # 6: Parse LLM response
        answer, llm_confidence, merged_sources = _parse_llm_response(
            response.content, sources
        )
        confidence = llm_confidence if llm_confidence > 0 else base_confidence

        # 7: Return enriched response
        return AskResponse(
            answer=answer,
            sources=merged_sources,
            confidence=confidence,
            decisions_referenced=_to_decision_refs(kg_decisions, semantic_decisions),
            experts=experts,
        )

    except Exception as exc:
        logger.exception("Error in /api/ask")
        raise HTTPException(500, f"Query failed: {exc}") from exc


@router.post("/ask/stream")
async def ask_stream(body: AskRequest, request: Request) -> StreamingResponse:
    """
    Same enriched retrieval pipeline as /api/ask, but returns the answer as
    Server-Sent Events (SSE).

    Event sequence:
      data: {"type": "source",   "source": {...}}
          — one per retrieved chunk
      data: {"type": "chunk",    "content": "..."}
          — streamed answer tokens
      data: {"type": "metadata", "decisions": [...], "experts": [...]}
          — architectural decisions and file experts (final, before done)
      data: {"type": "done"}
          — signals completion
    """
    embedding_service, vector_service, llm_client, kg, decision_svc = _get_services(
        request
    )

    async def _event_generator() -> AsyncGenerator[str, None]:
        """SSE event generator for streaming response."""
        try:
            # 1 & 2: Embed + vector search
            sources, file_paths, code_context, query_embedding, _ = (
                await _retrieve_chunks(
                    embedding_service, vector_service, body.project_id, body.question
                )
            )

            # Emit source references up front
            for src in sources:
                yield f"data: {json.dumps({'type': 'source', 'source': src.model_dump()})}\n\n"

            # 3: Knowledge graph enrichment
            graph_context, kg_decisions, experts = _enrich_with_kg(kg, file_paths)

            # 4: Optional semantic decision search
            kg_decision_ids = {
                d.get("decision_id") or d.get("title", "") for d in kg_decisions
            }
            semantic_decisions = await _maybe_search_decisions(
                decision_svc,
                body.project_id,
                body.question,
                query_embedding,
                kg_decision_ids,
            )

            # 5: Build prompt and stream answer tokens
            decisions_context = _format_decisions_block(kg_decisions, semantic_decisions)
            messages = _build_messages(
                code_context,
                decisions_context,
                graph_context,
                body.question,
                body.conversation_history,
            )
            stream = await llm_client.complete(messages=messages, stream=True)

            async for chunk in stream:
                if chunk.content:
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk.content})}\n\n"

            # Final metadata event — decisions + experts
            dec_refs = [
                {
                    "title": d.get("title", ""),
                    "decision": d.get("decision") or d.get("reasoning", ""),
                    "source_ref": d.get("source_ref", ""),
                }
                for d in kg_decisions + semantic_decisions
            ]
            expert_refs = [e.model_dump() for e in experts]
            yield f"data: {json.dumps({'type': 'metadata', 'decisions': dec_refs, 'experts': expert_refs})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as exc:
            logger.exception("Error in /api/ask/stream")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
