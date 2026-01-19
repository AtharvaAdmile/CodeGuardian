"""
LLM module for CodeGuardian.

Provides the Universal LLM Caller pattern with provider abstraction.
"""

from src.llm.base import LLMProvider, LLMResponse
from src.llm.gemini_provider import GeminiProvider
from src.llm.caller import llm_call, llm_stream

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "GeminiProvider",
    "llm_call",
    "llm_stream",
]
