"""
Dual-Write Vector Service.

ChromaDB for fast local search (always available).
Supabase pgvector for team sharing (optional).

CodeGuardian works offline with just ChromaDB — it can search existing
embeddings but can't generate new ones without the NIM API.
"""

from __future__ import annotations

import logging
from typing import Any

import chromadb

from server.models.embedding_models import SearchResult, VectorDocument

logger = logging.getLogger("codeguardian.vector")


class VectorService:
    """
    Dual-write vector store: ChromaDB (local) + optional Supabase (remote).

    Usage:
        service = VectorService(
            chromadb_dir="./chroma_data",
            supabase_client=supabase_client,  # or None for offline
        )
        await service.upsert("my_project", documents)
        results = await service.search("my_project", query_embedding, top_k=10)
    """

    def __init__(
        self,
        chromadb_dir: str,
        supabase_client: Any | None = None,
    ) -> None:
        # ── ChromaDB (always available) ──────────────────────────────
        self._chroma_client = chromadb.PersistentClient(path=chromadb_dir)
        self._chromadb_dir = chromadb_dir

        # ── Supabase (optional) ──────────────────────────────────────
        self._supabase = supabase_client

        logger.info(
            "VectorService initialised — chromadb_dir=%s  supabase=%s",
            chromadb_dir,
            "connected" if supabase_client else "disabled",
        )

    # ── Public API ───────────────────────────────────────────────────────

    async def upsert(
        self, project_id: str, documents: list[VectorDocument]
    ) -> None:
        """
        Insert or update documents in both stores.

        ChromaDB write is always performed. Supabase write is best-effort
        (failures are logged but do not raise).

        Args:
            project_id: The project identifier for collection namespacing.
            documents:  List of VectorDocument objects to upsert.
        """
        if not documents:
            return

        collection_name = f"cg_{project_id}"

        # ── ChromaDB upsert ──────────────────────────────────────────
        collection = self._chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        collection.upsert(
            ids=[doc.id for doc in documents],
            documents=[doc.text for doc in documents],
            embeddings=[doc.embedding for doc in documents],
            metadatas=[doc.metadata for doc in documents],
        )

        logger.debug(
            "ChromaDB upsert: %d documents into '%s'",
            len(documents),
            collection_name,
        )

        # ── Supabase upsert (best-effort) ────────────────────────────
        if self._supabase is not None:
            try:
                # Map VectorDocument fields to code_embeddings table columns.
                # Structured fields are extracted from metadata; everything
                # else goes into the metadata_json JSONB column.
                _structured_keys = {
                    "file_path", "chunk_type", "language",
                    "start_line", "end_line",
                }
                rows = [
                    {
                        "id": doc.id,
                        "project_id": project_id,
                        "file_path": doc.metadata.get("file_path", ""),
                        "chunk_text": doc.text,
                        "chunk_type": doc.metadata.get("chunk_type"),
                        "language": doc.metadata.get("language"),
                        "start_line": doc.metadata.get("start_line"),
                        "end_line": doc.metadata.get("end_line"),
                        "embedding": doc.embedding,  # list[float] — Supabase handles vector conversion
                        "metadata_json": {
                            k: v
                            for k, v in doc.metadata.items()
                            if k not in _structured_keys
                        },
                    }
                    for doc in documents
                ]
                self._supabase.table("code_embeddings").upsert(rows).execute()

                logger.debug(
                    "Supabase upsert: %d rows into code_embeddings",
                    len(rows),
                )
            except Exception as exc:
                logger.warning(
                    "Supabase upsert failed (non-fatal): %s", exc
                )

    async def search(
        self,
        project_id: str,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """
        Search for similar documents.

        Always queries ChromaDB first (fast, local). If ChromaDB returns
        fewer than top_k results and Supabase is available, supplements
        with remote results and deduplicates by ID.

        Args:
            project_id:      Project to search within.
            query_embedding: 1024-dim query vector.
            top_k:           Maximum results to return.
            filters:         Optional metadata filters (ChromaDB where clause).

        Returns:
            List of SearchResult objects sorted by score (descending).
        """
        collection_name = f"cg_{project_id}"
        results: list[SearchResult] = []
        seen_ids: set[str] = set()

        # ── ChromaDB search ──────────────────────────────────────────
        try:
            collection = self._chroma_client.get_collection(
                name=collection_name
            )

            query_params: dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": top_k,
            }
            if filters:
                query_params["where"] = filters

            chroma_results = collection.query(**query_params)

            # Unpack ChromaDB's nested list format
            ids = chroma_results.get("ids", [[]])[0]
            documents = chroma_results.get("documents", [[]])[0]
            distances = chroma_results.get("distances", [[]])[0]
            metadatas = chroma_results.get("metadatas", [[]])[0]

            for doc_id, text, distance, metadata in zip(
                ids, documents, distances, metadatas
            ):
                # ChromaDB returns distances; convert to similarity score
                # For cosine space: similarity = 1 - distance
                score = 1.0 - distance
                results.append(
                    SearchResult(
                        id=doc_id,
                        text=text or "",
                        score=score,
                        metadata=metadata or {},
                    )
                )
                seen_ids.add(doc_id)

        except Exception as exc:
            # Collection might not exist yet
            logger.debug(
                "ChromaDB search skipped for '%s': %s",
                collection_name,
                exc,
            )

        # ── Supabase supplement (if needed) ──────────────────────────
        if len(results) < top_k and self._supabase is not None:
            try:
                remaining = top_k - len(results)
                rpc_response = (
                    self._supabase.rpc(
                        "match_code_embeddings",
                        {
                            "query_embedding": query_embedding,
                            "match_count": remaining,
                            "filter_project_id": project_id,
                        },
                    ).execute()
                )

                for row in rpc_response.data or []:
                    row_id = row["id"]
                    if row_id not in seen_ids:
                        # Reconstruct metadata from structured columns
                        # + the metadata_json JSONB blob.
                        metadata = row.get("metadata_json") or {}
                        metadata.update(
                            {
                                "file_path": row.get("file_path", ""),
                                "chunk_type": row.get("chunk_type"),
                                "language": row.get("language"),
                                "start_line": row.get("start_line"),
                                "end_line": row.get("end_line"),
                            }
                        )
                        results.append(
                            SearchResult(
                                id=row_id,
                                text=row.get("chunk_text", ""),
                                score=row.get("similarity", 0.0),
                                metadata=metadata,
                            )
                        )
                        seen_ids.add(row_id)

                logger.debug(
                    "Supabase supplemented %d additional results",
                    len(rpc_response.data or []),
                )
            except Exception as exc:
                logger.warning(
                    "Supabase search failed (non-fatal): %s", exc
                )

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)

        return results[:top_k]

    async def delete_project(self, project_id: str) -> None:
        """
        Delete all vectors for a project from both stores.

        Args:
            project_id: The project to remove.
        """
        collection_name = f"cg_{project_id}"

        # ── ChromaDB ─────────────────────────────────────────────────
        try:
            self._chroma_client.delete_collection(name=collection_name)
            logger.info("Deleted ChromaDB collection '%s'", collection_name)
        except Exception as exc:
            logger.warning(
                "ChromaDB delete failed for '%s': %s",
                collection_name,
                exc,
            )

        # ── Supabase ─────────────────────────────────────────────────
        if self._supabase is not None:
            try:
                self._supabase.table("code_embeddings").delete().eq(
                    "project_id", project_id
                ).execute()
                logger.info(
                    "Deleted Supabase rows for project '%s'", project_id
                )
            except Exception as exc:
                logger.warning(
                    "Supabase delete failed for project '%s': %s",
                    project_id,
                    exc,
                )

    async def close(self) -> None:
        """Cleanup resources."""
        logger.info("VectorService closed")
