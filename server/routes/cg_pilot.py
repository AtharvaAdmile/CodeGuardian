"""
CG-pilot routes.

The chatbot is available only after the selected project has an indexed
Chroma collection. The LLM is OpenAI-powered, while retrieval remains
grounded in CodeGuardian's existing index plus constrained file tools.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger("codeguardian.routes.cg_pilot")

from server.models.route_schemas import (
    CGPilotRequest,
    CGPilotResponse,
    CGPilotStatusResponse,
)

router = APIRouter(prefix="/api/cg-pilot", tags=["cg-pilot"])


def _is_indexed(request: Request, project_id: str) -> bool:
    vector = getattr(request.app.state, "vector_service", None)
    if vector is None:
        return False
    return bool(vector.has_project_index(project_id))


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


@router.post("/chat", response_model=CGPilotResponse)
async def cg_pilot_chat(body: CGPilotRequest, request: Request) -> CGPilotResponse:
    """Ask CG-pilot a project-grounded question."""
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

    try:
        answer, sources, tools_used, steps = await service.chat(
            project_id=body.project_id,
            project_path=body.project_path,
            message=body.message,
            conversation_history=body.conversation_history,
        )

        return CGPilotResponse(
            answer=answer,
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
