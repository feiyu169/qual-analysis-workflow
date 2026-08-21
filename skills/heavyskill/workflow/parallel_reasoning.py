"""
HeavySkill Stage 1: Parallel Reasoning

Spawns K concurrent LLM requests, each with temperature=1.0 for diversity.
Each trajectory is independent with no shared context, allowing the model
to explore diverse reasoning paths.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.openai_compatible import LLMResponse, OpenAICompatibleClient
from configuration import (
    HeavySkillConfig,
    PromptType,
    Language,
    get_reasoning_system_prompt,
)
from .utils import extract_answer

logger = logging.getLogger(__name__)


@dataclass
class ReasoningResult:
    """Result from the parallel reasoning stage."""

    trajectories: List[str]  # Raw trajectory texts
    answers: List[Optional[str]]  # Extracted answers
    responses: List[LLMResponse]  # Full API responses
    total_tokens: int = 0
    total_latency: float = 0.0
    successful_count: int = 0
    failed_count: int = 0
    # P54：finish_reason == "length" 的轨迹数——>0 说明输出被 max_tokens 截断，
    # 消费端必须感知（这些轨迹已从审议/共识中剔除）
    truncated_count: int = 0
    # P54：content 为空回退思维链的轨迹数——无可靠"最终答案"，不参与共识投票
    content_fallback_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "trajectories": self.trajectories,
            "answers": self.answers,
            "total_tokens": self.total_tokens,
            "total_latency": self.total_latency,
            "successful_count": self.successful_count,
            "failed_count": self.failed_count,
            "truncated_count": self.truncated_count,
            "content_fallback_count": self.content_fallback_count,
            # P54：逐轨迹截断标记，供消费端精确判断
            "truncated_flags": [r.truncated for r in self.responses],
            "finish_reasons": [r.finish_reason for r in self.responses],
        }


@dataclass
class ParallelReasoner:
    """Stage 1: Parallel Reasoning.

    Spawns K independent reasoning trajectories in parallel. Each trajectory
    uses temperature=1.0 for maximum diversity. No context is shared between
    trajectories, allowing independent exploration of the solution space.

    Usage:
        async with ParallelReasoner(config) as reasoner:
            result = await reasoner.reason("What is 2+2?")
    """

    config: HeavySkillConfig
    client: Optional[OpenAICompatibleClient] = field(default=None, repr=False)

    async def __aenter__(self) -> ParallelReasoner:
        """Async context manager entry."""
        self.client = OpenAICompatibleClient(
            api_base=self.config.api_base,
            api_key=self.config.api_key,
            model=self.config.model,
            summary_model=self.config.summary_model,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
            retry_base_delay=self.config.retry_base_delay,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self.client:
            await self.client.close()

    def _build_messages(self, query: str) -> List[Dict[str, str]]:
        """Build the messages for a single reasoning request.

        Args:
            query: The user's question.

        Returns:
            List of message dicts for the API call.
        """
        system_prompt = self.config.system_prompt or get_reasoning_system_prompt(
            self.config.language, self.config.prompt_type
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]

    async def reason(self, query: str, k: Optional[int] = None) -> ReasoningResult:
        """Execute parallel reasoning with K independent trajectories.

        Args:
            query: The problem/question to reason about.
            k: 轨迹数覆盖（P54-增强-路径3：auto_k 时由 pipeline 传入，None 用 config.reason_k）。

        Returns:
            ReasoningResult with all trajectories and metadata.
        """
        if not self.client:
            raise RuntimeError("ParallelReasoner not initialized. Use async with.")

        k = k or self.config.reason_k
        logger.info(f"Starting parallel reasoning with K={k} trajectories")
        start_time = time.monotonic()

        # Build K identical message lists (each trajectory is independent)
        messages_list = [self._build_messages(query) for _ in range(k)]

        # Launch all requests in parallel
        responses = await self.client.chat_completions_parallel(
            messages_list=messages_list,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            concurrency_limit=k,
        )

        total_latency = time.monotonic() - start_time

        # Process results
        trajectories: List[str] = []
        answers: List[Optional[str]] = []
        total_tokens = 0
        successful = 0
        failed = 0

        for i, response in enumerate(responses):
            if response.finish_reason == "error":
                logger.warning(f"Trajectory {i} failed: {response.content[:100]}")
                failed += 1
                trajectories.append(response.content)
                answers.append(None)
            else:
                trajectories.append(response.content)

                answer = extract_answer(response.content)
                # P54：content 为空回退思维链的轨迹没有可靠"最终答案"，不参与共识投票
                if response.content_fallback:
                    answer = None
                answers.append(answer)
                total_tokens += response.total_tokens
                # P54-R5：截断轨迹不计入 successful（"完整成功"语义），
                # 避免 summary 出现 "8/8 successful" 与 ⚠️ 截断告警并存的误导
                if not response.truncated:
                    successful += 1

                if response.truncated:
                    logger.warning(
                        f"Trajectory {i} TRUNCATED (finish_reason=length, "
                        f"{len(response.content)} chars) — 已从审议/共识中剔除"
                    )

                if self.config.verbose:
                    logger.debug(
                        f"Trajectory {i}: answer={answer}, "
                        f"tokens={response.total_tokens}, "
                        f"latency={response.latency_seconds:.2f}s, "
                        f"truncated={response.truncated}, "
                        f"finish_reason={response.finish_reason}"
                    )

        truncated_count = sum(1 for r in responses if r.truncated)
        content_fallback_count = sum(1 for r in responses if r.content_fallback)

        logger.info(
            f"Parallel reasoning complete: {successful}/{k} successful, "
            f"{failed} failed, {truncated_count} truncated(length), "
            f"{content_fallback_count} content_fallback(思维链), "
            f"{total_tokens} total tokens, "
            f"{total_latency:.2f}s total latency"
        )

        return ReasoningResult(
            trajectories=trajectories,
            answers=answers,
            responses=responses,
            total_tokens=total_tokens,
            total_latency=total_latency,
            successful_count=successful,
            failed_count=failed,
            truncated_count=truncated_count,
            content_fallback_count=content_fallback_count,
        )
