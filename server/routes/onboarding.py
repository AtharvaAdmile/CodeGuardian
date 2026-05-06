"""
Onboarding Copilot route.

POST /api/onboard/generate  — convert a task description into an ordered
                              learning path enriched with KG context.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from server.models.route_schemas import OnboardingRequest, OnboardingResponse

logger = logging.getLogger("codeguardian.routes.onboarding")

router = APIRouter(prefix="/api/onboard", tags=["onboarding"])


@router.post("/generate", response_model=OnboardingResponse)
async def generate_onboarding_path(
    body: OnboardingRequest, request: Request
) -> OnboardingResponse:
    """
    Generate a learning path for a developer picking up a new task.

    Requires llm_client, embedding_service, and vector_service to be
    initialised (returns 503 if any are missing).
    knowledge_graph is optional — omitting it degrades enrichment gracefully.
    """
    llm_client = getattr(request.app.state, "llm_client", None)
    embedding_service = getattr(request.app.state, "embedding_service", None)
    vector_service = getattr(request.app.state, "vector_service", None)

    if llm_client is None:
        raise HTTPException(503, "LLM client is not initialised.")
    if embedding_service is None:
        raise HTTPException(503, "Embedding service is not initialised.")
    if vector_service is None:
        raise HTTPException(503, "Vector service is not initialised.")

    knowledge_graph = getattr(request.app.state, "knowledge_graph", None)

    from server.agents.onboarding_agent import OnboardingAgent

    agent = OnboardingAgent(
        llm_client=llm_client,
        embedding_service=embedding_service,
        vector_service=vector_service,
        knowledge_graph=knowledge_graph,
    )

    try:
        learning_path = await agent.run(
            project_id=body.project_id,
            task_description=body.task_description,
        )
        return OnboardingResponse(learning_path=learning_path)

    except asyncio.TimeoutError:
        logger.warning("Onboarding agent timed out for project %r", body.project_id)
        raise HTTPException(504, "Onboarding agent timed out after 180 seconds.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error in /api/onboard/generate")
        raise HTTPException(500, f"Onboarding generation failed: {exc}") from exc
