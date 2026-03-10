"""
VectorStore class for managing ChromaDB collections and embeddings.
"""
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import time

@dataclass
class CollectionStats:
    """Statistics about a ChromaDB collection."""
    name: str
    count: int
    dimension: Optional[int]


@dataclass
class QueryResult:
    """Result from a vector similarity search."""
    ids: List[str]
    documents: List[str]
    metadatas: List[Dict[str, Any]]
    distances: List[float]
    query_time_ms: float


class VectorStore:
    """
    Manages ChromaDB vector store for code embeddings.
    
    Handles collection creation, embedding storage, similarity search,
    and collection management operations.
    """
    
    def __init__(self, persist_directory: str = "./chroma_data", max_retries: int = 3, retry_delay: float = 1.0):
        """
        Initialize ChromaDB client with persistent storage.
        
        Args:
            persist_directory: Directory path for persistent storage
            max_retries: Maximum number of retry attempts for failed operations
            retry_delay: Initial delay between retries in seconds (exponential backoff)
            
        Raises:
            RuntimeError: If ChromaDB client initialization fails
        """
        self.persist_directory = persist_directory
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        try:
            self.client = chromadb.PersistentClient(path=persist_directory)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize ChromaDB client: {str(e)}")
    
    def create_collection(self, name: str) -> chromadb.Collection:
        """
        Create a new collection or get existing one with retry logic.
        
        Args:
            name: Name of the collection
            
        Returns:
            ChromaDB Collection object
            
        Raises:
            ValueError: If collection name is invalid
            RuntimeError: If collection creation fails after retries
        """
        if not name or not isinstance(name, str):
            raise ValueError("Collection name must be a non-empty string")
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                collection = self.client.get_or_create_collection(
                    name=name,
                    metadata={"hnsw:space": "cosine"}  # Use cosine similarity
                )
                return collection
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    print(f"Collection creation failed (attempt {attempt + 1}/{self.max_retries}), retrying in {delay}s: {str(e)}")
                    time.sleep(delay)
                else:
                    raise RuntimeError(f"Failed to create collection '{name}' after {self.max_retries} attempts: {str(last_error)}")

    def add_embeddings(
        self,
        collection_name: str,
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: Optional[List[str]] = None
    ) -> None:
        """
        Add embeddings to a collection with metadata and retry logic.
        
        Args:
            collection_name: Name of the collection
            embeddings: List of embedding vectors
            documents: List of document texts (code chunks)
            metadatas: List of metadata dicts containing:
                - file_path: str
                - start_line: int
                - end_line: int
                - chunk_type: str (function, class, method, block)
                - language: str
                - function_name: Optional[str]
                - class_name: Optional[str]
            ids: Optional list of unique IDs for each embedding
            
        Raises:
            ValueError: If inputs are invalid or mismatched lengths
            RuntimeError: If adding embeddings fails after retries
        """
        # Validate inputs
        if not embeddings or not documents or not metadatas:
            raise ValueError("Embeddings, documents, and metadatas must be non-empty")
        
        if not (len(embeddings) == len(documents) == len(metadatas)):
            raise ValueError(f"Length mismatch: embeddings({len(embeddings)}), documents({len(documents)}), metadatas({len(metadatas)})")
        
        # Generate IDs if not provided
        if ids is None:
            import uuid
            ids = [str(uuid.uuid4()) for _ in range(len(embeddings))]
        elif len(ids) != len(embeddings):
            raise ValueError(f"IDs length ({len(ids)}) must match embeddings length ({len(embeddings)})")
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                collection = self.client.get_collection(name=collection_name)
                collection.add(
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
                return
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    print(f"Adding embeddings failed (attempt {attempt + 1}/{self.max_retries}), retrying in {delay}s: {str(e)}")
                    time.sleep(delay)
                else:
                    raise RuntimeError(f"Failed to add embeddings to collection '{collection_name}' after {self.max_retries} attempts: {str(last_error)}")
    
    def query(
        self,
        collection_name: str,
        query_embedding: List[float],
        n_results: int = 5
    ) -> QueryResult:
        """
        Query collection for similar embeddings using cosine similarity with retry logic.
        
        Args:
            collection_name: Name of the collection to query
            query_embedding: Query embedding vector
            n_results: Number of results to return
            
        Returns:
            QueryResult containing matching documents and metadata
            
        Raises:
            ValueError: If inputs are invalid
            RuntimeError: If query fails after retries
        """
        if not query_embedding or not isinstance(query_embedding, list):
            raise ValueError("Query embedding must be a non-empty list")
        
        if n_results <= 0:
            raise ValueError("n_results must be positive")
        
        start_time = time.time()
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                collection = self.client.get_collection(name=collection_name)
                
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results
                )
                
                query_time_ms = (time.time() - start_time) * 1000
                
                return QueryResult(
                    ids=results['ids'][0] if results['ids'] else [],
                    documents=results['documents'][0] if results['documents'] else [],
                    metadatas=results['metadatas'][0] if results['metadatas'] else [],
                    distances=results['distances'][0] if results['distances'] else [],
                    query_time_ms=query_time_ms
                )
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    print(f"Query failed (attempt {attempt + 1}/{self.max_retries}), retrying in {delay}s: {str(e)}")
                    time.sleep(delay)
                else:
                    raise RuntimeError(f"Failed to query collection '{collection_name}' after {self.max_retries} attempts: {str(last_error)}")
    
    def delete_collection(self, name: str) -> bool:
        """
        Delete a collection from the vector store with retry logic.
        
        Args:
            name: Name of the collection to delete
            
        Returns:
            True if deletion was successful, False otherwise
        """
        if not name or not isinstance(name, str):
            print(f"Invalid collection name: {name}")
            return False
        
        for attempt in range(self.max_retries):
            try:
                self.client.delete_collection(name=name)
                return True
            except Exception as e:
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    print(f"Delete collection failed (attempt {attempt + 1}/{self.max_retries}), retrying in {delay}s: {str(e)}")
                    time.sleep(delay)
                else:
                    print(f"Failed to delete collection '{name}' after {self.max_retries} attempts: {str(e)}")
                    return False
    
    def get_collection_stats(self, name: str) -> CollectionStats:
        """
        Get statistics about a collection.
        
        Args:
            name: Name of the collection
            
        Returns:
            CollectionStats with count and dimension information
        """
        try:
            collection = self.client.get_collection(name=name)
            count = collection.count()
            
            # Get dimension from first embedding if available
            dimension = None
            if count > 0:
                # Peek at one item to get dimension
                result = collection.peek(limit=1)
                if result['embeddings'] and len(result['embeddings']) > 0:
                    dimension = len(result['embeddings'][0])
            
            return CollectionStats(
                name=name,
                count=count,
                dimension=dimension
            )
        except Exception as e:
            raise ValueError(f"Failed to get stats for collection '{name}': {str(e)}")
