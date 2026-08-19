"""
quality — 质量保障模块包。

组件代次：COMPONENT_GEN = "v3"（质量组件层整体换代用；独立于包版本 finance.__version__ 与
         架构代次 qual_v8.ARCH_GEN——三刻度分离，见 docs/qual-version-architecture.md）

导出 workflow.py 依赖的顶层符号：
- structural_check / semantic_audit / repair_chapter（审计修复循环）
- CheckpointManager（断点持久化）
"""
# 组件代次（三刻度之一）
COMPONENT_GEN = "v3"

from .structural_check import structural_check
from .auditor import semantic_audit
from .repairer import repair_chapter
from .checkpoint import CheckpointManager

__all__ = [
    "COMPONENT_GEN",
    "structural_check",
    "semantic_audit",
    "repair_chapter",
    "CheckpointManager",
]
