"""
Retrieval Service — retrieves relevant context for QnA queries.

Uses context-yaml files to provide meaningful context for questions
about the codebase, complementing the existing vector-based retrieval.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import yaml

from server.models.context_models import (
    DirectoryContext,
    ContextSearchResult,
    FileEntry,
)

if TYPE_CHECKING:
    from server.services.context_service import ContextService

logger = logging.getLogger("codeguardian.retrieval")

MAX_CONTEXT_DIRS = 5
MAX_SNIPPETS_PER_DIR = 3


class RetrievalService:
    """
    Service for retrieving relevant context for queries.

    Uses hybrid search combining path matching and keyword search
    to find the most relevant .context.yaml files.

    Usage::

        retrieval = RetrievalService(context_service)
        snippets = await retrieval.retrieve_for_query(
            "How does authentication work?",
            "/path/to/repo"
        )
        prompt = await retrieval.build_context_prompt(query, repo_path)
    """

    def __init__(
        self,
        context_service: "ContextService",
        max_contexts: int = MAX_CONTEXT_DIRS,
        max_snippets: int = MAX_SNIPPETS_PER_DIR,
    ) -> None:
        """
        Initialize the Retrieval Service.

        Args:
            context_service: ContextService for accessing context files.
            max_contexts: Maximum number of context directories to include.
            max_snippets: Maximum number of snippets per directory.
        """
        self.context = context_service
        self.max_contexts = max_contexts
        self.max_snippets = max_snippets

        logger.info(
            "RetrievalService initialized — max_contexts=%d  max_snippets=%d",
            max_contexts, max_snippets,
        )

    def search_contexts(
        self,
        query: str,
        repo_path: str,
    ) -> list[ContextSearchResult]:
        """
        Search for context files matching a query.

        Args:
            query: Search query (can include path components or keywords).
            repo_path: Absolute path to the repository root.

        Returns:
            List of matching context files with relevance scores.
        """
        return self.context.search_contexts(query, repo_path, self.max_contexts)

    async def retrieve_for_query(
        self,
        query: str,
        repo_path: str,
        max_contexts: int | None = None,
    ) -> list[dict]:
        """
        Retrieve relevant context snippets for a user query.

        Args:
            query: The user's question or query.
            repo_path: Absolute path to the repository root.
            max_contexts: Override max number of contexts.

        Returns:
            List of dictionaries with context information for the prompt.
        """
        max_results = max_contexts or self.max_contexts
        search_results = self.search_contexts(query, repo_path)

        contexts = []
        for result in search_results[:max_results]:
            context_dir = os.path.dirname(result.file_path)
            context = await self.context.read_context(context_dir)

            if context:
                snippets = self._extract_relevant_sections(context, query)
                contexts.append({
                    "directory": context.directory,
                    "description": context.description,
                    "snippets": snippets,
                    "files": [
                        {
                            "name": f.name,
                            "purpose": f.purpose,
                            "type": f.type,
                            "key_apis": f.key_apis,
                        }
                        for f in context.files[:10]
                    ],
                    "relevance_score": result.relevance_score,
                })

        return contexts

    async def build_context_prompt(
        self,
        query: str,
        repo_path: str,
    ) -> str:
        """
        Build a prompt context string for the QnA LLM.

        Args:
            query: The user's question.
            repo_path: Absolute path to the repository root.

        Returns:
            Formatted context string to include in the prompt.
        """
        contexts = await self.retrieve_for_query(query, repo_path)

        if not contexts:
            return ""

        prompt_parts = ["=== CONTEXT FROM CODEBASE ===\n"]

        for ctx in contexts:
            prompt_parts.append(f"## Directory: {ctx['directory']}\n")
            prompt_parts.append(f"Description: {ctx['description']}\n")

            if ctx["files"]:
                prompt_parts.append("\nFiles:")
                for f in ctx["files"][:5]:
                    prompt_parts.append(f"  - {f['name']}: {f['purpose']} (type: {f['type']})")
                    if f.get("key_apis"):
                        prompt_parts.append(f"    Key APIs: {', '.join(f['key_apis'][:5])}")

            if ctx["snippets"]:
                prompt_parts.append("\nRelevant excerpts:")
                for snippet in ctx["snippets"][:self.max_snippets]:
                    prompt_parts.append(f"  [{snippet['section']}] {snippet['content']}")

            prompt_parts.append("")

        prompt_parts.append("=== END CONTEXT ===\n")

        return "".join(prompt_parts)

    def _extract_relevant_sections(
        self,
        context: DirectoryContext,
        query: str,
    ) -> list[dict]:
        """Extract sections from context relevant to the query."""
        query_lower = query.lower()
        snippets = []

        if query_lower in context.description.lower():
            snippets.append({
                "section": "description",
                "content": context.description[:300],
            })

        keywords = self._extract_keywords(query_lower)
        matched_files: list[tuple[FileEntry, float]] = []

        for file_entry in context.files:
            file_score = 0.0
            if any(kw in file_entry.name.lower() for kw in keywords):
                file_score += 1.0
            if any(kw in file_entry.purpose.lower() for kw in keywords):
                file_score += 0.5
            if any(kw in api.lower() for api in file_entry.key_apis for kw in keywords):
                file_score += 1.5

            if file_score > 0:
                matched_files.append((file_entry, file_score))

        matched_files.sort(key=lambda x: x[1], reverse=True)

        for file_entry, score in matched_files[:self.max_snippets]:
            snippets.append({
                "section": f"file:{file_entry.name}",
                "content": f"{file_entry.name}: {file_entry.purpose}",
            })

        return snippets[:self.max_snippets]

    def _extract_keywords(self, query: str) -> list[str]:
        """Extract meaningful keywords from a query."""
        stopwords = {
            "a", "an", "the", "is", "are", "was", "were", "be", "been",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "can", "to", "of", "in",
            "for", "on", "with", "at", "by", "from", "as", "or", "and",
            "how", "what", "why", "when", "where", "which", "who", "whom",
            "this", "that", "these", "those", "it", "its", "i", "we", "you",
        }

        words = query.split()
        keywords = [w for w in words if w not in stopwords and len(w) > 2]
        return keywords[:5]

    async def get_directory_context(
        self,
        dir_path: str,
        include_related: bool = False,
    ) -> dict | None:
        """
        Get complete context for a specific directory.

        Args:
            dir_path: Absolute path to the directory.
            include_related: If True, include parent and sibling contexts.

        Returns:
            Dictionary with directory context or None if not found.
        """
        context = await self.context.read_context(dir_path)

        if not context:
            return None

        result = {
            "directory": context.directory,
            "description": context.description,
            "version": context.version,
            "generated_at": context.generated_at,
            "files": [f.to_dict() for f in context.files],
            "subdirectories": [s.to_dict() for s in context.subdirectories],
            "changes": context.changes.to_dict(),
        }

        if include_related:
            parent_path = str(Path(dir_path).parent)
            if parent_path != dir_path:
                parent_ctx = await self.context.read_context(parent_path)
                if parent_ctx:
                    result["parent"] = {
                        "directory": parent_ctx.directory,
                        "description": parent_ctx.description,
                    }

        return result

    def get_all_context_files(self, repo_path: str) -> list[str]:
        """
        Get all .context.yaml files in a repository.

        Args:
            repo_path: Absolute path to the repository root.

        Returns:
            List of paths to context files.
        """
        context_files = []
        context_filename = self.context.context_filename

        try:
            for root, dirs, files in os.walk(repo_path):
                if context_filename in files:
                    context_files.append(os.path.join(root, context_filename))
        except Exception as exc:
            logger.error("Failed to list context files: %s", exc)

        return context_files

    async def validate_context_files(self, repo_path: str) -> dict:
        """
        Validate all context files in a repository.

        Args:
            repo_path: Absolute path to the repository root.

        Returns:
            Dictionary with validation results.
        """
        context_files = self.get_all_context_files(repo_path)
        results = {
            "total": len(context_files),
            "valid": 0,
            "invalid": 0,
            "errors": [],
        }

        for file_path in context_files:
            try:
                yaml_str = Path(file_path).read_text(encoding="utf-8")
                data = yaml.safe_load(yaml_str)

                if not data or "directory" not in data or "description" not in data:
                    results["invalid"] += 1
                    results["errors"].append({
                        "file": file_path,
                        "error": "Missing required fields (directory or description)",
                    })
                else:
                    results["valid"] += 1

            except yaml.YAMLError as exc:
                results["invalid"] += 1
                results["errors"].append({
                    "file": file_path,
                    "error": f"YAML parse error: {exc}",
                })
            except Exception as exc:
                results["invalid"] += 1
                results["errors"].append({
                    "file": file_path,
                    "error": str(exc),
                })

        return results