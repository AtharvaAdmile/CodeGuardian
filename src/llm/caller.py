"""
Universal LLM Caller (Function X).

This module provides the single interface for all LLM calls in CodeGuardian.
All LLM interactions flow through this module, decoupling business logic
from LLM provider implementation.

Pattern:
    Function A (context gathering) → Function X (this module) → LLM Response
"""

from typing import Generator, Optional, Any
import logging

from src.llm.base import LLMProvider, LLMResponse
from src.llm.gemini_provider import GeminiProvider
from src.config.settings import get_settings

logger = logging.getLogger(__name__)

# Global provider instance (lazy initialized)
_provider: Optional[LLMProvider] = None


def get_provider() -> LLMProvider:
    """
    Get the configured LLM provider instance.
    
    Returns:
        LLMProvider instance (Gemini by default)
    """
    global _provider
    
    if _provider is None:
        settings = get_settings()
        
        if not settings.google_api_key:
            raise ValueError(
                "GOOGLE_API_KEY not found. Please set it in your .env file."
            )
        
        _provider = GeminiProvider(
            api_key=settings.google_api_key,
            model=settings.llm.model,
        )
        logger.info(f"Initialized LLM provider: {_provider.name}")
    
    return _provider


def llm_call(
    prompt: str,
    context: str = "",
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **kwargs: Any
) -> str:
    """
    Universal LLM call function (Function X).
    
    This is the single entry point for all synchronous LLM calls.
    Function A modules prepare context and call this function.
    
    Args:
        prompt: The user prompt/question
        context: Additional context from RAG or other sources
        system_prompt: Optional system prompt to set behavior
        temperature: Sampling temperature (uses config default if None)
        max_tokens: Maximum tokens (uses config default if None)
        **kwargs: Provider-specific arguments
        
    Returns:
        Generated text response
        
    Example:
        # Function A gathers context
        context = gather_ask_context(question, project_id)
        
        # Function X makes the LLM call
        answer = llm_call(prompt=question, context=context)
    """
    settings = get_settings()
    provider = get_provider()
    
    # Use config defaults if not specified
    temp = temperature if temperature is not None else settings.llm.temperature
    tokens = max_tokens if max_tokens is not None else settings.llm.max_tokens
    
    response = provider.call(
        prompt=prompt,
        context=context,
        system_prompt=system_prompt,
        temperature=temp,
        max_tokens=tokens,
        **kwargs
    )
    
    return response.content


def llm_stream(
    prompt: str,
    context: str = "",
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **kwargs: Any
) -> Generator[str, None, None]:
    """
    Universal LLM streaming function (Function X - streaming variant).
    
    This is the single entry point for all streaming LLM calls.
    
    Args:
        prompt: The user prompt/question
        context: Additional context from RAG or other sources
        system_prompt: Optional system prompt to set behavior
        temperature: Sampling temperature (uses config default if None)
        max_tokens: Maximum tokens (uses config default if None)
        **kwargs: Provider-specific arguments
        
    Yields:
        Chunks of generated text as they arrive
        
    Example:
        for chunk in llm_stream(prompt=question, context=context):
            print(chunk, end="", flush=True)
    """
    settings = get_settings()
    provider = get_provider()
    
    # Use config defaults if not specified
    temp = temperature if temperature is not None else settings.llm.temperature
    tokens = max_tokens if max_tokens is not None else settings.llm.max_tokens
    
    yield from provider.stream(
        prompt=prompt,
        context=context,
        system_prompt=system_prompt,
        temperature=temp,
        max_tokens=tokens,
        **kwargs
    )


def generate_embedding(text: str) -> list[float]:
    """
    Generate an embedding vector for the given text.
    
    Args:
        text: Text to embed
        
    Returns:
        List of floats representing the embedding vector
    """
    provider = get_provider()
    return provider.generate_embedding(text)


def generate_batch_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for multiple texts in batch.
    
    Args:
        texts: List of texts to embed
        
    Returns:
        List of embedding vectors
    """
    provider = get_provider()
    return provider.generate_batch_embeddings(texts)


def count_tokens(text: str) -> int:
    """
    Count the number of tokens in the given text using the configured provider.
    
    Args:
        text: Text to count tokens for
        
    Returns:
        Number of tokens
    """
    provider = get_provider()
    return provider.count_tokens(text)


def reset_provider() -> None:
    """Reset the global provider instance (useful for testing)."""
    global _provider
    _provider = None
