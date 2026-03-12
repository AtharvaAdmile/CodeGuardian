"""
Embedding & vector storage data models.

Dataclasses for embedding API communication and vector store operations.
Used by NIMEmbeddingService and VectorService.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class EmbeddingUnavailableError(Exception):
    """
    Raised when the NIM embedding API is unreachable.

    NEVER silently return empty vectors — that would corrupt the vector store
    with zero-distance entries that match everything.
    """

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class VectorDocument:
    """
    A document prepared for insertion into the vector store.

    Attributes:
        id:        Deterministic SHA256 hex (from generate_id).
        text:      The raw text chunk.
        embedding: 1024-dimensional float vector from NIM API.
        metadata:  Arbitrary metadata (file_path, language, chunk_index, etc.).
    """

    id: str
    text: str
    embedding: list[float]
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    """
    A single search hit from the vector store.

    Attributes:
        id:       Document ID.
        text:     The matched text chunk.
        score:    Similarity score (higher = more similar).
        metadata: Metadata associated with the document.
    """

    id: str
    text: str
    score: float
    metadata: dict = field(default_factory=dict)
