"""
NVIDIA NIM LLM Client.

Exclusive LLM provider for CodeGuardian. All completion requests go through
NVIDIA NIM's OpenAI-compatible chat/completions endpoint using raw httpx.

Primary model: qwen/qwen3-coder-480b-a35b-instruct
    - 480B total params, 35B active (MoE), 262K context
    - Supports function calling and thinking mode

NO openai package. NO Ollama. NO local model fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from typing import AsyncGenerator

import httpx

from server.models.llm_models import NIMRequest, NIMResponse, NIMStreamChunk

logger = logging.getLogger("codeguardian.llm")

# ── Thinking-tag regex ───────────────────────────────────────────────────
_THINK_PATTERN = re.compile(r"<think>(.*?)</think>", re.DOTALL)

# ── Retry constants ──────────────────────────────────────────────────────
_MAX_RATE_LIMIT_RETRIES = 3
_RATE_LIMIT_BASE_DELAY = 0.5  # seconds - reduced for faster retries
_SERVER_ERROR_DELAY = 1.0      # seconds - reduced for faster retries
_EXTENDED_TIMEOUT = 120.0      # seconds - increased to avoid retries


class NIMClientError(Exception):
    """Raised when a NIM API call fails after all retries."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class NIMClient:
    """
    Async client for NVIDIA NIM's OpenAI-compatible chat completions API.

    Usage:
        client = NIMClient(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key="nvapi-...",
            model="qwen/qwen3-coder-480b-a35b-instruct",
        )
        response = await client.complete(
            messages=[{"role": "user", "content": "Hello"}],
        )
        print(response.content)
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "qwen/qwen3-coder-480b-a35b-instruct",
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self.last_healthy_at: float | None = None

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

        logger.info(
            "NIMClient initialised — model=%s  base_url=%s  timeout=%.0fs",
            self._model,
            self._base_url,
            self._timeout,
        )

    # ── Public API ───────────────────────────────────────────────────────

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
        thinking_mode: bool = False,
    ) -> NIMResponse | AsyncGenerator[NIMStreamChunk, None]:
        """
        Send a chat completion request to the NIM API.

        Args:
            messages:       Chat history in OpenAI format.
            temperature:    Sampling temperature (0.0–2.0).
            max_tokens:     Maximum tokens to generate.
            stream:         If True, returns an async generator of NIMStreamChunks.
            thinking_mode:  If True, let the model think and separate <think> from answer.
                            If False, suppress thinking via chat_template_kwargs.

        Returns:
            NIMResponse for non-streaming, or an async generator for streaming.
        """
        request = NIMRequest(
            messages=messages,
            model=self._model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            thinking_mode=thinking_mode,
        )

        if stream:
            return self._stream(request)
        return await self._complete(request)

    async def warm_up(self) -> float:
        """
        Send a minimal request to trigger NIM model loading.

        Returns:
            Warmup latency in seconds.

        Should be called once at server startup. If latency > 30s, logs a
        cold-start warning.
        """
        logger.info("🔥 NIM warm-up starting …")
        start = time.monotonic()

        try:
            await self._complete(
                NIMRequest(
                    messages=[{"role": "user", "content": "hi"}],
                    model=self._model,
                    max_tokens=1,
                    stream=False,
                    thinking_mode=False,
                )
            )
            elapsed = time.monotonic() - start

            if elapsed > 30.0:
                logger.warning(
                    "⚠️  NIM warm-up took %.1fs — possible cold start", elapsed
                )
            else:
                logger.info("✅ NIM warm-up complete in %.1fs", elapsed)

            return elapsed

        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "❌ NIM warm-up failed after %.1fs: %s", elapsed, exc
            )
            raise

    async def is_healthy(self) -> bool:
        """
        Attempt a minimal completion to verify NIM connectivity.

        Updates ``last_healthy_at`` on success.

        Returns:
            True if the API responds successfully, False otherwise.
        """
        try:
            await self._complete(
                NIMRequest(
                    messages=[{"role": "user", "content": "ping"}],
                    model=self._model,
                    max_tokens=1,
                    stream=False,
                    thinking_mode=False,
                )
            )
            self.last_healthy_at = time.time()
            return True
        except Exception as exc:
            logger.warning("NIM health check failed: %s", exc)
            return False

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()
        logger.info("NIMClient connection closed")

    # ── Non-streaming implementation ─────────────────────────────────────

    async def _complete(self, request: NIMRequest) -> NIMResponse:
        """Execute a non-streaming chat completion with retry logic."""
        payload = request.to_payload()
        start = time.monotonic()

        response = await self._request_with_retry(payload)
        latency_ms = (time.monotonic() - start) * 1000

        data = response.json()
        raw_content: str = data["choices"][0]["message"]["content"]
        usage: dict = data.get("usage", {})
        model_used: str = data.get("model", self._model)

        # Parse thinking blocks if thinking mode was enabled
        thinking: str | None = None
        content = raw_content

        if request.thinking_mode:
            think_match = _THINK_PATTERN.search(raw_content)
            if think_match:
                thinking = think_match.group(1).strip()
                content = _THINK_PATTERN.sub("", raw_content).strip()

        # Update health timestamp on success
        self.last_healthy_at = time.time()

        return NIMResponse(
            content=content,
            thinking=thinking,
            model_used=model_used,
            latency_ms=round(latency_ms, 2),
            token_usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        )

    # ── Streaming implementation ─────────────────────────────────────────

    async def _stream(
        self, request: NIMRequest
    ) -> AsyncGenerator[NIMStreamChunk, None]:
        """
        Execute a streaming chat completion.

        Yields NIMStreamChunks. When thinking_mode is True, buffers
        content until </think> is seen before yielding answer chunks.
        """
        payload = request.to_payload()

        async with self._client.stream(
            "POST",
            "/chat/completions",
            json=payload,
            timeout=httpx.Timeout(self._timeout, connect=10.0),
        ) as response:
            if response.status_code != 200:
                body = await response.aread()
                raise NIMClientError(
                    f"NIM streaming request failed: {response.status_code} — {body.decode()}",
                    status_code=response.status_code,
                )

            thinking_buffer: list[str] = []
            inside_think = False
            thinking_done = False

            async for raw_line in response.aiter_lines():
                line = raw_line.strip()

                # Skip empty lines
                if not line:
                    continue

                # Strip SSE "data: " prefix
                if line.startswith("data: "):
                    line = line[6:]
                elif line.startswith("data:"):
                    line = line[5:]
                else:
                    continue

                # Handle [DONE] sentinel
                if line.strip() == "[DONE]":
                    # If we were still buffering thinking, yield it
                    if thinking_buffer and not thinking_done:
                        thinking_text = "".join(thinking_buffer)
                        yield NIMStreamChunk(
                            content=thinking_text,
                            is_thinking=True,
                        )
                    return

                # Parse JSON chunk
                try:
                    chunk_data = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("Skipping non-JSON SSE line: %s", line[:80])
                    continue

                choices = chunk_data.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                finish_reason = choices[0].get("finish_reason")
                fragment: str = delta.get("content", "")

                if not fragment and finish_reason is None:
                    continue

                # ── Thinking-mode handling ────────────────────────────
                if request.thinking_mode and not thinking_done:
                    combined = "".join(thinking_buffer) + fragment

                    # Check for <think> opening
                    if not inside_think and "<think>" in combined:
                        inside_think = True
                        # Remove the <think> tag itself
                        combined = combined.split("<think>", 1)[1]
                        thinking_buffer = [combined]
                        continue

                    if inside_think:
                        if "</think>" in fragment:
                            # Thinking block complete
                            thinking_buffer.append(
                                fragment.split("</think>")[0]
                            )
                            thinking_text = "".join(thinking_buffer).strip()
                            thinking_done = True
                            inside_think = False

                            yield NIMStreamChunk(
                                content=thinking_text,
                                is_thinking=True,
                            )

                            # Yield any content after </think> on this line
                            after_think = fragment.split("</think>", 1)[1]
                            if after_think.strip():
                                yield NIMStreamChunk(
                                    content=after_think,
                                    finish_reason=finish_reason,
                                    is_thinking=False,
                                )
                        else:
                            thinking_buffer.append(fragment)
                        continue

                # ── Normal content (or post-thinking answer) ──────────
                if fragment:
                    yield NIMStreamChunk(
                        content=fragment,
                        finish_reason=finish_reason,
                        is_thinking=False,
                    )
                elif finish_reason:
                    yield NIMStreamChunk(
                        content="",
                        finish_reason=finish_reason,
                        is_thinking=False,
                    )

        # Update health timestamp on successful stream
        self.last_healthy_at = time.time()

    # ── Retry engine ─────────────────────────────────────────────────────

    async def _request_with_retry(self, payload: dict) -> httpx.Response:
        """
        POST /chat/completions with retry logic.

        Retry policy:
            - 429 (rate limit): exponential backoff with jitter, up to 3 retries
            - 5xx (server error): 1 retry after 2s
            - Timeout: 1 retry with extended timeout (90s)
            - Connection error: raise immediately
        """
        rate_limit_retries = 0
        server_error_retried = False
        timeout_retried = False

        while True:
            try:
                response = await self._client.post(
                    "/chat/completions",
                    json=payload,
                )

                # ── Success ──────────────────────────────────────────
                if response.status_code == 200:
                    return response

                # ── Rate limited (429) ───────────────────────────────
                if response.status_code == 429:
                    rate_limit_retries += 1
                    if rate_limit_retries > _MAX_RATE_LIMIT_RETRIES:
                        raise NIMClientError(
                            f"Rate limited after {_MAX_RATE_LIMIT_RETRIES} retries",
                            status_code=429,
                        )
                    delay = _RATE_LIMIT_BASE_DELAY * (2 ** (rate_limit_retries - 1))
                    jitter = random.uniform(0, delay * 0.5)
                    wait = delay + jitter
                    logger.warning(
                        "Rate limited (429) — retry %d/%d in %.1fs",
                        rate_limit_retries,
                        _MAX_RATE_LIMIT_RETRIES,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                # ── Server error (5xx) ───────────────────────────────
                if 500 <= response.status_code < 600:
                    if server_error_retried:
                        raise NIMClientError(
                            f"Server error {response.status_code} after retry: "
                            f"{response.text[:200]}",
                            status_code=response.status_code,
                        )
                    server_error_retried = True
                    logger.warning(
                        "Server error (%d) — retrying once in %.0fs",
                        response.status_code,
                        _SERVER_ERROR_DELAY,
                    )
                    await asyncio.sleep(_SERVER_ERROR_DELAY)
                    continue

                # ── Other client errors (4xx) ────────────────────────
                raise NIMClientError(
                    f"NIM API error {response.status_code}: {response.text[:300]}",
                    status_code=response.status_code,
                )

            except httpx.TimeoutException as exc:
                if timeout_retried:
                    raise NIMClientError(
                        f"Request timed out after retry with extended timeout: {exc}"
                    ) from exc
                timeout_retried = True
                logger.warning(
                    "Request timed out — retrying once with %.0fs timeout",
                    _EXTENDED_TIMEOUT,
                )
                # Temporarily extend timeout for the retry
                self._client.timeout = httpx.Timeout(
                    _EXTENDED_TIMEOUT, connect=10.0
                )
                continue

            except httpx.ConnectError as exc:
                raise NIMClientError(
                    f"Cannot connect to NIM API at {self._base_url}: {exc}"
                ) from exc

            finally:
                # Reset timeout to default after any timeout retry
                if timeout_retried:
                    self._client.timeout = httpx.Timeout(
                        self._timeout, connect=10.0
                    )
