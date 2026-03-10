"""
QueryEngine module for processing user questions and retrieving relevant code chunks.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from src.embedding_generator import EmbeddingGenerator
from src.vector_store import VectorStore, QueryResult


@dataclass
class CodeChunk:
    """Represents a code chunk with metadata."""
    id: str
    content: str
    file_path: str
    start_line: int
    end_line: int
    chunk_type: str
    language: str
    distance: float
    metadata: Dict[str, Any]


@dataclass
class Message:
    """Represents a conversation message."""
    role: str  # 'user' or 'assistant'
    content: str


@dataclass
class RetrievalResult:
    """Result from query engine retrieval."""
    chunks: List[CodeChunk]
    query_time_ms: float
    total_retrieved: int


class QueryEngine:
    """
    Processes user questions and retrieves relevant code chunks.
    
    Uses a two-stage retrieval process:
    1. Vector similarity search to get top 10 candidates
    2. Reranking to select the top 5 most relevant chunks
    """
    
    def __init__(
        self,
        embedding_generator: EmbeddingGenerator,
        vector_store: VectorStore,
        collection_name: str
    ):
        """
        Initialize the QueryEngine.
        
        Args:
            embedding_generator: EmbeddingGenerator instance for query embeddings
            vector_store: VectorStore instance for similarity search
            collection_name: Name of the ChromaDB collection to query
        """
        self.embedding_generator = embedding_generator
        self.vector_store = vector_store
        self.collection_name = collection_name

    def query(
        self,
        question: str,
        conversation_context: Optional[List[Message]] = None
    ) -> RetrievalResult:
        """
        Process a natural language question and retrieve relevant code chunks.
        
        Args:
            question: Natural language question from the user
            conversation_context: Optional list of previous conversation messages
            
        Returns:
            RetrievalResult containing top 5 relevant code chunks
            
        Raises:
            ValueError: If question is invalid
        """
        # Validate question
        if not question or not isinstance(question, str):
            raise ValueError("Question must be a non-empty string")
        
        question = question.strip()
        if not question:
            raise ValueError("Question cannot be whitespace only")
        
        # Enhance question with conversation context if available
        enhanced_question = self._enhance_question_with_context(
            question, conversation_context
        )
        
        # Generate embedding for the question
        query_embedding = self.embedding_generator.generate_embedding(enhanced_question)
        
        # Retrieve top 10 similar chunks from vector store
        initial_chunks = self.retrieve_chunks(query_embedding, n_results=10)
        
        # Rerank to get top 5 most relevant chunks
        top_chunks = self.rerank_results(initial_chunks, question)
        
        return RetrievalResult(
            chunks=top_chunks,
            query_time_ms=0,  # Will be calculated in retrieve_chunks
            total_retrieved=len(initial_chunks)
        )
    
    def retrieve_chunks(
        self,
        query_embedding: List[float],
        n_results: int = 10
    ) -> List[CodeChunk]:
        """
        Query ChromaDB for top N similar code chunks.
        
        Args:
            query_embedding: Embedding vector for the query
            n_results: Number of results to retrieve (default: 10)
            
        Returns:
            List of CodeChunk objects with similarity scores
        """
        # Query the vector store
        result = self.vector_store.query(
            collection_name=self.collection_name,
            query_embedding=query_embedding,
            n_results=n_results
        )
        
        # Convert QueryResult to list of CodeChunk objects
        chunks = []
        for i in range(len(result.ids)):
            metadata = result.metadatas[i]
            chunk = CodeChunk(
                id=result.ids[i],
                content=result.documents[i],
                file_path=metadata.get("file_path", ""),
                start_line=metadata.get("start_line", 0),
                end_line=metadata.get("end_line", 0),
                chunk_type=metadata.get("chunk_type", ""),
                language=metadata.get("language", ""),
                distance=result.distances[i],
                metadata=metadata
            )
            chunks.append(chunk)
        
        return chunks
    
    def rerank_results(
        self,
        chunks: List[CodeChunk],
        question: str
    ) -> List[CodeChunk]:
        """
        Rerank retrieved chunks to select the top 5 most relevant.
        
        Uses a simple scoring mechanism based on:
        - Distance score (lower is better)
        - Keyword matching between question and code content
        - Chunk type preference (functions > classes > blocks)
        
        Args:
            chunks: List of CodeChunk objects to rerank
            question: Original user question
            
        Returns:
            Top 5 most relevant CodeChunk objects
        """
        if len(chunks) <= 5:
            return chunks
        
        # Score each chunk
        scored_chunks = []
        question_lower = question.lower()
        question_words = set(question_lower.split())
        
        for chunk in chunks:
            # Base score from distance (lower distance = higher relevance)
            # Normalize distance to 0-1 range and invert
            distance_score = 1.0 - min(chunk.distance, 2.0) / 2.0
            
            # Keyword matching score
            content_lower = chunk.content.lower()
            matching_words = sum(1 for word in question_words if word in content_lower)
            keyword_score = min(matching_words / max(len(question_words), 1), 1.0)
            
            # Chunk type preference score
            type_scores = {
                "function": 1.0,
                "method": 1.0,
                "class": 0.8,
                "block": 0.6
            }
            type_score = type_scores.get(chunk.chunk_type, 0.5)
            
            # Combined score (weighted average)
            final_score = (
                distance_score * 0.6 +
                keyword_score * 0.3 +
                type_score * 0.1
            )
            
            scored_chunks.append((final_score, chunk))
        
        # Sort by score (descending) and return top 5
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in scored_chunks[:5]]
    
    def _enhance_question_with_context(
        self,
        question: str,
        conversation_context: Optional[List[Message]]
    ) -> str:
        """
        Enhance the question with conversation context for better retrieval.
        
        Args:
            question: Current user question
            conversation_context: Previous conversation messages
            
        Returns:
            Enhanced question string
        """
        if not conversation_context or len(conversation_context) == 0:
            return question
        
        # Extract key terms from recent conversation (last 3 messages)
        recent_messages = conversation_context[-3:]
        context_terms = []
        
        for msg in recent_messages:
            if msg.role == "user":
                # Extract potential code-related terms (simple heuristic)
                words = msg.content.split()
                for word in words:
                    # Look for potential function/class names (camelCase, snake_case)
                    if "_" in word or (word and word[0].isupper()):
                        context_terms.append(word)
        
        # Combine question with context terms
        if context_terms:
            enhanced = f"{question} {' '.join(context_terms[:5])}"
            return enhanced
        
        return question
