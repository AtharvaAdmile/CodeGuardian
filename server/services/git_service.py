"""
Git History Service — wraps GitPython for blame, commits, diffs, and expertise.

Provides synchronous methods (git is inherently blocking I/O).
Call from async context via ``asyncio.to_thread(service.method, ...)``.

Handles edge cases gracefully:
  • Repos with no commits
  • Detached HEAD state
  • Shallow clones (partial blame results)
  • Binary / missing files
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import git
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from server.models.git_models import BlameEntry, CommitInfo, ExpertiseEntry

logger = logging.getLogger("codeguardian.git")


class GitServiceError(Exception):
    """Raised when a git operation fails irrecoverably."""


class GitService:
    """
    Wraps a local git repository for history inspection.

    Usage::

        svc = GitService("/path/to/repo")
        blame = svc.get_file_blame("src/main.py")
        commits = svc.get_recent_commits(limit=50)
    """

    def __init__(
        self,
        repo_path: str,
        supabase_client: Any | None = None,
        local_dir: str = ".codeguardian/expertise",
    ) -> None:
        """
        Open the git repository at *repo_path*.

        Args:
            repo_path:       Absolute path to the repository root.
            supabase_client: Optional Supabase client for expertise storage.
            local_dir:       Local directory for JSON expertise fallback.

        Raises:
            GitServiceError: If the path is not a valid git repository.
        """
        try:
            self._repo = git.Repo(repo_path, search_parent_directories=True)
        except InvalidGitRepositoryError as exc:
            raise GitServiceError(
                f"Not a git repository: {repo_path}"
            ) from exc
        except NoSuchPathError as exc:
            raise GitServiceError(
                f"Path does not exist: {repo_path}"
            ) from exc

        self._repo_path = repo_path
        self._supabase = supabase_client
        self._local_dir = local_dir

        logger.info(
            "GitService initialised — repo=%s  branch=%s  supabase=%s",
            repo_path,
            self._safe_branch_name(),
            "connected" if supabase_client else "disabled",
        )

    # ── Public API ───────────────────────────────────────────────────────

    def get_file_blame(self, file_path: str) -> list[BlameEntry]:
        """
        Return blame entries for *file_path* relative to the repo root.

        Returns an empty list if the file is binary, does not exist in
        the index, or the repo is in a state where blame is unavailable
        (e.g. empty repo or shallow history).
        """
        if self._is_empty_repo():
            return []

        try:
            blame_data = self._repo.blame("HEAD", file_path)
        except GitCommandError as exc:
            logger.warning(
                "Blame failed for '%s' (possibly binary/missing/shallow): %s",
                file_path,
                exc,
            )
            return []
        except ValueError:
            # Empty repo or other unusual state
            return []

        entries: list[BlameEntry] = []
        current_line = 1

        for commit, lines in blame_data:
            num_lines = len(lines)
            start_line = current_line
            end_line = current_line + num_lines - 1

            entries.append(
                BlameEntry(
                    author=str(commit.author),
                    email=str(commit.author.email) if commit.author.email else "",
                    date=datetime.fromtimestamp(
                        commit.committed_date, tz=timezone.utc
                    ),
                    commit_sha=commit.hexsha,
                    line_range=(start_line, end_line),
                )
            )
            current_line = end_line + 1

        return entries

    def get_recent_commits(self, limit: int = 100) -> list[CommitInfo]:
        """
        Return up to *limit* most recent commits across all branches.

        Returns an empty list for repos with no commits.
        """
        if self._is_empty_repo():
            return []

        try:
            commits = list(self._repo.iter_commits(max_count=limit))
        except ValueError:
            # Empty repo — iter_commits raises ValueError
            return []
        except GitCommandError as exc:
            logger.warning("Could not iterate commits: %s", exc)
            return []

        return [self._commit_to_info(c) for c in commits]

    def get_file_history(
        self, file_path: str, limit: int = 20
    ) -> list[CommitInfo]:
        """
        Return up to *limit* commits that touched *file_path*.

        Returns an empty list if the file has no history or the repo
        is empty.
        """
        if self._is_empty_repo():
            return []

        try:
            commits = list(
                self._repo.iter_commits(paths=file_path, max_count=limit)
            )
        except (ValueError, GitCommandError) as exc:
            logger.warning(
                "File history lookup failed for '%s': %s", file_path, exc
            )
            return []

        return [self._commit_to_info(c) for c in commits]

    def get_commit_diff(self, sha: str) -> str:
        """
        Return the unified diff string for commit *sha*.

        For the root commit (no parents), diffs against the empty tree.
        Returns an empty string if the commit is not found.
        """
        try:
            commit = self._repo.commit(sha)
            # Access parents eagerly to trigger any gitdb errors now
            _ = commit.parents
        except Exception as exc:
            logger.warning("Could not find commit %s: %s", sha, exc)
            return ""

        try:
            if commit.parents:
                # Normal commit — diff against first parent
                diff_text = self._repo.git.diff(
                    commit.parents[0].hexsha, commit.hexsha
                )
            else:
                # Root commit — use GitPython's diff API against NULL_TREE
                diffs = commit.diff(git.NULL_TREE, create_patch=True)
                parts: list[str] = []
                for d in diffs:
                    header = f"diff --git a/{d.b_path} b/{d.b_path}"
                    parts.append(header)
                    if d.diff:
                        decoded = (
                            d.diff.decode("utf-8", errors="replace")
                            if isinstance(d.diff, bytes)
                            else str(d.diff)
                        )
                        parts.append(decoded)
                diff_text = "\n".join(parts)
            return diff_text
        except GitCommandError as exc:
            logger.warning("Diff generation failed for %s: %s", sha, exc)
            return ""

    # ── Expertise Mapping ────────────────────────────────────────────────

    def build_expertise_map(
        self, file_paths: list[str]
    ) -> dict[str, list[ExpertiseEntry]]:
        """
        For each file in *file_paths*, aggregate blame data to produce
        an expertise ranking of authors.

        Returns a dict mapping file paths to lists of :class:`ExpertiseEntry`
        sorted by commit count descending.

        Results are persisted to Supabase (if available) or local JSON.
        """
        expertise: dict[str, list[ExpertiseEntry]] = {}

        for fp in file_paths:
            blame_entries = self.get_file_blame(fp)
            if not blame_entries:
                continue

            # Aggregate per-author stats - use epoch as initial value to ensure timezone-aware comparison
            author_stats: dict[str, dict] = defaultdict(
                lambda: {"email": "", "commit_count": 0, "last_active": datetime(1970, 1, 1, tzinfo=timezone.utc)}
            )

            # Track unique commits per author (blame can repeat SHAs)
            author_commits: dict[str, set[str]] = defaultdict(set)

            for entry in blame_entries:
                author_commits[entry.author].add(entry.commit_sha)
                stats = author_stats[entry.author]
                stats["email"] = entry.email
                stats["commit_count"] = len(author_commits[entry.author])
                if entry.date > stats["last_active"]:
                    stats["last_active"] = entry.date

            entries = [
                ExpertiseEntry(
                    file_path=fp,
                    author=author,
                    email=data["email"],
                    commit_count=data["commit_count"],
                    last_active=data["last_active"],
                )
                for author, data in author_stats.items()
            ]
            entries.sort(key=lambda e: e.commit_count, reverse=True)
            expertise[fp] = entries

        # Persist results
        self._store_expertise(expertise)

        return expertise

    # ── Storage helpers ──────────────────────────────────────────────────

    def _store_expertise(
        self, expertise: dict[str, list[ExpertiseEntry]]
    ) -> None:
        """Persist expertise map to Supabase or local JSON."""
        if self._supabase is not None:
            try:
                rows = []
                for file_path, entries in expertise.items():
                    for entry in entries:
                        rows.append(
                            {
                                "file_path": entry.file_path,
                                "author": entry.author,
                                "email": entry.email,
                                "commit_count": entry.commit_count,
                                "last_active": entry.last_active.isoformat(),
                                "repo_path": self._repo_path,
                            }
                        )
                if rows:
                    self._supabase.table("expertise_map").upsert(rows).execute()
                    logger.debug(
                        "Stored %d expertise entries in Supabase", len(rows)
                    )
                return
            except Exception as exc:
                logger.warning(
                    "Supabase expertise store failed (falling back to local): %s",
                    exc,
                )

        # Local JSON fallback
        self._write_local_expertise(expertise)

    def _write_local_expertise(
        self, expertise: dict[str, list[ExpertiseEntry]]
    ) -> None:
        """Write expertise map to local JSON file."""
        out_dir = Path(self._local_dir)
        # Clear any path component that exists as a file instead of directory
        for ancestor in reversed(out_dir.parents):
            if ancestor.exists() and not ancestor.is_dir():
                ancestor.unlink()
        if out_dir.exists() and not out_dir.is_dir():
            out_dir.unlink()
        out_dir.mkdir(parents=True, exist_ok=True)

        data = {}
        for file_path, entries in expertise.items():
            data[file_path] = [
                {
                    "author": e.author,
                    "email": e.email,
                    "commit_count": e.commit_count,
                    "last_active": e.last_active.isoformat(),
                }
                for e in entries
            ]

        out_file = out_dir / "expertise_map.json"
        out_file.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )
        logger.debug("Stored expertise map locally at %s", out_file)

    # ── Internal helpers ─────────────────────────────────────────────────

    def _is_empty_repo(self) -> bool:
        """Return True if the repo has zero commits."""
        try:
            self._repo.head.commit
            return False
        except ValueError:
            return True

    def _safe_branch_name(self) -> str:
        """Return the current branch name or 'DETACHED' / 'EMPTY'."""
        try:
            if self._repo.head.is_detached:
                return f"DETACHED@{self._repo.head.commit.hexsha[:8]}"
            return str(self._repo.active_branch)
        except (TypeError, ValueError):
            return "EMPTY"

    @staticmethod
    def _commit_to_info(commit: git.Commit) -> CommitInfo:
        """Convert a GitPython Commit into a CommitInfo dataclass."""
        # Get changed files — use diff against parent or empty tree
        files_changed: list[str] = []
        try:
            if commit.parents:
                diffs = commit.diff(commit.parents[0])
            else:
                diffs = commit.diff(git.NULL_TREE)
            files_changed = [
                d.b_path or d.a_path
                for d in diffs
                if d.b_path or d.a_path
            ]
        except (GitCommandError, Exception):
            # If diff fails, fall back to stats
            try:
                files_changed = list(commit.stats.files.keys())
            except Exception:
                pass

        return CommitInfo(
            sha=commit.hexsha,
            author=str(commit.author),
            email=str(commit.author.email) if commit.author.email else "",
            message=commit.message.strip(),
            date=datetime.fromtimestamp(
                commit.committed_date, tz=timezone.utc
            ),
            files_changed=files_changed,
        )
