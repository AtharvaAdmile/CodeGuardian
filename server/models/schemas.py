"""
Core Pydantic schemas shared across the CodeGuardian server.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Health ──────────────────────────────────────────────────────────────


class ComponentStatus(BaseModel):
    """Status of a single downstream dependency."""

    status: str = Field(
        ...,
        description="One of: ok, not_initialized, degraded, error",
        examples=["ok", "not_initialized"],
    )
    detail: str | None = Field(
        default=None,
        description="Optional human-readable detail about the component state.",
    )


class HealthStatus(BaseModel):
    """Aggregate health response returned by GET /api/health."""

    status: str = Field(
        ...,
        description="Overall status: healthy | degraded | unhealthy",
        examples=["healthy"],
    )
    components: dict[str, ComponentStatus] = Field(
        ...,
        description="Per-dependency status map.",
    )
    uptime_seconds: float = Field(
        ...,
        description="Seconds since server startup.",
        examples=[123.45],
    )


# ── Project Configuration ───────────────────────────────────────────────


class ProjectConfig(BaseModel):
    """
    Represents a project that CodeGuardian is tracking.

    Stored in the .codeguardian file at the project root or managed
    through the API.
    """

    project_path: str = Field(
        ...,
        description="Absolute path to the project root directory.",
    )
    project_name: str = Field(
        ...,
        description="Human-readable project name.",
    )
    languages: list[str] = Field(
        default_factory=list,
        description="Primary programming languages detected in the project.",
    )
    ignore_patterns: list[str] = Field(
        default_factory=lambda: [
            "__pycache__",
            "node_modules",
            ".git",
            "*.pyc",
            ".env",
        ],
        description="Glob patterns for files/dirs to exclude from analysis.",
    )
    indexed: bool = Field(
        default=False,
        description="Whether the project has been indexed in the vector store.",
    )
