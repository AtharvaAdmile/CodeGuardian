"""
Pydantic request / response schemas for the CodeGuardian REST API.

Covers:
  - /api/ask, /api/ask/stream  (query routes)
  - /api/analyze/*              (analysis routes)
  - /api/index, /api/index/status (indexing routes)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

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


class DecisionRef(BaseModel):
    """An architectural decision surfaced in the answer."""

    title: str = ""
    decision: str = ""
    source_ref: str = ""


class ExpertRef(BaseModel):
    """A developer identified as an expert for a retrieved file."""

    name: str = ""
    email: str = ""
    expertise_score: float = Field(0.0, ge=0.0, le=1.0)


class AskResponse(BaseModel):
    """JSON response for POST /api/ask."""

    answer: str
    sources: list[SourceRef] = Field(default_factory=list)
    confidence: float = Field(
        0.0, ge=0.0, le=1.0, description="Confidence extracted from LLM or mean chunk similarity."
    )
    decisions_referenced: list[DecisionRef] = Field(
        default_factory=list,
        description="Architectural decisions relevant to the answer.",
    )
    experts: list[ExpertRef] = Field(
        default_factory=list,
        description="Primary owners of the retrieved files.",
    )


class CGPilotMessage(BaseModel):
    """A compact chat history item for CG-pilot."""

    role: str = Field(..., description="user or assistant")
    content: str = Field(..., min_length=1)


class FileContextSchema(BaseModel):
    """An optional file attached as context for CG-pilot."""

    file_path: str = Field(..., description="Relative path to the file from project root.")


class CGPilotRequest(BaseModel):
    """POST /api/cg-pilot/chat"""

    project_id: str = Field(..., description="Project identifier.")
    project_path: str = Field(..., description="Absolute path to the project root.")
    message: str = Field(..., min_length=1)
    session_id: str | None = Field(
        None, description="Resume an existing chat session."
    )
    conversation_history: list[CGPilotMessage] = Field(default_factory=list)
    file_context: FileContextSchema | None = Field(
        None, description="Optional file to attach as context for the query."
    )


class CGPilotToolUse(BaseModel):
    """A tool call made while answering a CG-pilot message."""

    name: str
    summary: str = ""


class CGPilotStep(BaseModel):
    """A single step in the agentic reasoning loop."""

    round: int = Field(..., description="Round number (1-indexed).")
    action: str = Field(
        ..., description="One of: plan, tool_call, observation, final"
    )
    tool_name: str = ""
    tool_summary: str = ""
    message: str = ""


class CGPilotResponse(BaseModel):
    """Response from POST /api/cg-pilot/chat."""

    answer: str
    session_id: str = Field(..., description="Session ID for continuing the chat.")
    sources: list[SourceRef] = Field(default_factory=list)
    tools_used: list[CGPilotToolUse] = Field(default_factory=list)
    steps: list[CGPilotStep] = Field(default_factory=list)
    indexed: bool = True


class ChatSessionSummary(BaseModel):
    """Summary of a chat session for listing."""

    session_id: str
    project_id: str
    title: str = ""
    message_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class ChatSessionDetail(BaseModel):
    """Full chat session with messages."""

    session_id: str
    project_id: str
    title: str = ""
    messages: list[dict] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class ChatHistoryListResponse(BaseModel):
    """List of chat sessions for a project."""

    sessions: list[ChatSessionSummary] = Field(default_factory=list)
    total: int = 0


class DeleteSessionResponse(BaseModel):
    """Response from deleting a chat session."""

    success: bool = True
    message: str = "Session deleted."


class CGPilotStatusResponse(BaseModel):
    """GET /api/cg-pilot/status/{project_id}."""

    project_id: str
    indexed: bool
    ready: bool
    reason: str | None = None


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
    include_extensions: list[str] | None = Field(
        None, description="Only index files with these extensions."
    )
    include_directories: list[str] | None = Field(
        None, description="Only index files under these relative directory paths."
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
    """GET /api/index/status/{job_id} — tracks 2-phase progress."""

    job_id: str
    status: JobStatus = JobStatus.QUEUED

    # ── Phase 1: Code indexing ──────────────────────────────────────
    files_processed: int = 0
    files_total: int = 0
    chunks_created: int = 0
    current_file: str | None = None

    # ── Phase 2: Knowledge graph build ──────────────────────────────
    graph_status: str = Field(
        "pending",
        description="One of: pending, running, completed, failed, skipped",
    )
    graph_nodes: int = 0
    graph_edges: int = 0

    # ── Errors ──────────────────────────────────────────────────────
    errors: list[str] = Field(default_factory=list)
    error_message: str | None = None


class IndexHistoryEntry(BaseModel):
    """A single completed indexing run."""

    id: str
    date: str
    files: int
    chunks: int
    nodes: int
    edges: int
    status: str
    duration: str
    project_path: str


class ExtensionEstimate(BaseModel):
    """Files grouped by extension."""

    extension: str
    count: int
    total_lines: int
    estimated_chunks: int


class DirectoryEstimate(BaseModel):
    """Files grouped by directory."""

    path: str
    count: int
    total_lines: int
    estimated_chunks: int


class IndexEstimateResponse(BaseModel):
    """GET /api/index/estimate/{project_id}"""

    project_id: str
    project_path: str
    total_files: int
    total_lines: int
    estimated_total_chunks: int
    by_extension: list[ExtensionEstimate] = Field(default_factory=list)
    by_directory: list[DirectoryEstimate] = Field(default_factory=list)


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


# ═════════════════════════════════════════════════════════════════════════
# Impact Routes
# ═════════════════════════════════════════════════════════════════════════


class ImpactAnalyzeRequest(BaseModel):
    """POST /api/impact/analyze and POST /api/impact/saved"""

    project_path: str = Field(..., description="Absolute path to the project root.")
    file_path: str = Field(
        ...,
        description="File that was changed (project-relative or absolute path).",
    )
    diff: str | None = Field(
        None,
        description=(
            "Optional unified diff of the change. "
            "When provided, breaking-change detection runs automatically."
        ),
    )


class AffectedFileSchema(BaseModel):
    """A single file in the blast radius, with risk metadata."""

    file_path: str
    risk_score: float = Field(ge=0.0, le=1.0)
    distance: int = Field(ge=1)
    reason: str


class ImpactAnalyzeResponse(BaseModel):
    """Response from POST /api/impact/analyze."""

    changed_file: str
    total_affected: int = 0
    high_risk: list[AffectedFileSchema] = Field(default_factory=list)
    medium_risk: list[AffectedFileSchema] = Field(default_factory=list)
    low_risk: list[AffectedFileSchema] = Field(default_factory=list)
    affected_modules: list[str] = Field(default_factory=list)
    suggested_reviewers: list[str] = Field(default_factory=list)
    agent_summary: str = ""
    risk_assessment: str = ""
    recommendations: list[str] = Field(default_factory=list)
    validation_steps: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    generated_at: str = ""
    persisted: bool = False
    error: str | None = None


class BreakingChangesRequest(BaseModel):
    """POST /api/impact/breaking-changes"""

    old_content: str = Field(..., description="Source code of the original version.")
    new_content: str = Field(..., description="Source code of the modified version.")
    language: str = Field(
        ...,
        description=(
            "Source language: 'python', 'javascript', 'typescript', "
            "'js', 'ts', 'jsx', or 'tsx'."
        ),
    )


class BreakingChangeSchema(BaseModel):
    """A single detected breaking or non-breaking API change."""

    symbol: str
    change_type: str
    severity: str  # "breaking" | "non-breaking"
    old_signature: str | None = None
    new_signature: str | None = None
    description: str


class BreakingChangesResponse(BaseModel):
    """Response from POST /api/impact/breaking-changes."""

    changes: list[BreakingChangeSchema] = Field(default_factory=list)
    total_breaking: int = 0
    total_non_breaking: int = 0
    error: str | None = None


# ═════════════════════════════════════════════════════════════════════════
# Onboarding Routes
# ═════════════════════════════════════════════════════════════════════════


class OnboardingRequest(BaseModel):
    """POST /api/onboard/generate"""

    project_id: str
    task_description: str = Field(..., min_length=1)


class LearningStepSchema(BaseModel):
    """A single step in an onboarding learning path."""

    step_number: int
    action: str              # "read" | "understand" | "review"
    file_path: str
    focus_area: str
    context: str = ""
    related_decisions: list[str] = Field(default_factory=list)
    expert_contact: str | None = None


class OnboardingResponse(BaseModel):
    """Response from POST /api/onboard/generate."""

    learning_path: list[LearningStepSchema] = Field(default_factory=list)
    error: str | None = None


# ═════════════════════════════════════════════════════════════════════════
# Commit Review Routes
# ═════════════════════════════════════════════════════════════════════════


class CommitReviewRequest(BaseModel):
    """POST /api/review/status"""

    project_path: str = Field(..., description="Absolute path to project root.")
    history_limit: int = Field(10, ge=1, le=50)


class CommitRequest(BaseModel):
    """POST /api/review/commit"""

    project_path: str = Field(..., description="Absolute path to project root.")
    message: str
    history_limit: int = Field(10, ge=1, le=50)


class CommitFileChangeSchema(BaseModel):
    """A changed file in either git history or the working tree."""

    file_path: str = ""
    status: str = ""
    additions: int = 0
    deletions: int = 0
    staged: bool = False
    unstaged: bool = False
    untracked: bool = False
    diff: str = ""


class CommitHistoryEntrySchema(BaseModel):
    """A recent commit and the files it changed."""

    sha: str
    short_sha: str
    message: str
    author: str
    email: str = ""
    date: str
    files: list[CommitFileChangeSchema] = Field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    diff: str = ""


class CommitRecommendationSchema(BaseModel):
    """Commit readiness recommendation for the current working tree."""

    should_commit: bool = False
    title: str = ""
    reason: str = ""
    concerns: list[str] = Field(default_factory=list)
    suggested_message: str = ""


class CommitReviewResponse(BaseModel):
    """Response from POST /api/review/status."""

    project_path: str = ""
    branch: str = ""
    head_sha: str = ""
    is_git_repo: bool = False
    has_changes: bool = False
    staged_files: int = 0
    unstaged_files: int = 0
    untracked_files: int = 0
    uncommitted_files: list[CommitFileChangeSchema] = Field(default_factory=list)
    recent_commits: list[CommitHistoryEntrySchema] = Field(default_factory=list)
    summary: str = ""
    recommendation: CommitRecommendationSchema = Field(default_factory=CommitRecommendationSchema)
    error: str | None = None


class CommitActionResponse(BaseModel):
    """Response from POST /api/review/commit."""

    committed: bool = False
    commit_sha: str = ""
    message: str = ""
    status: CommitReviewResponse | None = None
    error: str | None = None


# ═════════════════════════════════════════════════════════════════════════
# Compliance Check Schemas
# ═════════════════════════════════════════════════════════════════════════


class ComplianceCheckType(BaseModel):
    """Describes one available compliance check type."""

    id: str
    name: str
    description: str
    category: str = "security"
    default_severity: str = "medium"


class ComplianceStep(BaseModel):
    """A single step in the agentic compliance check loop."""

    round: int = Field(..., description="Round number (1-indexed).")
    action: str = Field(
        ..., description="One of: plan, tool_call, observation, finding, check_complete, final"
    )
    check_type: str = ""
    tool_name: str = ""
    tool_summary: str = ""
    message: str = ""
    findings: list[ComplianceFinding] = Field(default_factory=list)


class ComplianceScanRequest(BaseModel):
    """POST /api/compliance/scan"""

    project_id: str = Field(..., description="Unique project identifier.")
    project_path: str = Field(..., description="Absolute path to the project root.")
    selected_checks: list[str] = Field(
        default_factory=lambda: [
            "secrets", "pii", "gdpr", "hipaa",
            "dangerous_funcs", "sql_injection",
        ],
        description="List of check type IDs to run.",
    )


class ComplianceFinding(BaseModel):
    """A single compliance violation found during scanning."""

    file_path: str = ""
    line: int = 0
    column: int = 0
    severity: str = "medium"
    category: str = "security"
    check_type: str = ""
    message: str = ""
    snippet: str = ""
    suggestion: str = ""


class ComplianceScanStatus(BaseModel):
    """Progress / status of an in-flight compliance scan job."""

    job_id: str = ""
    status: Literal["queued", "scanning", "completed", "failed", "cancelled"] = "queued"
    current_check: str | None = None
    files_scanned: int = 0
    files_total: int = 0
    total_violations: int = 0
    violation_counts: dict[str, int] = Field(
        default_factory=lambda: {"critical": 0, "high": 0, "medium": 0, "low": 0},
    )
    compliance_score: float | None = None
    steps: list[ComplianceStep] = Field(default_factory=list)
    error: str | None = None
    can_overwrite: bool = True


class ComplianceReport(BaseModel):
    """Final compliance scan report."""

    job_id: str = ""
    project_id: str = ""
    project_path: str = ""
    scanned_files: int = 0
    total_violations: int = 0
    violation_counts: dict[str, int] = Field(
        default_factory=lambda: {"critical": 0, "high": 0, "medium": 0, "low": 0},
    )
    compliance_score: float = 100.0
    passed: bool = True
    summary: str = ""
    violations: list[ComplianceFinding] = Field(default_factory=list)
    check_types_ran: list[str] = Field(default_factory=list)
    steps: list[ComplianceStep] = Field(default_factory=list)
    can_overwrite: bool = True


# Rebuild models that use forward references (needed with from __future__ import annotations)
ComplianceScanStatus.model_rebuild()
ComplianceReport.model_rebuild()
