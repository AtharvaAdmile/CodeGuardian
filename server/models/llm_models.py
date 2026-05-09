"""
LLM data models for NVIDIA NIM API communication.

Dataclasses for request construction, response parsing, and streaming chunks.
All types are framework-agnostic (no openai dependency) and map directly to
NIM's OpenAI-compatible API format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NIMRequest:
    """
    Represents a chat completion request to the NIM API.

    Mirrors the OpenAI-compatible request body:
    POST {base_url}/chat/completions
    """

    messages: list[dict[str, str]]
    model: str = "openai/gpt-oss-120b"
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = False
    thinking_mode: bool = False

    def to_payload(self) -> dict[str, Any]:
        """Convert to the JSON payload expected by the NIM API."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self.messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": self.stream,
        }

        # Suppress <think> tags for faster, more direct responses
        if not self.thinking_mode:
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        return payload


@dataclass
class NIMResponse:
    """
    Parsed response from a non-streaming NIM API call.

    Attributes:
        content:     The assistant's answer (with <think> tags stripped if present).
        thinking:    The content inside <think>...</think> tags (None if thinking
                     was disabled or no thinking block was found).
        model_used:  The model identifier returned by the API.
        latency_ms:  Round-trip time in milliseconds.
        token_usage: Token consumption dict, e.g.
                     {"prompt_tokens": 10, "completion_tokens": 50, "total_tokens": 60}.
    """

    content: str
    model_used: str
    latency_ms: float
    token_usage: dict[str, int] = field(default_factory=dict)
    thinking: str | None = None


@dataclass
class NIMStreamChunk:
    """
    A single chunk from a streaming NIM API response.

    Attributes:
        content:        Text fragment from this SSE event.
        finish_reason:  "stop" when generation is complete, None otherwise.
        is_thinking:    True while the model is inside a <think> block.
    """

    content: str
    finish_reason: str | None = None
    is_thinking: bool = False
