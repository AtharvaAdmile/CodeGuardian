"""
Decision Service — Architectural Decision Record (ADR) management.

Dual-mode storage:
  • Supabase (primary)  — uses the ``decisions`` table + ``decision_anchors``.
  • Local JSON fallback — writes to ``.codeguardian/decisions/`` when offline.

The service never raises on Supabase failures; it falls back to local
storage and logs a warning.
"""

from __future__ import annotations

import json
import logging
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("codeguardian.decisions")


# ── Helpers ──────────────────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length float vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Data container ───────────────────────────────────────────────────────

class DecisionRecord:
    """Lightweight representation of a decision returned by queries."""

    __slots__ = (
        "id", "project_id", "title", "context", "decision",
        "reasoning", "source_type", "source_ref", "author_name",
        "status", "similarity",
    )

    def __init__(self, **kwargs: Any) -> None:
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    def to_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}


# ── Service ──────────────────────────────────────────────────────────────

class DecisionService:
    """
    Manages Architectural Decision Records (ADRs).

    Uses Supabase when available, with a local JSON fallback for offline
    operation. All Supabase errors are swallowed and logged — the service
    degrades gracefully to local-only mode.
    """

    def __init__(
        self,
        supabase_client: Any | None = None,
        local_dir: str = ".codeguardian/decisions",
    ) -> None:
        self._supabase = supabase_client
        self._local_dir = local_dir

        logger.info(
            "DecisionService initialised — supabase=%s  local_dir=%s",
            "connected" if supabase_client else "disabled",
            local_dir,
        )

    # ── store_decision ───────────────────────────────────────────────

    async def store_decision(
        self,
        project_id: str,
        title: str,
        context: str,
        decision: str,
        reasoning: str,
        source_type: str | None = None,
        source_ref: str | None = None,
        author_name: str | None = None,
        embedding: list[float] | None = None,
    ) -> str:
        """
        Store an architectural decision.

        Returns:
            The decision ID (UUID hex string).
        """
        decision_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        row = {
            "id": decision_id,
            "project_id": project_id,
            "title": title,
            "context": context,
            "decision": decision,
            "reasoning": reasoning,
            "source_type": source_type,
            "source_ref": source_ref,
            "author_name": author_name,
            "status": "active",
        }

        # ── Supabase write ───────────────────────────────────────────
        if self._supabase is not None:
            try:
                sb_row = {**row}
                if embedding is not None:
                    sb_row["embedding"] = embedding  # list[float]
                self._supabase.table("decisions").upsert(sb_row).execute()
                logger.debug("Stored decision '%s' in Supabase", title)
                return decision_id
            except Exception as exc:
                logger.warning(
                    "Supabase decision store failed (falling back to local): %s",
                    exc,
                )

        # ── Local JSON fallback ──────────────────────────────────────
        local_row = {**row, "created_at": now}
        if embedding is not None:
            local_row["embedding"] = embedding
        self._write_local(project_id, decision_id, local_row)
        return decision_id

    # ── search_decisions ─────────────────────────────────────────────

    async def search_decisions(
        self,
        project_id: str,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[DecisionRecord]:
        """
        Semantic search over decisions using vector similarity.

        Returns up to *top_k* :class:`DecisionRecord` objects sorted by
        descending similarity.
        """
        # ── Supabase RPC ─────────────────────────────────────────────
        if self._supabase is not None:
            try:
                rpc_response = (
                    self._supabase.rpc(
                        "match_decisions",
                        {
                            "query_embedding": query_embedding,
                            "match_count": top_k,
                            "target_project_id": project_id,
                        },
                    ).execute()
                )

                results: list[DecisionRecord] = []
                for row in rpc_response.data or []:
                    results.append(
                        DecisionRecord(
                            id=row.get("id"),
                            title=row.get("title"),
                            decision=row.get("decision"),
                            reasoning=row.get("reasoning"),
                            status=row.get("status"),
                            similarity=row.get("similarity", 0.0),
                        )
                    )
                return results
            except Exception as exc:
                logger.warning(
                    "Supabase decision search failed (falling back to local): %s",
                    exc,
                )

        # ── Local brute-force cosine search ──────────────────────────
        return self._local_search(project_id, query_embedding, top_k)

    # ── get_decisions_for_file ───────────────────────────────────────

    async def get_decisions_for_file(
        self,
        project_id: str,
        file_path: str,
    ) -> list[DecisionRecord]:
        """
        Return all decisions linked to a specific file.

        On Supabase this queries ``decision_anchors`` joined with
        ``decisions``. Locally it scans JSON files for matching
        ``source_ref``.
        """
        # ── Supabase query ───────────────────────────────────────────
        if self._supabase is not None:
            try:
                # Join decision_anchors → decisions via decision_id,
                # filtering by file path and project.
                response = (
                    self._supabase.table("decision_anchors")
                    .select(
                        "decision_id, decisions!inner("
                        "id, project_id, title, context, decision, "
                        "reasoning, source_type, source_ref, author_name, status"
                        ")"
                    )
                    .eq("decisions.project_id", project_id)
                    .ilike("code_snippet", f"%{file_path}%")
                    .execute()
                )

                results: list[DecisionRecord] = []
                for row in response.data or []:
                    d = row.get("decisions", {})
                    results.append(
                        DecisionRecord(
                            id=d.get("id"),
                            project_id=d.get("project_id"),
                            title=d.get("title"),
                            context=d.get("context"),
                            decision=d.get("decision"),
                            reasoning=d.get("reasoning"),
                            source_type=d.get("source_type"),
                            source_ref=d.get("source_ref"),
                            author_name=d.get("author_name"),
                            status=d.get("status"),
                        )
                    )
                return results
            except Exception as exc:
                logger.warning(
                    "Supabase decision-for-file query failed "
                    "(falling back to local): %s",
                    exc,
                )

        # ── Local scan ───────────────────────────────────────────────
        return self._local_decisions_for_file(project_id, file_path)

    # ── Local storage helpers ────────────────────────────────────────

    def _project_dir(self, project_id: str) -> Path:
        """Return (and create) the local decisions directory for a project."""
        path = Path(self._local_dir) / project_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_local(
        self, project_id: str, decision_id: str, data: dict
    ) -> None:
        """Write a single decision to a local JSON file."""
        path = self._project_dir(project_id) / f"{decision_id}.json"
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        logger.debug("Stored decision '%s' locally at %s", data.get("title"), path)

    def _read_all_local(self, project_id: str) -> list[dict]:
        """Read all local decision JSON files for a project."""
        project_path = Path(self._local_dir) / project_id
        if not project_path.exists():
            return []
        decisions: list[dict] = []
        for fp in project_path.glob("*.json"):
            try:
                decisions.append(json.loads(fp.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping corrupt decision file %s: %s", fp, exc)
        return decisions

    def _local_search(
        self,
        project_id: str,
        query_embedding: list[float],
        top_k: int,
    ) -> list[DecisionRecord]:
        """Brute-force cosine similarity search over local JSON decisions."""
        decisions = self._read_all_local(project_id)
        scored: list[tuple[float, dict]] = []
        for d in decisions:
            emb = d.get("embedding")
            if emb is None:
                continue
            sim = _cosine_similarity(query_embedding, emb)
            scored.append((sim, d))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            DecisionRecord(
                id=d.get("id"),
                title=d.get("title"),
                decision=d.get("decision"),
                reasoning=d.get("reasoning"),
                status=d.get("status"),
                similarity=sim,
            )
            for sim, d in scored[:top_k]
        ]

    def _local_decisions_for_file(
        self,
        project_id: str,
        file_path: str,
    ) -> list[DecisionRecord]:
        """Scan local JSON files for decisions whose source_ref matches."""
        decisions = self._read_all_local(project_id)
        results: list[DecisionRecord] = []
        for d in decisions:
            ref = d.get("source_ref", "") or ""
            if file_path in ref:
                results.append(
                    DecisionRecord(
                        id=d.get("id"),
                        project_id=d.get("project_id"),
                        title=d.get("title"),
                        context=d.get("context"),
                        decision=d.get("decision"),
                        reasoning=d.get("reasoning"),
                        source_type=d.get("source_type"),
                        source_ref=d.get("source_ref"),
                        author_name=d.get("author_name"),
                        status=d.get("status"),
                    )
                )
        return results
