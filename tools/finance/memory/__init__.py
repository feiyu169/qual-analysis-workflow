"""
Memory Layer - 投资分析记忆集成层

Phase 5: 记忆集成
- gbrain_writer: GBrain 知识图谱集成 (Gate 5.1)
- flomo_writer: flomo 笔记集成 (Gate 5.2)
- nocturne_writer: nocturne 记忆集成 (Gate 5.3)
- memory_manager: 三层记忆管理器 (Gate 5.4)
"""

from .flomo_writer import write_to_flomo
from .gbrain_writer import write_to_gbrain
from .memory_manager import MemoryManager
from .nocturne_writer import write_to_nocturne

__all__ = [
    "MemoryManager",
    "write_to_flomo",
    "write_to_gbrain",
    "write_to_nocturne",
]
