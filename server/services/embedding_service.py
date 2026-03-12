"""
NVIDIA NIM Embedding Service.

All embeddings go through NVIDIA NIM's embedding API using raw httpx.
Model: nvidia/nv-embedqa-e5-v5 (1024-dimensional vectors).

NO sentence-transformers. NO torch. NO local models.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import time

import httpx

from server.models.embedding_models import EmbeddingUnavailableError

logger = logging.getLogger("codeguardian.embedding")

# ── Constants ────────────────────────────────────────────────────────────
_BATCH_SIZE = 50                # Max texts per NIM API call
_MAX_RATE_LIMIT_RETRIES = 3
_RATE_LIMIT_BASE_DELAY = 1.0   # seconds
_SERVER_ERROR_DELAY = 2.0      # seconds
_EXTENDED_TIMEOUT = 90.0       # seconds for timeout retry


class NIMEmbeddingService:
    """
    Async client for NVIDIA NIM's embedding API.

    Usage:
        service = NIMEmbeddingService(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key="nvapi-...",
            model="nvidia/nv-embedqa-e5-v5",
        )
        vectors = await service.embed_documents(["hello", "world"])
        query_vec = await service.embed_query("search term")
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "nvidia/nv-embedqa-e5-v5",
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

        logger.info(
            "NIMEmbeddingService initialised — model=%s  base_url=%s",
            self._model,
            self._base_url,
        )

    # ── Public API ───────────────────────────────────────────────────────

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of document texts for storage.

        Uses input_type="passage" (optimised for document indexing).
        Batches into groups of 50 to respect API limits.

        Args:
            texts: List of text chunks to embed.

        Returns:
            List of 1024-dimensional embedding vectors, one per text.

        Raises:
            EmbeddingUnavailableError: If the NIM API is unreachable.
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i : i + _BATCH_SIZE]
            batch_embeddings = await self._embed_batch(
                batch, input_type="passage"
            )
            all_embeddings.extend(batch_embeddings)

        logger.debug(
            "Embedded %d documents in %d batches",
            len(texts),
            (len(texts) + _BATCH_SIZE - 1) // _BATCH_SIZE,
        )

        return all_embeddings

    async def embed_query(self, text: str) -> list[float]:
        """
        Embed a single query text for retrieval.

        Uses input_type="query" — the NIM model optimises the vector
        for cosine similarity against passage embeddings.

        Args:
            text: The query string.

        Returns:
            A single 1024-dimensional embedding vector.

        Raises:
            EmbeddingUnavailableError: If the NIM API is unreachable.
        """
        embeddings = await self._embed_batch([text], input_type="query")
        return embeddings[0]

    @staticmethod
    def generate_id(project_id: str, file_path: str, chunk_index: int) -> str:
        """
        Generate a deterministic document ID.

        The same (project_id, file_path, chunk_index) triplet always
        produces the same ID, keeping ChromaDB and Supabase in sync.

        Returns:
            SHA256 hex digest string.
        """
        raw = f"{project_id}:{file_path}:{chunk_index}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()
        logger.info("NIMEmbeddingService connection closed")

    # ── Internal ─────────────────────────────────────────────────────────

    async def _embed_batch(
        self, texts: list[str], input_type: str
    ) -> list[list[float]]:
        """
        Call the NIM embedding API for a single batch.

        POST /embeddings
        Body: { "model": ..., "input": [...], "input_type": "passage"|"query" }

        Returns embeddings sorted by the API's index field to guarantee
        the same order as the input texts.
        """
        payload = {
            "model": self._model,
            "input": texts,
            "input_type": input_type,
        }

        start = time.monotonic()
        response = await self._request_with_retry(payload)
        latency_ms = (time.monotonic() - start) * 1000

        data = response.json()
        # Sort by index to preserve input order
        embedding_objects = sorted(data["data"], key=lambda x: x["index"])
        embeddings = [obj["embedding"] for obj in embedding_objects]

        logger.debug(
            "Embedding batch: %d texts, input_type=%s, %.0fms",
            len(texts),
            input_type,
            latency_ms,
        )

        return embeddings

    # ── Retry engine (mirrors llm_client.py pattern) ─────────────────────

    async def _request_with_retry(self, payload: dict) -> httpx.Response:
        """
        POST /embeddings with retry logic.

        Retry policy (same as LLM client):
            - 429 (rate limit): exponential backoff with jitter, up to 3 retries
            - 5xx (server error): 1 retry after 2s
            - Timeout: 1 retry with extended timeout (90s)
            - Connection error: raise EmbeddingUnavailableError immediately
        """
        rate_limit_retries = 0
        server_error_retried = False
        timeout_retried = False

        while True:
            try:
                response = await self._client.post(
                    "/embeddings",
                    json=payload,
                )

                # ── Success ──────────────────────────────────────────
                if response.status_code == 200:
                    return response

                # ── Rate limited (429) ───────────────────────────────
                if response.status_code == 429:
                    rate_limit_retries += 1
                    if rate_limit_retries > _MAX_RATE_LIMIT_RETRIES:
                        raise EmbeddingUnavailableError(
                            f"Rate limited after {_MAX_RATE_LIMIT_RETRIES} retries",
                            status_code=429,
                        )
                    delay = _RATE_LIMIT_BASE_DELAY * (
                        2 ** (rate_limit_retries - 1)
                    )
                    jitter = random.uniform(0, delay * 0.5)
                    wait = delay + jitter
                    logger.warning(
                        "Embedding rate limited (429) — retry %d/%d in %.1fs",
                        rate_limit_retries,
                        _MAX_RATE_LIMIT_RETRIES,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                # ── Server error (5xx) ───────────────────────────────
                if 500 <= response.status_code < 600:
                    if server_error_retried:
                        raise EmbeddingUnavailableError(
                            f"Server error {response.status_code} after retry: "
                            f"{response.text[:200]}",
                            status_code=response.status_code,
                        )
                    server_error_retried = True
                    logger.warning(
                        "Embedding server error (%d) — retrying once in %.0fs",
                        response.status_code,
                        _SERVER_ERROR_DELAY,
                    )
                    await asyncio.sleep(_SERVER_ERROR_DELAY)
                    continue

                # ── Other client errors (4xx) ────────────────────────
                raise EmbeddingUnavailableError(
                    f"NIM Embedding API error {response.status_code}: "
                    f"{response.text[:300]}",
                    status_code=response.status_code,
                )

            except httpx.TimeoutException as exc:
                if timeout_retried:
                    raise EmbeddingUnavailableError(
                        f"Embedding request timed out after retry: {exc}"
                    ) from exc
                timeout_retried = True
                logger.warning(
                    "Embedding request timed out — retrying with %.0fs timeout",
                    _EXTENDED_TIMEOUT,
                )
                self._client.timeout = httpx.Timeout(
                    _EXTENDED_TIMEOUT, connect=10.0
                )
                continue

            except httpx.ConnectError as exc:
                raise EmbeddingUnavailableError(
                    f"Cannot connect to NIM Embedding API at "
                    f"{self._base_url}: {exc}"
                ) from exc

            finally:
                # Reset timeout to default after any timeout retry
                if timeout_retried:
                    self._client.timeout = httpx.Timeout(
                        self._timeout, connect=10.0
                    )
