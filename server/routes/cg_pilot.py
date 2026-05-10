"""
CG-pilot routes.

The chatbot is available only after the selected project has an indexed
Chroma collection. The LLM is OpenAI-powered, while retrieval remains
grounded in CodeGuardian's existing index plus constrained file tools.

Chat sessions are persisted to ``.codeguardian/chat_history/`` so users
can revisit and continue previous conversations.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger("codeguardian.routes.cg_pilot")

from server.models.route_schemas import (
    CGPilotMessage,
    CGPilotRequest,
    CGPilotResponse,
    CGPilotStatusResponse,
    ChatHistoryListResponse,
    ChatSessionDetail,
    DeleteSessionResponse,
)

router = APIRouter(prefix="/api/cg-pilot", tags=["cg-pilot"])


def _is_indexed(request: Request, project_id: str) -> bool:
    vector = getattr(request.app.state, "vector_service", None)
    if vector is None:
        return False
    return bool(vector.has_project_index(project_id))


def _get_history(request: Request):
    return getattr(request.app.state, "chat_history_service", None)


# ── Status ─────────────────────────────────────────────────────────────────


@router.get("/status/{project_id}", response_model=CGPilotStatusResponse)
async def cg_pilot_status(project_id: str, request: Request) -> CGPilotStatusResponse:
    """Return whether CG-pilot can answer questions for a project."""
    service = getattr(request.app.state, "cg_pilot_service", None)
    indexed = _is_indexed(request, project_id)

    if service is None:
        return CGPilotStatusResponse(
            project_id=project_id,
            indexed=indexed,
            ready=False,
            reason="NVIDIA_NIM_API_KEY is not configured.",
        )
    if not indexed:
        return CGPilotStatusResponse(
            project_id=project_id,
            indexed=False,
            ready=False,
            reason="Project indexing must complete before CG-pilot can answer.",
        )

    return CGPilotStatusResponse(project_id=project_id, indexed=True, ready=True)


# ── Chat ────────────────────────────────────────────────────────────────────


@router.post("/chat", response_model=CGPilotResponse)
async def cg_pilot_chat(body: CGPilotRequest, request: Request) -> CGPilotResponse:
    """Ask CG-pilot a project-grounded question. Sessions are auto-created."""
    service = getattr(request.app.state, "cg_pilot_service", None)
    if service is None:
        raise HTTPException(503, "CG-pilot is not initialised. Set NVIDIA_NIM_API_KEY.")

    project_root = Path(body.project_path).expanduser()
    if not project_root.exists() or not project_root.is_dir():
        raise HTTPException(404, f"Project path not found: {body.project_path}")

    if not _is_indexed(request, body.project_id):
        raise HTTPException(
            409,
            "Project indexing must complete before CG-pilot can answer.",
        )

    history_svc = _get_history(request)
    session_id = body.session_id

    # ── Resolve session ──────────────────────────────────────────────
    if history_svc:
        if session_id:
            existing = history_svc.get_session(body.project_id, session_id)
            if existing is None:
                raise HTTPException(404, f"Session {session_id} not found.")
        else:
            title = body.message[:80]
            session_id = history_svc.create_session(body.project_id, title)

        # Persist user message immediately
        history_svc.append_message(
            body.project_id, session_id, "user", body.message,
        )

    file_context_dict = body.file_context.model_dump() if body.file_context else None

    try:
        answer, sources, tools_used, steps = await service.chat(
            project_id=body.project_id,
            project_path=body.project_path,
            message=body.message,
            conversation_history=body.conversation_history,
            file_context=file_context_dict,
        )

        # Persist assistant response
        if history_svc:
            history_svc.append_message(
                body.project_id,
                session_id,
                "assistant",
                answer,
                sources=[s.model_dump() for s in sources],
                tools_used=[t.model_dump() for t in tools_used],
                steps=[s.model_dump() for s in steps],
            )

        return CGPilotResponse(
            answer=answer,
            session_id=session_id,
            sources=sources,
            tools_used=tools_used,
            steps=steps,
            indexed=True,
        )
    except NotImplementedError as exc:
        raise HTTPException(501, str(exc))
    except Exception as exc:
        logger.error(f"CG-pilot chat failed: {exc}")
        raise HTTPException(500, f"CG-pilot error: {str(exc)[:200]}")


# ── History ─────────────────────────────────────────────────────────────────


@router.get("/history/{project_id}", response_model=ChatHistoryListResponse)
async def list_sessions(project_id: str, request: Request) -> ChatHistoryListResponse:
    """List all chat sessions for a project."""
    history_svc = _get_history(request)
    if history_svc is None:
        return ChatHistoryListResponse(sessions=[])
    sessions = history_svc.get_sessions(project_id)
    return ChatHistoryListResponse(
        sessions=sessions,
        total=len(sessions),
    )


@router.get("/history/{project_id}/{session_id}", response_model=ChatSessionDetail)
async def get_session(
    project_id: str, session_id: str, request: Request
) -> ChatSessionDetail:
    """Get a full chat session with all messages."""
    history_svc = _get_history(request)
    if history_svc is None:
        raise HTTPException(404, "Chat history not available.")
    session = history_svc.get_session(project_id, session_id)
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found.")
    return ChatSessionDetail(**session)


@router.delete(
    "/history/{project_id}/{session_id}",
    response_model=DeleteSessionResponse,
)
async def delete_session_route(
    project_id: str, session_id: str, request: Request
) -> DeleteSessionResponse:
    """Delete a chat session."""
    history_svc = _get_history(request)
    if history_svc is None:
        raise HTTPException(404, "Chat history not available.")
    ok = history_svc.delete_session(project_id, session_id)
    if not ok:
        raise HTTPException(404, f"Session {session_id} not found.")
    return DeleteSessionResponse(success=True, message="Session deleted.")
