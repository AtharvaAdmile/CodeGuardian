"""
Google Gemini LLM provider implementation.

Implements the LLMProvider interface for Google's Gemini API.
"""

import google.generativeai as genai
from typing import Generator, Optional, Dict, Any, List
import logging

from src.llm.base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """
    Google Gemini LLM provider.
    
    Supports both chat completion and embedding generation.
    """
    
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        """
        Initialize Gemini provider.
        
        Args:
            api_key: Google API key
            model: Model name (default: gemini-2.0-flash)
        """
        self._api_key = api_key
        self._model_name = model
        self._embedding_model = "models/text-embedding-004"
        self._embedding_dimension = 768
        
        # Configure the API
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)
        
        logger.info(f"GeminiProvider initialized with model: {model}")
    
    @property
    def name(self) -> str:
        """Provider name identifier."""
        return "gemini"
    
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
        Make a synchronous Gemini API call.
        
        Args:
            prompt: The user prompt/question
            context: Additional context (e.g., from RAG retrieval)
            system_prompt: Optional system prompt to set behavior
            temperature: Sampling temperature (0.0 - 1.0)
            max_tokens: Maximum tokens in response
            **kwargs: Additional Gemini-specific arguments
            
        Returns:
            LLMResponse with the generated content
        """
        # Build the full prompt
        full_prompt = self._build_prompt(prompt, context, system_prompt)
        
        # Configure generation settings
        generation_config = genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        
        try:
            response = self._model.generate_content(
                full_prompt,
                generation_config=generation_config,
            )
            
            return LLMResponse(
                content=response.text,
                model=self._model_name,
                finish_reason=response.candidates[0].finish_reason.name if response.candidates else None,
            )
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise
    
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
        Make a streaming Gemini API call.
        
        Args:
            prompt: The user prompt/question
            context: Additional context (e.g., from RAG retrieval)
            system_prompt: Optional system prompt to set behavior
            temperature: Sampling temperature (0.0 - 1.0)
            max_tokens: Maximum tokens in response
            **kwargs: Additional Gemini-specific arguments
            
        Yields:
            Chunks of generated text as they arrive
        """
        # Build the full prompt
        full_prompt = self._build_prompt(prompt, context, system_prompt)
        
        # Configure generation settings
        generation_config = genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        
        try:
            response = self._model.generate_content(
                full_prompt,
                generation_config=generation_config,
                stream=True,
            )
            
            for chunk in response:
                if chunk.text:
                    yield chunk.text
                    
        except Exception as e:
            logger.error(f"Gemini streaming call failed: {e}")
            raise
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate an embedding vector using Gemini embedding model.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector (768 dimensions)
        """
        if not text or not isinstance(text, str):
            raise ValueError("Text must be a non-empty string")
        
        try:
            result = genai.embed_content(
                model=self._embedding_model,
                content=text,
                task_type="retrieval_document",
            )
            return result["embedding"]
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise
    
    def generate_batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors (768 dimensions each)
        """
        if not texts or not isinstance(texts, list):
            raise ValueError("Texts must be a non-empty list")
        
        if not all(isinstance(text, str) and text for text in texts):
            raise ValueError("All texts must be non-empty strings")
        
        embeddings = []
        try:
            # Gemini embedding API supports batching
            result = genai.embed_content(
                model=self._embedding_model,
                content=texts,
                task_type="retrieval_document",
            )
            embeddings = result["embedding"]
            return embeddings
        except Exception as e:
            logger.error(f"Batch embedding generation failed: {e}")
            raise

    def count_tokens(self, text: str) -> int:
        """
        Count the number of tokens in the given text using a local heuristic.
        This avoids making API calls and hitting quota limits.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Estimated number of tokens
        """
        if not text:
            return 0
        
        # Local heuristic for code and text: 
        # 1 token is roughly 3 characters for code, 4 for prose.
        # We use a conservative 3.2 to balance it out.
        token_estimate = max(1, int(len(text) / 3.2))
        return token_estimate
    
    def _build_prompt(
        self,
        prompt: str,
        context: str = "",
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Build the full prompt with context and system instructions.
        
        Args:
            prompt: User prompt
            context: Additional context
            system_prompt: System instructions
            
        Returns:
            Combined prompt string
        """
        parts = []
        
        if system_prompt:
            parts.append(f"System: {system_prompt}\n\n")
        
        if context:
            parts.append(f"Context:\n{context}\n\n")
        
        parts.append(f"User: {prompt}")
        
        return "".join(parts)
