"""
Query routes — RAG-powered Q&A over indexed codebases.

POST /api/ask         → JSON answer with sources
POST /api/ask/stream  → Server-Sent Events stream
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from server.models.route_schemas import AskRequest, AskResponse, SourceRef

logger = logging.getLogger("codeguardian.routes.query")

router = APIRouter(prefix="/api", tags=["query"])

# ── Defaults ────────────────────────────────────────────────────────────
_TOP_K = 10
_SYSTEM_PROMPT = (
    "You are CodeGuardian, an AI assistant that answers questions about "
    "a codebase using retrieved source code context. Base your answers "
    "strictly on the provided code chunks. If the context is insufficient, "
    "say so clearly.\n\n"
    "### Retrieved Code Context\n{context}"
)


# ── Helpers ─────────────────────────────────────────────────────────────


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

    return embedding, vector, llm


async def _retrieve_context(
    embedding_service,
    vector_service,
    project_id: str,
    question: str,
) -> tuple[list[SourceRef], str, float]:
    """Embed the question, search vectors, return (sources, context_text, confidence)."""
    query_embedding = await embedding_service.embed_query(question)

    results = await vector_service.search(
        project_id=project_id,
        query_embedding=query_embedding,
        top_k=_TOP_K,
    )

    sources: list[SourceRef] = []
    context_parts: list[str] = []

    for r in results:
        meta = r.metadata or {}
        sources.append(
            SourceRef(
                file_path=meta.get("file_path", "unknown"),
                start_line=meta.get("start_line"),
                end_line=meta.get("end_line"),
                chunk_type=meta.get("chunk_type"),
                relevance_score=round(r.score, 4),
            )
        )
        header = meta.get("file_path", "unknown")
        if meta.get("start_line"):
            header += f":{meta['start_line']}"
        context_parts.append(f"```\n# {header}\n{r.text}\n```")

    context_text = "\n\n".join(context_parts) if context_parts else "(no context found)"
    confidence = (
        round(sum(s.relevance_score for s in sources) / len(sources), 4)
        if sources
        else 0.0
    )

    return sources, context_text, confidence


def _build_messages(
    context_text: str,
    question: str,
    conversation_history: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Assemble the chat prompt with system context + history + question."""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT.format(context=context_text)},
    ]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": question})
    return messages


# ── Endpoints ───────────────────────────────────────────────────────────


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, request: Request) -> AskResponse:
    """
    Embed the question, retrieve relevant code chunks, and generate
    an LLM answer grounded in the retrieved context.
    """
    embedding_service, vector_service, llm_client = _get_services(request)

    try:
        sources, context_text, confidence = await _retrieve_context(
            embedding_service, vector_service, body.project_id, body.question
        )

        messages = _build_messages(
            context_text, body.question, body.conversation_history
        )

        response = await llm_client.complete(messages=messages, stream=False)

        return AskResponse(
            answer=response.content,
            sources=sources,
            confidence=confidence,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error in /api/ask")
        raise HTTPException(500, f"Query failed: {exc}") from exc


@router.post("/ask/stream")
async def ask_stream(body: AskRequest, request: Request) -> StreamingResponse:
    """
    Same retrieval pipeline as /api/ask, but returns the answer as
    Server-Sent Events (SSE).

    Event types:
      data: {"type": "source", "source": {...}}    — one per retrieved chunk
      data: {"type": "chunk",  "content": "..."}   — streamed answer tokens
      data: {"type": "done"}                       — signals completion
    """
    embedding_service, vector_service, llm_client = _get_services(request)

    async def _event_generator() -> AsyncGenerator[str, None]:
        try:
            sources, context_text, _confidence = await _retrieve_context(
                embedding_service, vector_service, body.project_id, body.question
            )

            # Emit source references first
            for src in sources:
                event = {"type": "source", "source": src.model_dump()}
                yield f"data: {json.dumps(event)}\n\n"

            # Stream the LLM answer
            messages = _build_messages(
                context_text, body.question, body.conversation_history
            )

            stream = await llm_client.complete(messages=messages, stream=True)

            async for chunk in stream:
                if chunk.content:
                    event = {"type": "chunk", "content": chunk.content}
                    yield f"data: {json.dumps(event)}\n\n"

            # Done sentinel
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as exc:
            logger.exception("Error in /api/ask/stream")
            error_event = {"type": "error", "message": str(exc)}
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
