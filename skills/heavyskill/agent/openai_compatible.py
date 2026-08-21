"""
OpenAI-Compatible Async HTTP Client

Provides an async client for OpenAI-compatible API endpoints using httpx.
Supports exponential backoff retry logic and separate models for reasoning vs deliberation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Structured response from an LLM API call."""

    content: str
    model: str
    finish_reason: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_seconds: float = 0.0
    raw_response: Optional[Dict[str, Any]] = None
    reasoning_content: str = ""
    # P54：finish_reason == "length" 表示输出被 max_tokens 硬截断，上游必须显式处理
    truncated: bool = False
    # P54：content 为空时回退到 reasoning_content（思维链）——该轨迹没有可靠的
    # "最终答案"，不应参与共识投票（但仍可作为审议素材）
    content_fallback: bool = False


@dataclass
class OpenAICompatibleClient:
    """Async HTTP client for OpenAI-compatible API endpoints.

    Supports retry with exponential backoff, separate models for
    reasoning vs deliberation, and structured response parsing.

    Attributes:
        api_base: Base URL for the API (e.g., https://api.deepseek.com/v1).
        api_key: Bearer token for authentication.
        model: Default model name for reasoning.
        summary_model: Model name for deliberation/summary.
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retry attempts.
        retry_base_delay: Base delay for exponential backoff.
    """

    api_base: str = "https://api.deepseek.com/v1"
    api_key: str = "<YOUR_DEEPSEEK_API_KEY>"
    model: str = "deepseek-v3"
    summary_model: str = "deepseek-v3"
    timeout: float = 120.0
    max_retries: int = 3
    retry_base_delay: float = 1.0

    # Internal state
    _client: Optional[httpx.AsyncClient] = field(default=None, repr=False)

    @property
    def chat_url(self) -> str:
        """Full URL for chat completions endpoint."""
        base = self.api_base.rstrip("/")
        return f"{base}/chat/completions"

    @property
    def headers(self) -> Dict[str, str]:
        """HTTP headers including authorization."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the httpx async client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=30.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> OpenAICompatibleClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat completion request with retry logic.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: Model name override (uses self.model if None).
            temperature: Sampling temperature (0-2).
            max_tokens: Maximum tokens in response.
            **kwargs: Additional parameters passed to the API.

        Returns:
            LLMResponse with the generated content and metadata.

        Raises:
            httpx.HTTPStatusError: After all retries exhausted for HTTP errors.
            httpx.RequestError: After all retries exhausted for connection errors.
        """
        target_model = model or self.model
        payload = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            start_time = time.monotonic()
            try:
                client = await self._get_client()
                response = await client.post(
                    self.chat_url,
                    headers=self.headers,
                    json=payload,
                )
                response.raise_for_status()
                latency = time.monotonic() - start_time

                data = response.json()
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                usage = data.get("usage", {})

                # Support reasoning models (deepseek-v4-pro etc.)
                # reasoning models put output in reasoning_content, content may be empty
                content = message.get("content", "")
                reasoning = message.get("reasoning_content", "")
                finish_reason = choice.get("finish_reason")
                content_fallback = bool(not content and reasoning)
                if content_fallback:
                    # P54：思维链当作轨迹 = 没有"最终答案"，标记 content_fallback，
                    # 上游据此排除其参与共识投票
                    content = reasoning

                return LLMResponse(
                    content=content,
                    model=data.get("model", target_model),
                    finish_reason=finish_reason,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    latency_seconds=latency,
                    raw_response=data,
                    reasoning_content=reasoning,
                    truncated=(finish_reason == "length"),
                    content_fallback=content_fallback,
                )

            except httpx.HTTPStatusError as e:
                last_error = e
                status_code = e.response.status_code
                # Log response body for debugging
                try:
                    error_body = e.response.text[:300]
                except:
                    error_body = "N/A"
                # Don't retry on client errors (4xx) except 429 (rate limit)
                if 400 <= status_code < 500 and status_code != 429:
                    logger.error(
                        f"HTTP {status_code} error (attempt {attempt + 1}): {e}\nResponse: {error_body}"
                    )
                    raise
                logger.warning(
                    f"HTTP {status_code} error (attempt {attempt + 1}/{self.max_retries + 1}): {e}\nResponse: {error_body}"
                )

            except (httpx.RequestError, httpx.TimeoutException) as e:
                last_error = e
                logger.warning(
                    f"Request error (attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                )

            except Exception as e:
                last_error = e
                logger.error(
                    f"Unexpected error (attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                )

            # Exponential backoff (skip on last attempt)
            if attempt < self.max_retries:
                delay = self.retry_base_delay * (2 ** attempt)
                logger.debug(f"Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)

        # All retries exhausted
        raise last_error  # type: ignore[misc]

    async def chat_completions_parallel(
        self,
        messages_list: List[List[Dict[str, str]]],
        model: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        concurrency_limit: int = 8,
        **kwargs: Any,
    ) -> List[LLMResponse]:
        """Send multiple chat completion requests in parallel.

        Args:
            messages_list: List of message lists, one per request.
            model: Model name override.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens per response.
            concurrency_limit: Maximum concurrent requests.
            **kwargs: Additional parameters passed to each request.

        Returns:
            List of LLMResponse objects in the same order as input.
        """
        semaphore = asyncio.Semaphore(concurrency_limit)

        async def _bounded_request(
            messages: List[Dict[str, str]],
        ) -> LLMResponse:
            async with semaphore:
                return await self.chat_completion(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )

        logger.info(
            f"Launching {len(messages_list)} parallel requests "
            f"(concurrency_limit={concurrency_limit})"
        )

        tasks = [_bounded_request(msgs) for msgs in messages_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error responses
        responses: List[LLMResponse] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Request {i} failed: {result}")
                responses.append(
                    LLMResponse(
                        content=f"[ERROR: {result}]",
                        model=model or self.model,
                        finish_reason="error",
                    )
                )
            else:
                responses.append(result)

        return responses

    async def reasoning_call(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 1.0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """Make a call using the reasoning model."""
        return await self.chat_completion(
            messages=messages,
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    async def deliberation_call(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """Make a call using the deliberation/summary model."""
        return await self.chat_completion(
            messages=messages,
            model=self.summary_model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
