"""
Health-check endpoint.

Returns the overall server status and the readiness of each
downstream dependency (vector store, LLM, Supabase).
"""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from server.models.schemas import ComponentStatus, HealthStatus

router = APIRouter(prefix="/api", tags=["health"])


def _check_component(resource: object | None) -> ComponentStatus:
    """Return a ComponentStatus based on whether a resource has been wired in."""
    if resource is None:
        return ComponentStatus(status="not_initialized")
    # For generic components without specific health checks
    return ComponentStatus(status="ok")


async def _check_llm(request: Request) -> ComponentStatus:
    """Check the NIM LLM client health with an actual API ping."""
    llm_client = getattr(request.app.state, "llm_client", None)

    if llm_client is None:
        return ComponentStatus(
            status="not_initialized",
            detail="NVIDIA_NIM_API_KEY not set or client not created",
        )

    try:
        healthy = await llm_client.is_healthy()
    except Exception:
        healthy = False

    last_at = llm_client.last_healthy_at
    detail = None
    if last_at:
        dt = datetime.fromtimestamp(last_at, tz=timezone.utc)
        detail = f"last_healthy_at={dt.isoformat()}"

    if healthy:
        return ComponentStatus(status="ok", detail=detail)
    return ComponentStatus(
        status="error",
        detail=detail or "Health check failed — NIM API unreachable",
    )


@router.get("/health", response_model=HealthStatus)
async def health_check(request: Request) -> HealthStatus:
    """
    GET /api/health

    Returns the aggregate health status plus per-component breakdown.
    """
    boot_time: float = getattr(request.app.state, "boot_time", time.time())
    uptime = time.time() - boot_time

    components = {
        "vector_store": _check_component(
            getattr(request.app.state, "vector_store", None)
        ),
        "llm": await _check_llm(request),
        "supabase": _check_component(None),  # Not wired yet
    }

    # Derive aggregate status
    statuses = [c.status for c in components.values()]
    if all(s == "ok" for s in statuses):
        overall = "healthy"
    elif any(s == "error" for s in statuses):
        overall = "unhealthy"
    else:
        overall = "degraded"

    return HealthStatus(
        status=overall,
        components=components,
        uptime_seconds=round(uptime, 2),
    )
