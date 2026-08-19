"""
HeavySkill: A Two-Stage Pipeline for Enhanced LLM Reasoning

Based on arXiv:2605.02396 - HeavySkill implements parallel reasoning with
sequential deliberation to improve LLM problem-solving capabilities.

Stage 1 (Parallel Reasoning): Spawn K independent reasoning trajectories
Stage 2 (Sequential Deliberation): Cross-validate and synthesize final answer
"""

from .configuration import HeavySkillConfig

__version__ = "1.0.0"
__all__ = ["HeavySkillConfig"]


def get_pipeline():
    """Lazy import to avoid circular imports."""
    from .workflow.pipeline import HeavySkillPipeline, HeavySkillResult
    return HeavySkillPipeline, HeavySkillResult
