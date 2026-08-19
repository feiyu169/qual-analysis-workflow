"""
HeavySkill Stage 2: Sequential Deliberation

Takes reasoning trajectories from Stage 1, builds a deliberation prompt,
and generates a synthesized final answer. Supports three selection strategies
for choosing which trajectories to deliberate on.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.openai_compatible import LLMResponse, OpenAICompatibleClient
from configuration import DeliberationRecord, HeavySkillConfig, Language, PromptType, SelectionStrategy, get_deliberation_prompt
from .memory_cache import MemoryCache
from .utils import extract_answer, estimate_tokens

logger = logging.getLogger(__name__)


@dataclass
class DeliberationResult:
    """Result from the sequential deliberation stage."""

    final_answer: Optional[str]
    deliberation_response: str
    selected_indices: List[int]
    iteration: int
    tokens: int = 0
    latency: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "final_answer": self.final_answer,
            "deliberation_response": self.deliberation_response,
            "selected_indices": self.selected_indices,
            "iteration": self.iteration,
            "tokens": self.tokens,
            "latency": self.latency,
        }


@dataclass
class SequentialDeliberator:
    """Stage 2: Sequential Deliberation.

    Analyzes multiple reasoning trajectories, identifies errors,
    cross-validates answers, and synthesizes a final answer.

    Supports three selection strategies:
        - random: Randomly sample k trajectories
        - max_answer_frequency: Select trajectories with most common answers
        - max_diversity: Round-robin across different answers for diversity
    """

    config: HeavySkillConfig
    client: Optional[OpenAICompatibleClient] = field(default=None, repr=False)

    async def __aenter__(self) -> SequentialDeliberator:
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

    def build_deliberation_prompt(
        self,
        query: str,
        trajectories: List[str],
        iteration: int = 0,
        previous_deliberation: Optional[str] = None,
    ) -> str:
        """Build the deliberation prompt from trajectories.

        Args:
            query: Original user question.
            trajectories: Selected trajectory texts.
            iteration: Current iteration number.
            previous_deliberation: Previous deliberation result for iterative refinement.

        Returns:
            Formatted deliberation prompt string.
        """
        # Get the base deliberation prompt template
        prompt_template = get_deliberation_prompt(
            self.config.language, self.config.prompt_type
        )

        # Format trajectories with labels
        formatted_trajectories = ""
        for i, traj in enumerate(trajectories, 1):
            formatted_trajectories += f"\n--- Attempt {i} ---\n{traj}\n"

        # Add previous deliberation if iterating
        if previous_deliberation and iteration > 0:
            formatted_trajectories += (
                f"\n--- Previous Deliberation (Iteration {iteration}) ---\n"
                f"{previous_deliberation}\n"
            )

        # Fill in the template
        prompt = prompt_template.format(
            k=len(trajectories),
            query=query,
            trajectories=formatted_trajectories,
        )

        # Add iteration context
        if iteration > 0:
            prompt = (
                f"[This is iteration {iteration + 1} of iterative refinement. "
                f"You have access to the previous deliberation result below.]\n\n"
                f"{prompt}"
            )

        return prompt

    async def deliberate(
        self,
        query: str,
        cache: MemoryCache,
        iteration: int = 0,
        previous_deliberation: Optional[str] = None,
    ) -> DeliberationResult:
        """Execute deliberation on cached trajectories.

        Selects trajectories using the configured strategy, builds
        a deliberation prompt, and generates a synthesized answer.

        Args:
            query: Original user question.
            cache: MemoryCache with stored trajectories.
            iteration: Current iteration number.
            previous_deliberation: Previous deliberation result for iteration.

        Returns:
            DeliberationResult with the synthesized answer.
        """
        if not self.client:
            raise RuntimeError("SequentialDeliberator not initialized. Use async with.")

        start_time = time.monotonic()

        # Select trajectories using configured strategy
        selected_indices = cache.select_trajectories(
            k=self.config.summary_k,
            strategy=self.config.selection_strategy,
        )

        if not selected_indices:
            logger.warning("No trajectories available for deliberation")
            return DeliberationResult(
                final_answer=None,
                deliberation_response="No valid trajectories available for deliberation.",
                selected_indices=[],
                iteration=iteration,
            )

        selected_trajectories = cache.get_trajectory_contents(selected_indices)

        logger.info(
            f"Deliberation iteration {iteration + 1}: "
            f"selected {len(selected_trajectories)} trajectories "
            f"(strategy: {self.config.selection_strategy.value})"
        )

        if self.config.verbose:
            for i, idx in enumerate(selected_indices):
                traj = selected_trajectories[i]
                preview = traj[:100].replace("\n", " ")
                logger.debug(f"  Selected trajectory {idx}: {preview}...")

        # Build deliberation prompt
        prompt = self.build_deliberation_prompt(
            query, selected_trajectories, iteration, previous_deliberation
        )

        # Get deliberation system prompt
        system_prompt = self.config.deliberation_system_prompt
        if not system_prompt:
            if self.config.language == Language.CN:
                system_prompt = "你是一个高级推理分析专家。请仔细分析多个推理尝试，找出错误，验证答案，并给出最终综合结论。"
            else:
                system_prompt = (
                    "You are an expert reasoning analyst. Carefully analyze "
                    "multiple reasoning attempts, identify errors, validate "
                    "answers, and provide a synthesized final conclusion."
                )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        # Call the deliberation model
        response = await self.client.deliberation_call(
            messages=messages,
            temperature=self.config.summary_temperature,
            max_tokens=self.config.max_tokens,
        )

        latency = time.monotonic() - start_time
        deliberation_text = response.content
        final_answer = extract_answer(deliberation_text)

        # If no answer extracted from deliberation, check consensus
        if final_answer is None:
            final_answer = cache.get_consensus_answer()
            if final_answer:
                logger.info("Using consensus answer as fallback")

        # Record the deliberation
        record = DeliberationRecord(
            iteration=iteration,
            selected_indices=selected_indices,
            prompt=prompt[:500] + "..." if len(prompt) > 500 else prompt,
            response=deliberation_text,
            extracted_answer=final_answer,
            tokens=response.total_tokens,
        )
        cache.add_deliberation(record)

        logger.info(
            f"Deliberation complete: answer='{final_answer}', "
            f"tokens={response.total_tokens}, latency={latency:.2f}s"
        )

        return DeliberationResult(
            final_answer=final_answer,
            deliberation_response=deliberation_text,
            selected_indices=selected_indices,
            iteration=iteration,
            tokens=response.total_tokens,
            latency=latency,
        )
