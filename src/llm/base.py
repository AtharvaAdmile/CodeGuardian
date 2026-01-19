"""
Base LLM provider interface.

Defines the abstract interface that all LLM providers must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generator, Optional, Dict, Any


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None
    finish_reason: Optional[str] = None


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    All LLM providers (Gemini, OpenAI, etc.) must implement this interface.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name identifier."""
        pass
    
    @abstractmethod
    def call(
        self,
        prompt: str,
        context: str = "",
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any
    ) -> LLMResponse:
        """
        Make a synchronous LLM call.
        
        Args:
            prompt: The user prompt/question
            context: Additional context (e.g., from RAG retrieval)
            system_prompt: Optional system prompt to set behavior
            temperature: Sampling temperature (0.0 - 1.0)
            max_tokens: Maximum tokens in response
            **kwargs: Provider-specific arguments
            
        Returns:
            LLMResponse with the generated content
        """
        pass
    
    @abstractmethod
    def stream(
        self,
        prompt: str,
        context: str = "",
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any
    ) -> Generator[str, None, None]:
        """
        Make a streaming LLM call.
        
        Args:
            prompt: The user prompt/question
            context: Additional context (e.g., from RAG retrieval)
            system_prompt: Optional system prompt to set behavior
            temperature: Sampling temperature (0.0 - 1.0)
            max_tokens: Maximum tokens in response
            **kwargs: Provider-specific arguments
            
        Yields:
            Chunks of generated text as they arrive
        """
        pass
    
    @abstractmethod
    def generate_embedding(self, text: str) -> list[float]:
        """
        Generate an embedding vector for the given text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        pass
    
    @abstractmethod
    def generate_batch_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """
        Count the number of tokens in the given text.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Number of tokens
        """
        pass
