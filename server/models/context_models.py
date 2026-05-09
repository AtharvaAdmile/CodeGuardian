"""
Context-YAML data models.

Dataclasses representing directory context stored in .context.yaml files.
Used by ContextService and RetrievalService.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

import yaml


@dataclass
class FileEntry:
    """Represents a file within a directory context."""
    name: str
    purpose: str
    type: str
    key_apis: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> FileEntry:
        return cls(
            name=data.get("name", ""),
            purpose=data.get("purpose", ""),
            type=data.get("type", "unknown"),
            key_apis=data.get("key_apis", []),
        )


@dataclass
class SubdirectoryEntry:
    """Represents a subdirectory within a directory context."""
    name: str
    purpose: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> SubdirectoryEntry:
        return cls(
            name=data.get("name", ""),
            purpose=data.get("purpose", ""),
        )


@dataclass
class RecentChange:
    """Represents a committed change to this directory."""
    commit: str
    message: str
    files: list[str]
    date: str
    author: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> RecentChange:
        return cls(
            commit=data.get("commit", ""),
            message=data.get("message", ""),
            files=data.get("files", []),
            date=data.get("date", ""),
            author=data.get("author", ""),
        )


@dataclass
class UncommittedChange:
    """Represents an uncommitted change (staged or unstaged)."""
    file: str
    description: str
    diff: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> UncommittedChange:
        return cls(
            file=data.get("file", ""),
            description=data.get("description", ""),
            diff=data.get("diff"),
        )


@dataclass
class FileChange:
    """Represents a file rename, move, or deletion."""
    type: str
    from_path: Optional[str] = None
    to_path: Optional[str] = None
    file: Optional[str] = None
    commit: Optional[str] = None
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> FileChange:
        return cls(
            type=data.get("type", ""),
            from_path=data.get("from"),
            to_path=data.get("to"),
            file=data.get("file"),
            commit=data.get("commit"),
            note=data.get("note"),
        )


@dataclass
class ChangesSection:
    """Container for all change tracking in a directory context."""
    recent: list[RecentChange] = field(default_factory=list)
    staged: list[UncommittedChange] = field(default_factory=list)
    unstaged: list[UncommittedChange] = field(default_factory=list)
    file_changes: list[FileChange] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "recent": [c.to_dict() for c in self.recent],
            "staged": [c.to_dict() for c in self.staged],
            "unstaged": [c.to_dict() for c in self.unstaged],
            "file_changes": [c.to_dict() for c in self.file_changes],
        }

    @classmethod
    def from_dict(cls, data: dict) -> ChangesSection:
        return cls(
            recent=[RecentChange.from_dict(c) for c in data.get("recent", [])],
            staged=[UncommittedChange.from_dict(c) for c in data.get("staged", [])],
            unstaged=[UncommittedChange.from_dict(c) for c in data.get("unstaged", [])],
            file_changes=[FileChange.from_dict(c) for c in data.get("file_changes", [])],
        )


@dataclass
class DirectoryContext:
    """Complete context for a directory."""
    directory: str
    description: str
    files: list[FileEntry] = field(default_factory=list)
    subdirectories: list[SubdirectoryEntry] = field(default_factory=list)
    changes: ChangesSection = field(default_factory=ChangesSection)
    version: str = "1.0"
    generated_at: str = ""

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def to_yaml(self) -> str:
        """Serialize to YAML string."""
        data = {
            "directory": self.directory,
            "description": self.description,
            "version": self.version,
            "generated_at": self.generated_at,
        }
        if self.files:
            data["files"] = [f.to_dict() for f in self.files]
        if self.subdirectories:
            data["subdirectories"] = [s.to_dict() for s in self.subdirectories]
        if self.changes.recent or self.changes.staged or self.changes.unstaged or self.changes.file_changes:
            data["changes"] = self.changes.to_dict()
        return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)

    @classmethod
    def from_yaml(cls, yaml_str: str, path: str) -> DirectoryContext:
        """Deserialize from YAML string."""
        data = yaml.safe_load(yaml_str)
        if data is None:
            raise ValueError(f"Empty YAML file: {path}")

        files = [FileEntry.from_dict(f) for f in data.get("files", [])]
        subdirs = [SubdirectoryEntry.from_dict(s) for s in data.get("subdirectories", [])]

        changes_data = data.get("changes", {})
        changes = ChangesSection.from_dict(changes_data) if changes_data else ChangesSection()

        return cls(
            directory=data.get("directory", path),
            description=data.get("description", ""),
            files=files,
            subdirectories=subdirs,
            changes=changes,
            version=data.get("version", "1.0"),
            generated_at=data.get("generated_at", ""),
        )

    @classmethod
    def from_dict(cls, data: dict) -> DirectoryContext:
        """Create from a dictionary."""
        files = [FileEntry.from_dict(f) for f in data.get("files", [])]
        subdirs = [SubdirectoryEntry.from_dict(s) for s in data.get("subdirectories", [])]
        changes = ChangesSection.from_dict(data.get("changes", {}))
        return cls(
            directory=data.get("directory", ""),
            description=data.get("description", ""),
            files=files,
            subdirectories=subdirs,
            changes=changes,
            version=data.get("version", "1.0"),
            generated_at=data.get("generated_at", ""),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "directory": self.directory,
            "description": self.description,
            "version": self.version,
            "generated_at": self.generated_at,
            "files": [f.to_dict() for f in self.files],
            "subdirectories": [s.to_dict() for s in self.subdirectories],
            "changes": self.changes.to_dict(),
        }


@dataclass
class ContextSearchResult:
    """A search result from context files."""
    directory: str
    file_path: str
    relevance_score: float
    matched_field: str
    matched_content: str


FILE_TYPES = [
    "api", "schema", "util", "test", "model", "middleware",
    "config", "service", "handler", "controller", "view",
    "component", "hook", "lib", "helper", "unknown"
]


def infer_file_type(filename: str) -> str:
    """Infer file type from filename."""
    name_lower = filename.lower()
    if name_lower.startswith("test_") or name_lower.endswith("_test.py"):
        return "test"
    if name_lower in ("routes", "endpoints", "views", "api"):
        return "api"
    if "schema" in name_lower or name_lower.endswith(".pydantic"):
        return "schema"
    if "middleware" in name_lower:
        return "middleware"
    if "model" in name_lower or "entity" in name_lower:
        return "model"
    if name_lower in ("config", "settings"):
        return "config"
    if name_lower in ("utils", "helpers", "tools"):
        return "util"
    if any(name_lower.endswith(ext) for ext in (".component.tsx", ".component.jsx", ".vue")):
        return "component"
    if name_lower.startswith("use") or name_lower.endswith(".hook."):
        return "hook"
    return "unknown"