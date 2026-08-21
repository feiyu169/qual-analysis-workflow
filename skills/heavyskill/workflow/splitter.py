"""P54-增强-路径4：审查包分批（split_pack）。

消除 build_pack 的 20000 字符截断——被审内容不完整直接限制结论质量上限。
按章节边界（markdown 标题 / def|class / 空行）切分，块间重叠保上下文。
"""

from __future__ import annotations

import re
from typing import List

# 章节边界：markdown 标题、函数/类定义、分隔线
_BOUNDARY_PATTERNS = [
    re.compile(r"^#{1,6}\s+\S", re.MULTILINE),
    re.compile(r"^(?:async\s+)?def\s+\w+|^class\s+\w+", re.MULTILINE),
    re.compile(r"^---+\s*$", re.MULTILINE),
]


def _find_boundaries(content: str, min_gap: int = 40) -> List[int]:
    """找所有章节边界行号（去重、去太近的）。"""
    positions = set()
    for pat in _BOUNDARY_PATTERNS:
        for m in pat.finditer(content):
            positions.add(m.start())
    # 按位置排序并合并过近的边界
    sorted_pos = sorted(positions)
    merged: List[int] = []
    for p in sorted_pos:
        if not merged or p - merged[-1] >= min_gap:
            merged.append(p)
    return merged


def split_pack(
    content: str,
    max_chars: int = 18000,
    overlap: int = 500,
    max_chunks: int = 5,
) -> List[str]:
    """按章节边界把长内容切分为多个审查块。

    Args:
        content: 被审内容全文。
        max_chars: 单块上限（字符）。
        overlap: 块间重叠字符数（保上下文连续）。
        max_chunks: 最大块数（超出告警由调用方处理，这里硬上限截断末尾）。

    Returns:
        块文本列表；单块内容 ≤ max_chars + overlap（尾部重叠段）。
    """
    if len(content) <= max_chars:
        return [content]

    boundaries = _find_boundaries(content)
    chunks: List[str] = []
    start = 0
    text_len = len(content)

    while start < text_len and len(chunks) < max_chunks - 1:
        limit = start + max_chars
        if limit >= text_len:
            chunks.append(content[start:])
            break
        # 在 limit 之前找最近边界（保证 ≥ 60% 进度，防边界太近导致死循环）
        candidates = [b for b in boundaries if start < b <= limit]
        cut = (
            candidates[-1]
            if candidates and (limit - candidates[-1]) < max_chars * 0.6
            else limit
        )
        if cut <= start:
            cut = limit
        chunk = content[start:cut]
        # 尾部附加下一块前 overlap 字符（上下文重叠）
        overlap_text = content[cut : cut + overlap]
        if overlap_text:
            chunk += "\n[--- 上下文衔接（下块开头）---]\n" + overlap_text
        chunks.append(chunk)
        start = cut

    if start < text_len:
        # max_chunks 截断：末尾块标记
        last = content[start:]
        chunks.append(last[:max_chars] + "\n[...超出 max_chunks，剩余内容已截断...]")
    return chunks


def chunk_stats(chunks: List[str]) -> List[int]:
    """各块长度（字符），供日志/测试。"""
    return [len(c) for c in chunks]
