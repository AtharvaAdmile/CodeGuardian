"""
Context Service — manages .context.yaml files for directories.

Generates, reads, updates, and searches directory context files.
Works alongside existing vector-based indexing (not replacing it initially).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import yaml

from server.models.context_models import (
    DirectoryContext,
    FileEntry,
    RecentChange,
    SubdirectoryEntry,
    UncommittedChange,
    ChangesSection,
    ContextSearchResult,
    infer_file_type,
)
from server.models.llm_models import NIMResponse

if TYPE_CHECKING:
    from server.services.llm_client import NIMClient

logger = logging.getLogger("codeguardian.context")

CONTEXT_FILENAME = ".context.yaml"
SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".svelte",
    ".go", ".rs", ".java", ".kt", ".cs", ".cpp", ".c", ".h",
    ".rb", ".php", ".swift", ".m", ".sh", ".bash", ".zsh",
    ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf",
    ".md", ".txt", ".rst", ".html", ".css", ".scss", ".sass",
    ".sql", ".graphql", ".proto", ".Dockerfile", ".tf", ".tfvars",
}


class ContextServiceError(Exception):
    """Raised when a context operation fails."""


class ContextService:
    """
    Manages .context.yaml files for directory-level code context.

    This service generates human-readable context files that describe
    directories, their purpose, files, and change history.

    Usage::

        svc = ContextService(llm_client, git_service)
        ctx = await svc.analyze_directory("/path/to/repo/src")
        await svc.save_context(ctx)
    """

    def __init__(
        self,
        llm_client: "NIMClient",
        git_service: "GitService | None" = None,
        context_filename: str = CONTEXT_FILENAME,
    ) -> None:
        """
        Initialize the Context Service.

        Args:
            llm_client: NIMClient for LLM generation.
            git_service: Optional GitService for git history integration.
            context_filename: Name of the context file (default: .context.yaml).
        """
        self.llm = llm_client
        self.git = git_service
        self.context_filename = context_filename
        self._context_cache: dict[str, DirectoryContext] = {}

        logger.info(
            "ContextService initialized — filename=%s  git=%s",
            context_filename,
            "enabled" if git_service else "disabled",
        )

    def _get_context_path(self, dir_path: str) -> Path:
        """Get the path to the context file for a directory."""
        return Path(dir_path) / self.context_filename

    def _is_supported_file(self, filename: str) -> bool:
        """Check if a file should be included in context."""
        if filename.startswith("."):
            return filename == self.context_filename
        ext = os.path.splitext(filename)[1].lower()
        return ext in SUPPORTED_EXTENSIONS or filename in (
            "Makefile", "Dockerfile", "Vagrantfile", "Brewfile",
            "CMakeLists.txt", "setup.py", "package.json", "go.mod",
            "go.sum", "Cargo.toml", "requirements.txt", "Pipfile",
            "pyproject.toml", "setup.cfg", "tox.ini", "pytest.ini",
        )

    async def analyze_directory(
        self,
        dir_path: str,
        repo_path: str,
        force_refresh: bool = False,
    ) -> DirectoryContext:
        """
        Analyze a directory and generate its context YAML.

        Args:
            dir_path: Absolute path to the directory to analyze.
            repo_path: Absolute path to the repository root.
            force_refresh: If True, regenerate even if context exists.

        Returns:
            DirectoryContext object for the directory.
        """
        context_path = self._get_context_path(dir_path)

        if not force_refresh and context_path.exists():
            try:
                existing = await self.read_context(dir_path)
                if existing:
                    logger.debug("Using existing context for %s", dir_path)
                    return existing
            except Exception as exc:
                logger.warning("Failed to read existing context: %s", exc)

        try:
            files = self._list_files(dir_path)
            subdirs = self._list_subdirectories(dir_path)
            git_history: list[dict] = []

            if self.git:
                git_history = await asyncio.to_thread(
                    self._get_directory_history, dir_path, repo_path, limit=10
                )

            context = await self._generate_initial_context(
                dir_path, files, subdirs, git_history
            )

            self._context_cache[dir_path] = context
            return context

        except Exception as exc:
            logger.error("Failed to analyze directory %s: %s", dir_path, exc)
            raise ContextServiceError(f"Directory analysis failed: {exc}") from exc

    async def read_context(self, dir_path: str) -> Optional[DirectoryContext]:
        """
        Read and parse an existing .context.yaml file.

        Args:
            dir_path: Absolute path to the directory.

        Returns:
            DirectoryContext or None if file doesn't exist.
        """
        if dir_path in self._context_cache:
            return self._context_cache[dir_path]

        context_path = self._get_context_path(dir_path)

        if not context_path.exists():
            return None

        try:
            yaml_str = context_path.read_text(encoding="utf-8")
            context = DirectoryContext.from_yaml(yaml_str, dir_path)
            self._context_cache[dir_path] = context
            return context
        except Exception as exc:
            logger.warning("Failed to parse context file %s: %s", context_path, exc)
            return None

    async def save_context(
        self,
        context: DirectoryContext,
        auto_commit: bool = False,
    ) -> bool:
        """
        Save a DirectoryContext to its .context.yaml file.

        Args:
            context: The DirectoryContext to save.
            auto_commit: If True, auto-commit the file via git.

        Returns:
            True if saved successfully, False otherwise.
        """
        context_path = self._get_context_path(context.directory)
        context_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            yaml_content = context.to_yaml()
            context_path.write_text(yaml_content, encoding="utf-8")
            context_path.chmod(0o644)

            self._context_cache[context.directory] = context

            if auto_commit and self.git:
                await asyncio.to_thread(
                    self._auto_commit, str(context_path.parent), str(context_path)
                )

            logger.debug("Saved context to %s", context_path)
            return True

        except Exception as exc:
            logger.error("Failed to save context to %s: %s", context_path, exc)
            return False

    async def update_on_changes(
        self,
        dir_path: str,
        repo_path: str,
        change_type: str,
    ) -> DirectoryContext:
        """
        Update an existing context file with new changes.

        Args:
            dir_path: Absolute path to the directory.
            repo_path: Absolute path to the repository root.
            change_type: One of "staged", "unstaged", "committed".

        Returns:
            Updated DirectoryContext object.
        """
        existing = await self.read_context(dir_path)
        if not existing:
            logger.info("No existing context for %s, creating new", dir_path)
            return await self.analyze_directory(dir_path, repo_path, force_refresh=True)

        changes = await self._get_changes_for_directory(dir_path, repo_path, change_type)

        if changes.staged or changes.unstaged or changes.recent:
            updated_context = await self._generate_update(existing, changes)
            await self.save_context(updated_context)
            return updated_context

        return existing

    async def delete_context(self, dir_path: str) -> bool:
        """
        Remove .context.yaml when a directory is deleted.

        Args:
            dir_path: Absolute path to the directory.

        Returns:
            True if deleted, False if file didn't exist.
        """
        context_path = self._get_context_path(dir_path)

        if not context_path.exists():
            return False

        try:
            context_path.unlink()
            self._context_cache.pop(dir_path, None)
            logger.debug("Deleted context file %s", context_path)
            return True
        except Exception as exc:
            logger.error("Failed to delete context %s: %s", context_path, exc)
            return False

    def search_contexts(
        self,
        query: str,
        repo_path: str,
        max_results: int = 5,
    ) -> list[ContextSearchResult]:
        """
        Search for relevant context files matching a query.

        Args:
            query: Search query (can include path or keywords).
            repo_path: Absolute path to the repository root.
            max_results: Maximum number of results to return.

        Returns:
            List of ContextSearchResult objects sorted by relevance.
        """
        results: list[ContextSearchResult] = []
        query_lower = query.lower()

        try:
            for root, dirs, files in os.walk(repo_path):
                if self.context_filename not in files:
                    continue

                context_path = os.path.join(root, self.context_filename)
                try:
                    yaml_str = Path(context_path).read_text(encoding="utf-8")
                    data = yaml.safe_load(yaml_str)

                    if not data:
                        continue

                    score = 0.0
                    matched_field = ""
                    matched_content = ""

                    directory = data.get("directory", "")
                    description = data.get("description", "")
                    dir_name = os.path.basename(root).lower()

                    if query_lower in directory.lower():
                        score += 3.0
                        matched_field = "directory"
                        matched_content = directory

                    if query_lower in dir_name:
                        score += 2.5
                        if not matched_field:
                            matched_field = "directory"

                    if query_lower in description.lower():
                        score += 2.0
                        matched_field = "description"
                        matched_content = description[:200]

                    for file_entry in data.get("files", []):
                        file_name = file_entry.get("name", "").lower()
                        file_purpose = file_entry.get("purpose", "").lower()

                        if query_lower in file_name:
                            score += 1.5
                            if not matched_content:
                                matched_content = f"{file_name}: {file_purpose}"

                        if query_lower in file_purpose:
                            score += 1.0

                    if score > 0:
                        results.append(ContextSearchResult(
                            directory=directory or root,
                            file_path=context_path,
                            relevance_score=score,
                            matched_field=matched_field,
                            matched_content=matched_content,
                        ))

                except Exception as exc:
                    logger.debug("Failed to search context %s: %s", context_path, exc)
                    continue

        except Exception as exc:
            logger.error("Context search failed: %s", exc)

        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:max_results]

    def _list_files(self, dir_path: str) -> list[dict]:
        """List files in a directory with metadata."""
        files = []
        try:
            for entry in os.scandir(dir_path):
                if entry.is_file() and self._is_supported_file(entry.name):
                    file_type = infer_file_type(entry.name)
                    try:
                        stat = entry.stat()
                        size = stat.st_size
                    except OSError:
                        size = 0
                    files.append({
                        "name": entry.name,
                        "type": file_type,
                        "size": size,
                    })
        except PermissionError:
            logger.warning("Permission denied reading directory: %s", dir_path)
        return files

    def _list_subdirectories(self, dir_path: str) -> list[dict]:
        """List subdirectories in a directory."""
        subdirs = []
        try:
            for entry in os.scandir(dir_path):
                if entry.is_dir() and not entry.name.startswith("."):
                    subdirs.append({
                        "name": entry.name,
                        "has_context": self._get_context_path(entry.path).exists(),
                    })
        except PermissionError:
            logger.warning("Permission denied reading directory: %s", dir_path)
        return subdirs

    def _get_directory_history(
        self,
        dir_path: str,
        repo_path: str,
        limit: int = 10,
    ) -> list[dict]:
        """Get git history for files in a directory."""
        if not self.git:
            return []

        try:
            commits = self.git.get_recent_commits(limit=limit * 2)
            relevant = []

            for commit in commits:
                dir_relative = os.path.relpath(dir_path, repo_path)
                for changed_file in commit.files_changed:
                    if changed_file.startswith(dir_relative) or dir_relative in changed_file:
                        relevant.append({
                            "commit": commit.sha,
                            "message": commit.message,
                            "date": commit.date.isoformat(),
                            "author": commit.author,
                            "files": [f for f in commit.files_changed if f.startswith(dir_relative)],
                        })
                        break

                if len(relevant) >= limit:
                    break

            return relevant

        except Exception as exc:
            logger.warning("Failed to get directory history: %s", exc)
            return []

    async def _generate_initial_context(
        self,
        dir_path: str,
        files: list[dict],
        subdirs: list[dict],
        git_history: list[dict],
    ) -> DirectoryContext:
        """Call LLM to generate initial directory context."""
        dir_name = os.path.basename(dir_path)
        dir_relative = os.path.relpath(dir_path, start=os.path.dirname(dir_path))

        file_list_str = "\n".join(
            f"  - {f['name']} ({f['type']}, {f.get('size', 0)} bytes)"
            for f in files[:50]
        )
        subdir_list_str = "\n".join(
            f"  - {s['name']}" + (" (has context)" if s.get("has_context") else "")
            for s in subdirs[:20]
        )
        history_str = "\n".join(
            f"  - {h['commit'][:8]}: {h['message'][:80]} by {h['author']}"
            for h in git_history[:5]
        ) if git_history else "  No recent changes"

        system_prompt = """You are a code analyst. Generate a .context.yaml description for a directory.
Focus on:
1. What this directory contains and its purpose
2. Key files and their roles
3. How it relates to the overall codebase

Be concise but informative. Use the file types provided (api, schema, util, test, model, middleware, etc.)."""

        user_prompt = f"""Analyze this directory and provide context:

Directory: {dir_relative or dir_name}
Full path: {dir_path}

Files in this directory:
{file_list_str or '  (empty or no supported files)'}

Subdirectories:
{subdir_list_str or '  (no subdirectories)'}

Recent git history:
{history_str}

Respond with a brief description (2-3 sentences) of what this directory contains and its purpose."""

        try:
            response = await self.llm.complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=500,
            )

            description = response.content.strip()

            file_entries = [
                FileEntry(
                    name=f["name"],
                    purpose=f"File of type {f['type']}",
                    type=f["type"],
                )
                for f in files
            ]

            subdir_entries = [
                SubdirectoryEntry(
                    name=s["name"],
                    purpose="Subdirectory" + (" with existing context" if s.get("has_context") else ""),
                )
                for s in subdirs
            ]

            recent_changes = [
                RecentChange(
                    commit=h["commit"],
                    message=h["message"],
                    files=h["files"],
                    date=h["date"],
                    author=h["author"],
                )
                for h in git_history[:10]
            ]

            return DirectoryContext(
                directory=dir_relative or dir_name,
                description=description,
                files=file_entries,
                subdirectories=subdir_entries,
                changes=ChangesSection(recent=recent_changes),
            )

        except Exception as exc:
            logger.error("LLM context generation failed: %s", exc)
            fallback_desc = f"Directory containing {len(files)} files and {len(subdirs)} subdirectories."
            return DirectoryContext(
                directory=dir_relative or dir_name,
                description=fallback_desc,
                files=[
                    FileEntry(name=f["name"], purpose=f"File of type {f['type']}", type=f["type"])
                    for f in files
                ],
                subdirectories=[
                    SubdirectoryEntry(name=s["name"], purpose="Subdirectory")
                    for s in subdirs
                ],
            )

    async def _generate_update(
        self,
        existing: DirectoryContext,
        changes: ChangesSection,
    ) -> DirectoryContext:
        """Call LLM to update existing context with new changes."""
        changes_summary = []
        if changes.recent:
            changes_summary.append(f"New commits: {len(changes.recent)}")
        if changes.staged:
            changes_summary.append(f"Staged changes: {len(changes.staged)}")
        if changes.unstaged:
            changes_summary.append(f"Unstaged changes: {len(changes.unstaged)}")

        system_prompt = """You are a code historian. Update the description of a directory based on recent changes.
Keep the description accurate but update it if the changes affect the directory's purpose.
Respond with only the updated description (2-3 sentences)."""

        user_prompt = f"""Update the directory description for: {existing.directory}

Current description:
{existing.description}

Recent changes:
{chr(10).join(changes_summary)}

If the changes are significant, briefly update the description. Otherwise, keep it similar."""

        try:
            response = await self.llm.complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=200,
            )

            existing.description = response.content.strip()
        except Exception as exc:
            logger.warning("Failed to update description via LLM: %s", exc)

        existing.changes = changes
        existing.generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return existing

    def _get_changes_for_directory(
        self,
        dir_path: str,
        repo_path: str,
        change_type: str,
    ) -> ChangesSection:
        """Get changes for a directory based on change type."""
        changes = ChangesSection()
        dir_relative = os.path.relpath(dir_path, repo_path)

        if not self.git:
            return changes

        try:
            if change_type == "committed":
                commits = self.git.get_recent_commits(limit=5)
                for commit in commits:
                    for changed_file in commit.files_changed:
                        if changed_file.startswith(dir_relative):
                            changes.recent.append(RecentChange(
                                commit=commit.sha,
                                message=commit.message,
                                files=[changed_file],
                                date=commit.date.isoformat(),
                                author=commit.author,
                            ))
                            break

            elif change_type in ("staged", "unstaged"):
                flag = "--cached" if change_type == "staged" else ""
                diff_output = self.git._repo.git.diff(flag, "--name-only").strip()
                if diff_output:
                    changed_files = diff_output.split("\n")
                    for f in changed_files:
                        if f.startswith(dir_relative):
                            changes.unstaged.append(UncommittedChange(
                                file=f,
                                description="Modified file",
                            ))

        except Exception as exc:
            logger.warning("Failed to get changes for %s: %s", dir_path, exc)

        return changes

    def _auto_commit(self, dir_path: str, context_path: str) -> None:
        """Auto-commit the .context.yaml file."""
        try:
            self.git._repo.index.add([context_path])
            self.git._repo.index.commit(
                f"docs: update context for {os.path.relpath(context_path, dir_path)}"
            )
            logger.debug("Auto-committed context file %s", context_path)
        except Exception as exc:
            logger.warning("Auto-commit failed: %s", exc)