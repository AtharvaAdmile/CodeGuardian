"""
Embedding Generator module for generating vector embeddings from text using sentence-transformers.
"""

import torch
from sentence_transformers import SentenceTransformer
from typing import List, Union
import time


class EmbeddingGenerator:
    """
    Generates vector embeddings for code chunks using sentence-transformers.
    
    Uses the all-MiniLM-L6-v2 model which produces 384-dimensional embeddings.
    Automatically detects and uses GPU if available, otherwise falls back to CPU.
    """
    
    MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION = 384
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        """
        Initialize the EmbeddingGenerator with the sentence-transformers model.
        Automatically detects GPU/CPU and loads the model on the appropriate device.
        
        Args:
            max_retries: Maximum number of retry attempts for failed operations
            retry_delay: Initial delay between retries in seconds (exponential backoff)
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Detect device (GPU if available, otherwise CPU)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        try:
            # Initialize the SentenceTransformer model
            self.model = SentenceTransformer(self.MODEL_NAME, device=self.device)
            print(f"EmbeddingGenerator initialized on device: {self.device}")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize embedding model: {str(e)}")
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text string with retry logic.
        
        Args:
            text: The text string to embed
            
        Returns:
            A list of floats representing the embedding vector (384 dimensions)
            
        Raises:
            ValueError: If text is invalid
            RuntimeError: If embedding generation fails after retries
        """
        if not text or not isinstance(text, str):
            raise ValueError("Text must be a non-empty string")
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                # Generate embedding and convert to list
                embedding = self.model.encode(text, convert_to_tensor=False)
                return embedding.tolist()
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    print(f"Embedding generation failed (attempt {attempt + 1}/{self.max_retries}), retrying in {delay}s: {str(e)}")
                    time.sleep(delay)
                else:
                    raise RuntimeError(f"Failed to generate embedding after {self.max_retries} attempts: {str(last_error)}")
    
    def generate_batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of text strings with retry logic.
        More efficient than calling generate_embedding() multiple times.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            A list of embedding vectors, one for each input text
            
        Raises:
            ValueError: If texts are invalid
            RuntimeError: If batch embedding generation fails after retries
        """
        if not texts or not isinstance(texts, list):
            raise ValueError("Texts must be a non-empty list")
        
        if not all(isinstance(text, str) and text for text in texts):
            raise ValueError("All texts must be non-empty strings")
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                # Generate embeddings in batch and convert to list
                embeddings = self.model.encode(texts, convert_to_tensor=False, batch_size=32)
                return embeddings.tolist()
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    print(f"Batch embedding generation failed (attempt {attempt + 1}/{self.max_retries}), retrying in {delay}s: {str(e)}")
                    time.sleep(delay)
                else:
                    raise RuntimeError(f"Failed to generate batch embeddings after {self.max_retries} attempts: {str(last_error)}")
    
    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of the embedding vectors produced by this model.
        
        Returns:
            The embedding dimension (384 for all-MiniLM-L6-v2)
        """
        return self.EMBEDDING_DIMENSION
