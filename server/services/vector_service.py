"""
ChromaDB Vector Service.

Local vector store only — ChromaDB PersistentClient for fast local search.
No Supabase, no remote storage.

CodeGuardian works offline with just ChromaDB — it can search existing
embeddings but can't generate new ones without the NIM API.
"""

from __future__ import annotations

import logging
from typing import Any

import chromadb
import os

from server.models.embedding_models import SearchResult, VectorDocument

logger = logging.getLogger("codeguardian.vector")


class VectorService:
    """
    ChromaDB vector store.

    Usage:
        service = VectorService(chromadb_dir="./chroma_data")
        await service.upsert("my_project", documents)
        results = await service.search("my_project", query_embedding, top_k=10)
    """

    def __init__(
        self,
        chromadb_dir: str,
    ) -> None:
        try:
            os.makedirs(chromadb_dir, exist_ok=True)
            self._chroma_client = chromadb.PersistentClient(path=chromadb_dir)
            logger.info("Initialized Persistent ChromaDB at %s", chromadb_dir)
        except Exception as e:
            logger.warning("Failed to initialize Persistent ChromaDB (%s). Falling back to InMemoryClient.", e)
            self._chroma_client = chromadb.InMemoryClient()

        logger.info("VectorService initialised — chromadb_dir=%s", chromadb_dir)

    async def upsert(
        self, project_id: str, documents: list[VectorDocument]
    ) -> None:
        """
        Insert or update documents in ChromaDB.

        Args:
            project_id: The project identifier for collection namespacing.
            documents:  List of VectorDocument objects to upsert.
        """
        if not documents:
            return

        collection_name = f"cg_{project_id}"

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

    async def search(
        self,
        project_id: str,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """
        Search for similar documents in ChromaDB.

        Args:
            project_id:      Project to search within.
            query_embedding: 1024-dim query vector.
            top_k:           Maximum results to return.
            filters:         Optional metadata filters (ChromaDB where clause).

        Returns:
            List of SearchResult objects sorted by score (descending).
        """
        collection_name = f"cg_{project_id}"

        try:
            collection = self._chroma_client.get_collection(name=collection_name)

            query_params: dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": top_k,
            }
            if filters:
                query_params["where"] = filters

            chroma_results = collection.query(**query_params)

            ids = chroma_results.get("ids", [[]])[0]
            documents = chroma_results.get("documents", [[]])[0]
            distances = chroma_results.get("distances", [[]])[0]
            metadatas = chroma_results.get("metadatas", [[]])[0]

            results: list[SearchResult] = []
            for doc_id, text, distance, metadata in zip(
                ids, documents, distances, metadatas
            ):
                score = 1.0 - distance
                results.append(
                    SearchResult(
                        id=doc_id,
                        text=text or "",
                        score=score,
                        metadata=metadata or {},
                    )
                )

            results.sort(key=lambda r: r.score, reverse=True)
            return results[:top_k]

        except Exception as exc:
            logger.debug(
                "ChromaDB search skipped for '%s': %s",
                collection_name,
                exc,
            )
            return []

    def has_project_index(self, project_id: str) -> bool:
        """Return True when ChromaDB has at least one vector for a project."""
        collection_name = f"cg_{project_id}"
        try:
            collection = self._chroma_client.get_collection(name=collection_name)
            return collection.count() > 0
        except Exception:
            return False

    def get_project_index_count(self, project_id: str) -> int:
        """Return the number of chunks in ChromaDB for a project."""
        collection_name = f"cg_{project_id}"
        try:
            collection = self._chroma_client.get_collection(name=collection_name)
            return collection.count()
        except Exception:
            return 0

    async def delete_project(self, project_id: str) -> None:
        """Delete all vectors for a project from ChromaDB."""
        collection_name = f"cg_{project_id}"
        try:
            self._chroma_client.delete_collection(name=collection_name)
            logger.info("Deleted ChromaDB collection '%s'", collection_name)
        except Exception as exc:
            logger.warning(
                "ChromaDB delete failed for '%s': %s",
                collection_name,
                exc,
            )

    async def close(self) -> None:
        """Cleanup resources."""
        logger.info("VectorService closed")
