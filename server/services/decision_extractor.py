"""
Decision Extractor — LLM-powered architectural decision extraction.

Uses the NIM LLM client to identify genuine architectural decisions
embedded in commit messages, diffs, and PR comments. The core insight
is that the VAST majority of commits and comments are NOT decisions;
the extraction prompt is intentionally conservative.

Usage::

    extractor = DecisionExtractor(llm_client)
    decisions = await extractor.extract_from_commit(
        commit_message="Migrate from REST to gRPC for inter-service calls",
        diff="... unified diff ...",
    )

    # Batch processing with rate limiting
    stats = await extractor.process_commits_batch(commits, git_service)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from server.models.git_models import CommitInfo, Decision

if TYPE_CHECKING:
    from server.services.git_service import GitService
    from server.services.llm_client import NIMClient

logger = logging.getLogger("codeguardian.decisions.extractor")

# ── Maximum diff size sent to the LLM (characters) ──────────────────────
_MAX_DIFF_CHARS = 8_000

# ── Batch processing constants ──────────────────────────────────────────
_BATCH_SIZE = 10
_RATE_LIMIT_DELAY_MS = 200  # 200ms between LLM calls

# ── System prompt — user-specified, intentionally conservative ──────────
_SYSTEM_PROMPT = """\
You are analyzing git commit messages and PR comments to extract architectural \
decisions — choices about HOW or WHY the code is designed a certain way.

An architectural decision is NOT:
- A bug fix ("fixed null pointer in auth")
- A feature description ("added login page")
- A code review nitpick ("rename this variable")
- A merge commit with no context

An architectural decision IS:
- A technology choice ("switched from REST to gRPC because...")
- A design pattern choice ("using repository pattern here to isolate DB...")
- A constraint explanation ("timeout is 30s because downstream service X...")
- A tradeoff acknowledgment ("chose eventual consistency over strong because...")

If the text contains NO architectural decision, respond with exactly: NONE

If it contains a decision, respond in JSON:
{"title": "...", "context": "what problem was being solved", "decision": "what was decided", "reasoning": "why this choice over alternatives"}
"""

_PR_SYSTEM_PROMPT = """\
You are analyzing pull request comments to extract architectural decisions — \
choices about HOW or WHY the code is designed a certain way.

An architectural decision is NOT:
- Code review nits (style, naming, formatting)
- Bug reports or bug fix suggestions
- Questions without resolution
- Approval/merge comments ("LGTM", "Looks good")
- Feature requests without design discussion

An architectural decision IS:
- A technology choice with stated reasoning
- A design pattern selection with justification
- An explicit tradeoff between competing concerns
- A convention being established for the codebase

If the comments contain NO architectural decision, respond with exactly: NONE

If they contain a decision, respond in JSON:
{"title": "...", "context": "what problem was being solved", "decision": "what was decided", "reasoning": "why this choice over alternatives"}
"""


# ── Extraction Stats ────────────────────────────────────────────────────


@dataclass
class ExtractionStats:
    """Tracks batch extraction progress and results."""

    total_processed: int = 0
    decisions_found: int = 0
    errors: int = 0
    skipped_trivial: int = 0
    elapsed_seconds: float = 0.0
    decisions: list[Decision] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_processed": self.total_processed,
            "decisions_found": self.decisions_found,
            "errors": self.errors,
            "skipped_trivial": self.skipped_trivial,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }


class DecisionExtractor:
    """
    Extracts architectural decisions from git commits and PR comments
    using the NIM LLM client.

    The extraction is intentionally conservative — most inputs will
    yield an empty list.
    """

    def __init__(self, llm_client: NIMClient) -> None:
        self._llm = llm_client
        logger.info("DecisionExtractor initialised")

    # ── Single-item extraction ───────────────────────────────────────────

    async def extract_from_commit(
        self,
        commit_message: str,
        diff: str,
        *,
        source_ref: str = "",
    ) -> list[Decision]:
        """
        Extract architectural decisions from a commit message and diff.

        Args:
            commit_message: The full commit message.
            diff:           The unified diff string (truncated to ~8k chars).
            source_ref:     Commit SHA for back-reference.

        Returns:
            A list of Decision objects (empty list if none found).
        """
        # Quick heuristic rejections — skip obviously routine commits
        msg_lower = commit_message.lower().strip()
        if self._is_trivial_commit(msg_lower):
            logger.debug(
                "Skipping trivial commit: %.60s…", commit_message
            )
            return []

        # Truncate large diffs to stay within LLM context
        truncated_diff = diff[:_MAX_DIFF_CHARS]
        if len(diff) > _MAX_DIFF_CHARS:
            truncated_diff += "\n\n[... diff truncated ...]"

        user_content = (
            f"COMMIT MESSAGE:\n{commit_message}\n\n"
            f"DIFF:\n{truncated_diff}"
        )

        raw = await self._call_llm(_SYSTEM_PROMPT, user_content)
        return self._parse_response(
            raw, source_type="commit", source_ref=source_ref
        )

    async def extract_from_pr_comments(
        self,
        comments: list[str],
        *,
        source_ref: str = "",
    ) -> list[Decision]:
        """
        Extract architectural decisions from PR/review comments.

        Args:
            comments:   List of comment strings from the PR thread.
            source_ref: PR URL or number for back-reference.

        Returns:
            A list of Decision objects (empty list if none found).
        """
        if not comments:
            return []

        # Concatenate with clear separators
        numbered = "\n\n".join(
            f"--- Comment {i + 1} ---\n{c}" for i, c in enumerate(comments)
        )

        # Truncate if extremely long
        content = numbered[:_MAX_DIFF_CHARS * 2]
        if len(numbered) > _MAX_DIFF_CHARS * 2:
            content += "\n\n[... comments truncated ...]"

        raw = await self._call_llm(_PR_SYSTEM_PROMPT, content)
        return self._parse_response(
            raw, source_type="pr_comment", source_ref=source_ref
        )

    # ── Batch processing with rate limiting ──────────────────────────────

    async def process_commits_batch(
        self,
        commits: list[CommitInfo],
        git_service: GitService,
    ) -> ExtractionStats:
        """
        Process a list of commits in batches of 10 with 200ms delays
        between LLM calls to respect NIM rate limits.

        Args:
            commits:     List of CommitInfo objects to process.
            git_service: GitService instance for fetching diffs.

        Returns:
            ExtractionStats with totals and all found decisions.
        """
        stats = ExtractionStats()
        start_time = time.monotonic()

        # Process in batches
        for batch_start in range(0, len(commits), _BATCH_SIZE):
            batch = commits[batch_start : batch_start + _BATCH_SIZE]

            for commit in batch:
                msg_lower = commit.message.lower().strip()

                # Skip trivial commits without hitting LLM
                if self._is_trivial_commit(msg_lower):
                    stats.skipped_trivial += 1
                    stats.total_processed += 1
                    continue

                try:
                    # Fetch diff for this commit
                    diff = git_service.get_commit_diff(commit.sha)

                    # Extract decisions
                    decisions = await self.extract_from_commit(
                        commit_message=commit.message,
                        diff=diff,
                        source_ref=commit.sha,
                    )

                    stats.decisions_found += len(decisions)
                    stats.decisions.extend(decisions)

                except Exception as exc:
                    logger.warning(
                        "Error extracting from commit %s: %s",
                        commit.sha[:8],
                        exc,
                    )
                    stats.errors += 1

                stats.total_processed += 1

                # Rate limiting: 200ms delay between LLM calls
                await asyncio.sleep(_RATE_LIMIT_DELAY_MS / 1000)

            logger.info(
                "Batch %d-%d processed: %d/%d commits, %d decisions found",
                batch_start + 1,
                min(batch_start + _BATCH_SIZE, len(commits)),
                stats.total_processed,
                len(commits),
                stats.decisions_found,
            )

        stats.elapsed_seconds = time.monotonic() - start_time
        logger.info(
            "Decision extraction complete: %d processed, %d decisions, "
            "%d skipped, %d errors in %.1fs",
            stats.total_processed,
            stats.decisions_found,
            stats.skipped_trivial,
            stats.errors,
            stats.elapsed_seconds,
        )

        return stats

    # ── Internal helpers ─────────────────────────────────────────────────

    async def _call_llm(self, system_prompt: str, user_content: str) -> str:
        """Send the extraction prompt to the LLM and return raw response text."""
        try:
            response = await self._llm.complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,  # Low temp for consistent extraction
                max_tokens=2048,
                stream=False,
                thinking_mode=False,
            )
            return response.content
        except Exception as exc:
            logger.error("LLM call failed during decision extraction: %s", exc)
            return "NONE"

    @staticmethod
    def _parse_response(
        raw: str,
        source_type: str,
        source_ref: str,
    ) -> list[Decision]:
        """
        Parse the LLM response into Decision objects.

        Handles:
          - "NONE" → empty list
          - Single JSON object → one Decision
          - JSON array → multiple Decisions
          - Malformed output → empty list (never crash)
        """
        text = raw.strip()

        # Handle the model wrapping in markdown fences despite instructions
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [
                ln for ln in lines
                if not ln.strip().startswith("```")
            ]
            text = "\n".join(lines).strip()

        # Explicit "no decisions" sentinel
        if not text or text.upper() == "NONE":
            return []

        # Try parsing as JSON
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Failed to parse LLM decision response as JSON: %s — raw: %.200s",
                exc,
                text,
            )
            return []

        # Normalize to list
        if isinstance(data, dict):
            items = [data]
        elif isinstance(data, list):
            items = data
        else:
            logger.warning(
                "Unexpected JSON type from LLM: %s", type(data).__name__
            )
            return []

        # Empty array
        if not items:
            return []

        decisions: list[Decision] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                decisions.append(
                    Decision(
                        title=str(item.get("title", "Untitled Decision")),
                        context=str(item.get("context", "")),
                        decision=str(item.get("decision", "")),
                        reasoning=str(item.get("reasoning", "")),
                        source_type=source_type,
                        source_ref=source_ref,
                        confidence=float(item.get("confidence", 0.0)),
                    )
                )
            except (TypeError, ValueError) as exc:
                logger.warning("Skipping malformed decision entry: %s", exc)

        return decisions

    @staticmethod
    def _is_trivial_commit(msg: str) -> bool:
        """
        Quick heuristic check — skip commits that are almost certainly
        not architectural decisions. Saves an LLM call.
        """
        trivial_prefixes = (
            "fix typo",
            "fix lint",
            "fixup",
            "wip",
            "merge branch",
            "merge pull request",
            "bump version",
            "update changelog",
            "chore:",
            "chore(",
            "style:",
            "style(",
            "docs:",
            "docs(",
            "ci:",
            "ci(",
            "test:",
            "test(",
            "revert ",
        )
        if any(msg.startswith(p) for p in trivial_prefixes):
            return True

        # Very short messages are rarely decisions
        if len(msg.split()) < 5:
            return True

        return False
