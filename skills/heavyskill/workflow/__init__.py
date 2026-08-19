"""Workflow module for HeavySkill pipeline stages."""

# Lazy imports to avoid circular dependencies
__all__ = [
    "ParallelReasoner",
    "SequentialDeliberator",
    "MemoryCache",
    "HeavySkillPipeline",
    "HeavySkillResult",
]


def __getattr__(name: str):
    if name == "ParallelReasoner":
        from .parallel_reasoning import ParallelReasoner
        return ParallelReasoner
    elif name == "SequentialDeliberator":
        from .sequential_deliberation import SequentialDeliberator
        return SequentialDeliberator
    elif name == "MemoryCache":
        from .memory_cache import MemoryCache
        return MemoryCache
    elif name in ("HeavySkillPipeline", "HeavySkillResult"):
        from .pipeline import HeavySkillPipeline, HeavySkillResult
        if name == "HeavySkillPipeline":
            return HeavySkillPipeline
        return HeavySkillResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
