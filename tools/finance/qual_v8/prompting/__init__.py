"""
Qual v9 Prompting 模块入口。

提供 prompt 构建、条件渲染、上下文插槽管理。
参照 dayu-agent prompting/ 层（条件渲染 + context_slots）。
"""
from .chapter_prompts import (
    ContextSlots,
    build_chapter_prompt,
    render_conditional,
    render_variables,
)

__all__ = [
    "ContextSlots",
    "build_chapter_prompt",
    "render_conditional",
    "render_variables",
]
