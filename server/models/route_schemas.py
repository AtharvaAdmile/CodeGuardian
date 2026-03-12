"""
Pydantic request / response schemas for the CodeGuardian REST API.

Covers:
  - /api/ask, /api/ask/stream  (query routes)
  - /api/analyze/*              (analysis routes)
  - /api/index, /api/index/status (indexing routes)
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ═════════════════════════════════════════════════════════════════════════
# Query Routes
# ═════════════════════════════════════════════════════════════════════════


class AskRequest(BaseModel):
    """POST /api/ask  and  POST /api/ask/stream"""

    project_id: str = Field(
        ..., description="Project identifier (maps to a vector collection)."
    )
    question: str = Field(
        ..., min_length=1, description="Natural-language question about the codebase."
    )
    conversation_history: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "Optional prior messages in OpenAI chat format "
            '(e.g. [{"role": "user", "content": "…"}]).'
        ),
    )


class SourceRef(BaseModel):
    """A single source chunk referenced in the answer."""

    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    chunk_type: str | None = None
    relevance_score: float = 0.0


class AskResponse(BaseModel):
    """JSON response for POST /api/ask."""

    answer: str
    sources: list[SourceRef] = Field(default_factory=list)
    confidence: float = Field(
        0.0, ge=0.0, le=1.0, description="Mean similarity of top retrieved chunks."
    )


# ═════════════════════════════════════════════════════════════════════════
# Analysis Routes
# ═════════════════════════════════════════════════════════════════════════


class StructureRequest(BaseModel):
    """POST /api/analyze/structure"""

    project_path: str = Field(..., description="Absolute path to the project root.")


class StructureResponse(BaseModel):
    """Response from /api/analyze/structure."""

    project_path: str
    score: float = Field(0.0, description="Organisation score (0-10).")
    has_git: bool = False
    total_files: int = 0
    root_files: int = 0
    folders_count: int = 0
    error: str | None = None


class HealthRequest(BaseModel):
    """POST /api/analyze/health"""

    project_path: str = Field(..., description="Absolute path to the project root.")
    file_path: str = Field(..., description="File to analyse (absolute or relative).")


class HealthResponse(BaseModel):
    """Response from /api/analyze/health."""

    file_path: str
    health_score: float = 0.0
    complexity: dict[str, Any] = Field(default_factory=dict)
    churn: dict[str, Any] = Field(default_factory=dict)
    recommendation: dict[str, Any] = Field(default_factory=dict)
    is_hotspot: bool = False
    error: str | None = None


class DependencyRequest(BaseModel):
    """POST /api/analyze/dependencies"""

    project_path: str = Field(..., description="Absolute path to the project root.")
    file_path: str = Field(..., description="File to analyse (absolute or relative).")


class DependencyItem(BaseModel):
    """A single import / call / inheritance dependency."""

    name: str
    dependency_type: str  # "import" | "function_call" | "inheritance"


class DependencyResponse(BaseModel):
    """Response from /api/analyze/dependencies."""

    file_path: str
    language: str = "unknown"
    imports: list[str] = Field(default_factory=list)
    function_calls: list[str] = Field(default_factory=list)
    inheritance: list[str] = Field(default_factory=list)
    total_dependencies: int = 0
    error: str | None = None


# ═════════════════════════════════════════════════════════════════════════
# Indexing Routes
# ═════════════════════════════════════════════════════════════════════════


class IndexRequest(BaseModel):
    """POST /api/index"""

    project_id: str = Field(..., description="Unique project identifier.")
    project_path: str = Field(..., description="Absolute path to the project root.")
    force: bool = Field(
        False, description="Re-index even if project was already indexed."
    )


class IndexResponse(BaseModel):
    """Immediate response from POST /api/index (job queued)."""

    job_id: str
    status: str = "queued"
    message: str = "Indexing job has been queued."


class JobStatus(str, Enum):
    """Lifecycle states for an indexing job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class IndexStatus(BaseModel):
    """GET /api/index/status/{job_id} — tracks 3-phase progress."""

    job_id: str
    status: JobStatus = JobStatus.QUEUED

    # ── Phase 1: Code indexing (fast) ────────────────────────────────
    files_processed: int = 0
    files_total: int = 0
    chunks_created: int = 0

    # ── Phase 2: Expertise mapping (background) ─────────────────────
    expertise_status: str = Field(
        "pending",
        description="One of: pending, running, completed, failed, skipped",
    )
    expertise_files_mapped: int = 0

    # ── Phase 3: Decision extraction (background) ───────────────────
    decision_status: str = Field(
        "pending",
        description="One of: pending, running, completed, failed, skipped",
    )
    decisions_commits_processed: int = 0
    decisions_found: int = 0

    # ── Errors ──────────────────────────────────────────────────────
    errors: list[str] = Field(default_factory=list)
    error_message: str | None = None


# ═════════════════════════════════════════════════════════════════════════
# Extended Analysis Routes
# ═════════════════════════════════════════════════════════════════════════


class ComplianceRequest(BaseModel):
    """POST /api/analyze/compliance"""

    project_path: str = Field(..., description="Absolute path to the project root.")
    code_snippet: str = Field(..., min_length=1, description="Source code to scan.")


class ComplianceResponse(BaseModel):
    """Response from /api/analyze/compliance."""

    passed: bool = True
    violations: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    error: str | None = None


class RegulatoryComplianceRequest(BaseModel):
    """POST /api/analyze/regulatory-compliance"""

    project_path: str = Field(..., description="Absolute path to the project root.")
    file_path: str = Field(..., description="Path to the source file.")
    file_content: str = Field(..., min_length=1, description="Content of the file.")


class RegulatoryComplianceResponse(BaseModel):
    """Response from /api/analyze/regulatory-compliance."""

    passed: bool = False
    score: float = 0.0
    violations: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    error: str | None = None


class ExpertRequest(BaseModel):
    """POST /api/analyze/expert"""

    project_path: str = Field(..., description="Absolute path to the project root.")
    file_path: str = Field(..., description="File to find experts for.")


class ExpertResponse(BaseModel):
    """Response from /api/analyze/expert."""

    primary_expert: str | None = None
    backup: str | None = None
    experts: list[dict[str, Any]] = Field(default_factory=list)
    last_active: str | None = None
    file_path: str = ""
    error: str | None = None


class HistoryRequest(BaseModel):
    """POST /api/analyze/history"""

    project_path: str = Field(..., description="Absolute path to the project root.")
    file_path: str = Field(..., description="File to get history for.")
    line_start: int | None = Field(None, description="Starting line (1-indexed).")
    line_end: int | None = Field(None, description="Ending line (1-indexed).")


class HistoryResponse(BaseModel):
    """Response from /api/analyze/history."""

    file_path: str = ""
    history: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    churn: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class RuntimeRequest(BaseModel):
    """POST /api/analyze/runtime"""

    project_path: str = Field(..., description="Absolute path to the project root.")
    file_path: str = Field(..., description="File to check runtime stats for.")


class RuntimeResponse(BaseModel):
    """Response from /api/analyze/runtime."""

    file_path: str = ""
    available: bool = False
    error_rate: float | None = None
    avg_latency_ms: float | None = None
    alert_level: str = "none"
    last_error: str | None = None
    error: str | None = None


class ProjectDependenciesRequest(BaseModel):
    """POST /api/analyze/project-dependencies"""

    project_path: str = Field(..., description="Absolute path to the project root.")


class ProjectDependenciesResponse(BaseModel):
    """Response from /api/analyze/project-dependencies."""

    nodes: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, Any]] = Field(default_factory=list)
    total_files: int = 0
    total_links: int = 0
    error: str | None = None


class DocumentationGapsRequest(BaseModel):
    """POST /api/analyze/documentation-gaps"""

    project_path: str = Field(..., description="Absolute path to the project root.")
    file_path: str = Field(..., description="File to check for doc gaps.")


class DocumentationGapsResponse(BaseModel):
    """Response from /api/analyze/documentation-gaps."""

    file_path: str = ""
    elements: list[dict[str, Any]] = Field(default_factory=list)
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    total_elements: int = 0
    elements_with_gaps: int = 0
    average_score: float = 100.0
    quality_threshold: float = 70.0
    error: str | None = None


class TestabilityRequest(BaseModel):
    """POST /api/analyze/testability"""

    project_path: str = Field(..., description="Absolute path to the project root.")
    file_path: str = Field(..., description="File to analyze for testability.")


class TestabilityResponse(BaseModel):
    """Response from /api/analyze/testability."""

    file_path: str = ""
    testable_elements: list[dict[str, Any]] = Field(default_factory=list)
    total_elements: int = 0
    error: str | None = None


class RunTestsRequest(BaseModel):
    """POST /api/analyze/tests"""

    project_path: str = Field(..., description="Absolute path to the project root.")
    file_path: str | None = Field(None, description="Specific test file to run.")
    test_dir: str = Field("tests", description="Directory containing tests.")


class RunTestsResponse(BaseModel):
    """Response from /api/analyze/tests."""

    passed: bool = False
    results: dict[str, Any] = Field(default_factory=dict)
    output: str = ""
    error: str | None = None


class GenerateTestRequest(BaseModel):
    """POST /api/analyze/generate-test"""

    project_path: str = Field(..., description="Absolute path to the project root.")
    file_path: str = Field(..., description="Source file path (for language detection).")
    file_content: str = Field(..., min_length=1, description="Source file content.")


class GenerateTestResponse(BaseModel):
    """Response from /api/analyze/generate-test."""

    test_code: str | None = None
    language: str = "unknown"
    framework: str = ""
    suggested_test_path: str = ""
    success: bool = False
    error: str | None = None


class RunGeneratedTestRequest(BaseModel):
    """POST /api/analyze/run-test"""

    project_path: str = Field(..., description="Absolute path to the project root.")
    test_file_path: str = Field(..., description="Path to the generated test file.")


class RunGeneratedTestResponse(BaseModel):
    """Response from /api/analyze/run-test."""

    passed: bool = False
    file_path: str = ""
    output: str = ""
    error_message: str | None = None
    error: str | None = None
