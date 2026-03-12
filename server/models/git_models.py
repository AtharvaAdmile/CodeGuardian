"""
Git-related data models for CodeGuardian's history indexer.

Lightweight dataclasses for blame entries, commit metadata, expertise
mapping, and extracted architectural decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


# ── Git History Models ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class BlameEntry:
    """A single blame segment from ``git blame``."""

    author: str
    email: str
    date: datetime
    commit_sha: str
    line_range: tuple[int, int]  # (start_line, end_line) 1-indexed


@dataclass(frozen=True, slots=True)
class CommitInfo:
    """Metadata for a single git commit."""

    sha: str
    author: str
    email: str
    message: str
    date: datetime
    files_changed: list[str] = field(default_factory=list)


# ── Expertise Mapping ────────────────────────────────────────────────────


@dataclass(slots=True)
class ExpertiseEntry:
    """Aggregated authorship stats for a single file–author pair."""

    file_path: str
    author: str
    email: str
    commit_count: int
    last_active: datetime


# ── Decision Extraction ──────────────────────────────────────────────────


@dataclass(slots=True)
class Decision:
    """
    An architectural decision extracted from a commit or PR comment.

    ``confidence`` is a 0.0–1.0 score assigned by the LLM indicating how
    certain it is that this is a genuine architectural decision rather
    than routine code commentary.
    """

    title: str
    context: str
    decision: str
    reasoning: str
    source_type: str  # "commit" | "pr_comment"
    source_ref: str   # commit SHA or PR URL/number
    confidence: float = 0.0
