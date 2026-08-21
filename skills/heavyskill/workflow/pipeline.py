"""
HeavySkill Pipeline

Orchestrates the complete two-stage pipeline:
  Stage 1: Parallel Reasoning → Generate K independent trajectories
  Cache: Store and select trajectories
  Stage 2: Sequential Deliberation → Synthesize final answer
  Optional: Iterative refinement (feed deliberation back as trajectory)

Returns a HeavySkillResult dataclass with the complete result.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configuration import HeavySkillConfig, SelectionStrategy
from .memory_cache import MemoryCache
from .parallel_reasoning import ParallelReasoner, ReasoningResult
from .sequential_deliberation import DeliberationResult, SequentialDeliberator
from .utils import estimate_total_tokens, filter_trajectories

logger = logging.getLogger(__name__)


@dataclass
class HeavySkillResult:
    """Complete result from the HeavySkill pipeline.

    Attributes:
        query: The original question.
        final_answer: The synthesized final answer.
        consensus_answer: Most frequent answer across trajectories.
        reasoning_result: Result from Stage 1 (parallel reasoning).
        deliberation_results: Results from Stage 2 (deliberation iterations).
        cache_stats: Statistics from the memory cache.
        total_tokens: Total tokens used across all stages.
        total_latency: Total wall-clock time in seconds.
        iterations_completed: Number of deliberation iterations completed.
    """

    query: str
    final_answer: Optional[str]
    consensus_answer: Optional[str]
    reasoning_result: Optional[ReasoningResult] = None
    deliberation_results: List[DeliberationResult] = field(default_factory=list)
    cache_stats: Dict[str, Any] = field(default_factory=dict)
    total_tokens: int = 0
    total_latency: float = 0.0
    iterations_completed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON output."""
        reasoning_dict = (
            self.reasoning_result.to_dict() if self.reasoning_result else None
        )
        result = {
            "query": self.query,
            "final_answer": self.final_answer,
            "consensus_answer": self.consensus_answer,
            "total_tokens": self.total_tokens,
            "total_latency_seconds": round(self.total_latency, 2),
            "iterations_completed": self.iterations_completed,
            "cache_stats": self.cache_stats,
            # P54：截断摘要——消费端先看这里，>0 必须处理（重跑/增大预算/标记接受）
            "truncation": {
                "reasoning_truncated_count": (
                    self.reasoning_result.truncated_count
                    if self.reasoning_result
                    else 0
                ),
                "content_fallback_count": (
                    self.reasoning_result.content_fallback_count
                    if self.reasoning_result
                    else 0
                ),
                "deliberation_truncated": any(
                    d.truncated for d in self.deliberation_results
                ),
            },
        }

        if reasoning_dict:
            result["reasoning"] = reasoning_dict

        if self.deliberation_results:
            result["deliberation"] = [d.to_dict() for d in self.deliberation_results]

        return result

    def has_truncation(self) -> bool:
        """P54-R5：本次运行是否有退化（截断轨迹/思维链回退/审议截断）。

        与 to_dict()["truncation"] 摘要口径一致（含 content_fallback_count），
        供 CLI/告警判断"结果是否可放心采信"。
        """
        if self.reasoning_result and (
            self.reasoning_result.truncated_count > 0
            or self.reasoning_result.content_fallback_count > 0
        ):
            return True
        return any(d.truncated for d in self.deliberation_results)

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def summary(self) -> str:
        """Generate a human-readable summary."""
        lines = [
            "=" * 60,
            "HeavySkill Pipeline Result",
            "=" * 60,
            f"Query: {self.query[:200]}{'...' if len(self.query) > 200 else ''}",
            f"",
            f"Final Answer: {self.final_answer}",
            f"Consensus Answer: {self.consensus_answer}",
            f"",
            f"Iterations: {self.iterations_completed}",
            f"Total Tokens: {self.total_tokens:,}",
            f"Total Latency: {self.total_latency:.2f}s",
        ]

        if self.reasoning_result:
            lines.extend(
                [
                    f"",
                    f"Stage 1 - Parallel Reasoning:",
                    f"  Trajectories: {self.reasoning_result.successful_count}/{len(self.reasoning_result.trajectories)} successful",
                    f"  Tokens: {self.reasoning_result.total_tokens:,}",
                    f"  Latency: {self.reasoning_result.total_latency:.2f}s",
                ]
            )

        if self.cache_stats:
            answer_freq = self.cache_stats.get("answer_frequencies", {})
            if answer_freq:
                lines.append(f"")
                lines.append(f"Answer Distribution:")
                for answer, count in list(answer_freq.items())[:5]:
                    lines.append(f"  '{answer}': {count} votes")

        # P54-R1/R5：退化告警——summary 只展示短字段，必须显式提示消费端去读 JSON 详情
        if self.has_truncation():
            truncated_reasoning = (
                self.reasoning_result.truncated_count if self.reasoning_result else 0
            )
            fallback_count = (
                self.reasoning_result.content_fallback_count
                if self.reasoning_result
                else 0
            )
            delib_truncated = any(d.truncated for d in self.deliberation_results)
            lines.append("")
            lines.append("⚠️  WARNING: 本次运行存在截断或退化！")
            lines.append(
                f"   推理轨迹截断: {truncated_reasoning} 条（已从审议/共识剔除）"
            )
            lines.append(f"   思维链回退: {fallback_count} 条（不参与共识投票）")
            lines.append(f"   审议结论截断: {'是' if delib_truncated else '否'}")
            lines.append(
                "   处理：增大 --max-tokens / --summary-max-tokens 后重跑，"
                "或使用 --accept-partial 显式接受部分结果"
            )

        lines.append("=" * 60)
        return "\n".join(lines)


@dataclass
class HeavySkillPipeline:
    """Complete HeavySkill pipeline orchestrator.

    Executes the two-stage process:
    1. Parallel Reasoning: Generate K independent reasoning trajectories
    2. Sequential Deliberation: Analyze and synthesize final answer

    Supports iterative refinement where deliberation results are fed
    back as additional context for subsequent deliberation rounds.

    Usage:
        config = HeavySkillConfig(query="What is 2+2?")
        pipeline = HeavySkillPipeline(config)
        result = await pipeline.run()
        print(result.summary())
    """

    config: HeavySkillConfig

    async def run(self, query: Optional[str] = None) -> HeavySkillResult:
        """Execute the complete HeavySkill pipeline.

        Args:
            query: The question to reason about. Uses config query if None.

        Returns:
            HeavySkillResult with the complete pipeline output.
        """
        if query is None:
            raise ValueError("Query must be provided")

        pipeline_start = time.monotonic()
        total_tokens = 0

        logger.info(f"Starting HeavySkill pipeline")
        logger.info(f"  Query: {query[:100]}{'...' if len(query) > 100 else ''}")
        logger.info(f"  Reason K: {self.config.reason_k}")
        logger.info(f"  Summary K: {self.config.summary_k}")
        logger.info(f"  Iterations: {self.config.max_iterations}")
        logger.info(f"  Strategy: {self.config.selection_strategy.value}")

        # Initialize memory cache
        cache = MemoryCache(query=query)

        # Stage 1: Parallel Reasoning
        logger.info("=" * 40)
        logger.info("STAGE 1: Parallel Reasoning")
        logger.info("=" * 40)

        reasoning_result: Optional[ReasoningResult] = None
        async with ParallelReasoner(self.config) as reasoner:
            reasoning_result = await reasoner.reason(query)

        # Store trajectories in cache
        # P54：透传逐轨迹截断/思维链回退标记——截断轨迹不参与审议与共识
        cache.add_trajectories(
            reasoning_result.trajectories,
            latencies=[r.latency_seconds for r in reasoning_result.responses],
            truncated=[r.truncated for r in reasoning_result.responses],
            content_fallback=[r.content_fallback for r in reasoning_result.responses],
        )
        total_tokens += reasoning_result.total_tokens

        # Filter trajectories for quality
        # P54-R5：早退判定统一用 cache 的有效集（is_valid 已排除截断轨迹），
        # 不再用未过滤的 reasoning_result.answers（旧逻辑全截断时仍判"有有效轨迹"）
        valid_trajectories, _ = filter_trajectories(
            reasoning_result.trajectories,
            reasoning_result.answers,
        )
        if not valid_trajectories or not cache.get_valid_trajectories():
            logger.warning(
                "No valid trajectories after filtering (截断/失败/质量过滤后为空)"
            )
            return HeavySkillResult(
                query=query,
                final_answer=None,
                consensus_answer=None,
                reasoning_result=reasoning_result,
                cache_stats=cache.get_stats(),
                total_tokens=total_tokens,
                total_latency=time.monotonic() - pipeline_start,
                iterations_completed=0,
            )

        # Stage 2: Sequential Deliberation (with optional iteration)
        logger.info("=" * 40)
        logger.info("STAGE 2: Sequential Deliberation")
        logger.info("=" * 40)

        deliberation_results: List[DeliberationResult] = []
        previous_deliberation: Optional[str] = None

        async with SequentialDeliberator(self.config) as deliberator:
            for iteration in range(self.config.max_iterations):
                logger.info(
                    f"Deliberation iteration {iteration + 1}/{self.config.max_iterations}"
                )

                delib_result = await deliberator.deliberate(
                    query=query,
                    cache=cache,
                    iteration=iteration,
                    previous_deliberation=previous_deliberation,
                )

                deliberation_results.append(delib_result)
                total_tokens += delib_result.tokens
                # P54-R3：截断的审议残稿不回填下一轮迭代（防污染）
                previous_deliberation = (
                    delib_result.deliberation_response
                    if not delib_result.truncated
                    else None
                )

                # If we got a confident answer, we can stop early
                if delib_result.final_answer and iteration > 0:
                    logger.info(
                        f"Got answer on iteration {iteration + 1}, stopping early"
                    )
                    break

        # Determine final answer
        final_answer = None
        if deliberation_results:
            # Use the last deliberation's answer
            final_answer = deliberation_results[-1].final_answer

        # Fallback to consensus if deliberation didn't produce an answer
        if final_answer is None:
            final_answer = cache.get_consensus_answer()
            if final_answer:
                logger.info("Using consensus answer as final fallback")

        total_latency = time.monotonic() - pipeline_start

        logger.info("=" * 40)
        logger.info("PIPELINE COMPLETE")
        logger.info(f"  Final Answer: {final_answer}")
        logger.info(f"  Total Tokens: {total_tokens:,}")
        logger.info(f"  Total Latency: {total_latency:.2f}s")
        logger.info("=" * 40)

        return HeavySkillResult(
            query=query,
            final_answer=final_answer,
            consensus_answer=cache.get_consensus_answer(),
            reasoning_result=reasoning_result,
            deliberation_results=deliberation_results,
            cache_stats=cache.get_stats(),
            total_tokens=total_tokens,
            total_latency=total_latency,
            iterations_completed=len(deliberation_results),
        )

    async def run_with_progress(
        self, query: str, progress_callback: Optional[Any] = None
    ) -> HeavySkillResult:
        """Execute pipeline with progress callbacks.

        Args:
            query: The question to reason about.
            progress_callback: Optional async callable(stage, progress, total).

        Returns:
            HeavySkillResult with the complete pipeline output.
        """
        # For now, delegates to run(). Can be extended for progress tracking.
        return await self.run(query)
