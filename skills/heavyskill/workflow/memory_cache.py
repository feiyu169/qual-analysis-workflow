"""
HeavySkill Memory Cache

Stores trajectories and deliberation history. Supports multiple selection
strategies for choosing which trajectories to include in deliberation.
"""

from __future__ import annotations

import logging
import random as rng
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from configuration import DeliberationRecord, SelectionStrategy
from .utils import (
    extract_answer,
    extract_all_answers,
    filter_trajectories,
    get_answer_frequencies,
    select_top_k_trajectories,
)

logger = logging.getLogger(__name__)


@dataclass
class Trajectory:
    """A single reasoning trajectory."""

    index: int
    content: str
    answer: Optional[str] = None
    tokens: int = 0
    latency: float = 0.0
    quality_score: float = 1.0
    is_valid: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "index": self.index,
            "content": self.content,
            "answer": self.answer,
            "tokens": self.tokens,
            "latency": self.latency,
            "quality_score": self.quality_score,
            "is_valid": self.is_valid,
        }


@dataclass
class MemoryCache:
    """Cache for trajectories and deliberation history.

    Stores all reasoning trajectories from Stage 1 and deliberation
    results from Stage 2. Provides selection strategies for choosing
    which trajectories to include in deliberation.

    Selection Strategies:
        random: Randomly sample k trajectories.
        max_answer_frequency: Select trajectories whose answers appear
            most frequently (consensus-based).
        max_diversity: Round-robin selection across different answers
            to maximize diversity of perspectives.
    """

    query: str = ""
    trajectories: List[Trajectory] = field(default_factory=list)
    deliberation_history: List[DeliberationRecord] = field(default_factory=list)

    def add_trajectories(self, contents: List[str], latencies: Optional[List[float]] = None) -> None:
        """Add reasoning trajectories to the cache.

        Args:
            contents: List of trajectory text contents.
            latencies: Optional list of response latencies.
        """
        for i, content in enumerate(contents):
            answer = extract_answer(content)
            trajectory = Trajectory(
                index=len(self.trajectories),
                content=content,
                answer=answer,
                tokens=len(content) // 4,  # rough estimate
                latency=latencies[i] if latencies and i < len(latencies) else 0.0,
            )
            self.trajectories.append(trajectory)

        logger.info(
            f"Added {len(contents)} trajectories to cache "
            f"(total: {len(self.trajectories)})"
        )

    def add_deliberation(self, record: DeliberationRecord) -> None:
        """Add a deliberation record to history.

        Args:
            record: The deliberation record to add.
        """
        self.deliberation_history.append(record)
        logger.info(
            f"Added deliberation record (iteration {record.iteration}), "
            f"answer: {record.extracted_answer}"
        )

    def get_valid_trajectories(self) -> List[Trajectory]:
        """Get all valid (non-error) trajectories.

        Returns:
            List of valid Trajectory objects.
        """
        return [t for t in self.trajectories if t.is_valid and not t.content.startswith("[ERROR:")]

    def get_trajectory_contents(self, indices: Optional[List[int]] = None) -> List[str]:
        """Get trajectory contents by indices.

        Args:
            indices: Specific indices to retrieve, or None for all valid.

        Returns:
            List of trajectory content strings.
        """
        if indices is None:
            return [t.content for t in self.get_valid_trajectories()]
        return [
            self.trajectories[i].content
            for i in indices
            if i < len(self.trajectories) and self.trajectories[i].is_valid
        ]

    def get_all_answers(self) -> List[Optional[str]]:
        """Get extracted answers from all valid trajectories.

        Returns:
            List of answers (None for trajectories without extractable answers).
        """
        return [t.answer for t in self.get_valid_trajectories()]

    def select_trajectories(
        self,
        k: int = 4,
        strategy: Optional[SelectionStrategy] = None,
    ) -> List[int]:
        """Select trajectories using the specified strategy.

        Args:
            k: Number of trajectories to select.
            strategy: Selection strategy override.

        Returns:
            List of selected trajectory indices.
        """
        if strategy is None:
            strategy = SelectionStrategy.MAX_ANSWER_FREQUENCY

        valid = self.get_valid_trajectories()
        if not valid:
            logger.warning("No valid trajectories to select from")
            return []

        if strategy == SelectionStrategy.RANDOM:
            return self._select_random(valid, k)
        elif strategy == SelectionStrategy.MAX_ANSWER_FREQUENCY:
            return self._select_max_answer_frequency(valid, k)
        elif strategy == SelectionStrategy.MAX_DIVERSITY:
            return self._select_max_diversity(valid, k)
        else:
            logger.warning(f"Unknown strategy {strategy}, using max_answer_frequency")
            return self._select_max_answer_frequency(valid, k)

    def _select_random(self, valid: List[Trajectory], k: int) -> List[int]:
        """Randomly sample k trajectories."""
        selected = rng.sample(valid, min(k, len(valid)))
        return [t.index for t in selected]

    def _select_max_answer_frequency(self, valid: List[Trajectory], k: int) -> List[int]:
        """Select trajectories with the most frequently occurring answers."""
        answers = [t.answer for t in valid]
        answer_freq = get_answer_frequencies(answers)

        if not answer_freq:
            # No valid answers, return first k indices
            return [t.index for t in valid[:k]]

        # Group trajectories by answer
        answer_to_indices: Dict[Optional[str], List[int]] = {}
        for t in valid:
            answer_to_indices.setdefault(t.answer, []).append(t.index)

        # Sort answers by frequency (descending)
        sorted_answers = sorted(answer_freq.items(), key=lambda x: x[1], reverse=True)

        selected: List[int] = []
        for answer, freq in sorted_answers:
            indices = answer_to_indices.get(answer, [])
            for idx in indices:
                if idx not in selected:
                    selected.append(idx)
                    if len(selected) >= k:
                        return selected

        # Fill remaining with any valid trajectories
        for t in valid:
            if t.index not in selected:
                selected.append(t.index)
                if len(selected) >= k:
                    break

        return selected

    def _select_max_diversity(self, valid: List[Trajectory], k: int) -> List[int]:
        """Round-robin selection across different answers for maximum diversity."""
        # Group by answer
        answer_to_indices: Dict[Optional[str], List[int]] = {}
        for t in valid:
            answer_to_indices.setdefault(t.answer, []).append(t.index)

        # Sort groups by frequency (ascending - prioritize diverse answers)
        sorted_groups = sorted(
            answer_to_indices.items(),
            key=lambda x: len(x[1]),
            reverse=False,
        )

        selected: List[int] = []
        round_robin_idx = 0

        while len(selected) < k:
            added_any = False
            for answer, indices in sorted_groups:
                if round_robin_idx < len(indices) and len(selected) < k:
                    idx = indices[round_robin_idx]
                    if idx not in selected:
                        selected.append(idx)
                        added_any = True

            round_robin_idx += 1
            if not added_any:
                break

        return selected

    def get_answer_summary(self) -> Dict[str, int]:
        """Get a summary of answer frequencies.

        Returns:
            Dictionary mapping answer -> count.
        """
        answers = self.get_all_answers()
        freq = get_answer_frequencies(answers)
        return dict(freq.most_common())

    def get_consensus_answer(self) -> Optional[str]:
        """Get the most common answer across all trajectories.

        Returns:
            The most frequent answer, or None if no answers found.
        """
        answers = self.get_all_answers()
        freq = get_answer_frequencies(answers)
        if not freq:
            return None
        return freq.most_common(1)[0][0]

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics.
        """
        valid = self.get_valid_trajectories()
        answers = self.get_all_answers()
        answer_freq = get_answer_frequencies(answers)

        return {
            "total_trajectories": len(self.trajectories),
            "valid_trajectories": len(valid),
            "deliberation_rounds": len(self.deliberation_history),
            "unique_answers": len(answer_freq),
            "consensus_answer": self.get_consensus_answer(),
            "answer_frequencies": dict(answer_freq.most_common()),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the entire cache to a dictionary."""
        return {
            "query": self.query,
            "trajectories": [t.to_dict() for t in self.trajectories],
            "deliberation_history": [d.to_dict() for d in self.deliberation_history],
            "stats": self.get_stats(),
        }
