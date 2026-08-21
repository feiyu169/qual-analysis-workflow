"""
review_chunker.py — 长文分批送审工具（P0-② 消除输入超限中断）

规则（docs/qual-review-char-limit.md）：
1. 优先按 "# 第N章" 切分（语义完整）
2. 单章仍 > max_chars → 按 "## 小节" 再切
3. 仍 > max_chars → 按句子边界切（不切断数字/表格）

Gate8 红队、review_report_text、fix_report 统一复用。
"""

import logging
import re

logger = logging.getLogger(__name__)


def split_report(
    report: str,
    max_chars: int = 12000,
    by: str = "chapter",
) -> list[tuple[int, str]]:
    """把报告分成可送审的片段列表

    Args:
        report: 完整报告文本
        max_chars: 每片最大字符数
        by: "chapter"（按章）| "section"（按小节）

    Returns:
        [(序号, 片段内容), ...]（序号用于聚合/断点续审）
    """
    if not report:
        return []

    # 1. 按 "# 第N章" 切分（语义完整边界）
    parts = re.split(r"(?m)^#\s*第(\d+)章\s*", report)
    # parts: [pre, num, body, num, body, ...]
    chunks: list[tuple[int, str]] = []
    if len(parts) > 1:
        i = 1
        while i + 1 < len(parts):
            num = int(parts[i])
            body = parts[i + 1]
            chunks.append((num, body))
            i += 2
    else:
        chunks = [(0, report)]

    # 2. 单片段超限 → 按小节再切
    result: list[tuple[int, str]] = []
    for num, body in chunks:
        if len(body) <= max_chars:
            result.append((num, body))
            continue
        # 按 "## " 小节切分
        sub_parts = re.split(r"(?m)(?=^##\s)", body)
        cur_num = num
        cur_text = ""
        for sp in sub_parts:
            if len(cur_text) + len(sp) > max_chars and cur_text:
                result.append((cur_num, cur_text))
                cur_num = num + 1000  # 子片序号偏移，避免与章号冲突
                cur_text = sp
            else:
                cur_text += sp
        if cur_text:
            result.append((cur_num, cur_text))

    # 3. 仍有超限（如单个小节 > max_chars）→ 按句子边界切
    final: list[tuple[int, str]] = []
    for num, body in result:
        if len(body) <= max_chars:
            final.append((num, body))
            continue
        # 按句子边界（。！？\n）切，尽量不切断数字
        sentences = re.split(r"(?<=[。！？\n])", body)
        buf = ""
        buf_num = num
        for sent in sentences:
            if len(buf) + len(sent) > max_chars and buf:
                final.append((buf_num, buf))
                buf_num = num + 2000
                buf = sent
            else:
                buf += sent
        if buf:
            final.append((buf_num, buf))
        logger.warning(f"片段 {num} 超 {max_chars} 字符，已按句子边界切分")

    logger.info(f"review_chunker: {len(chunks)} 章 → {len(final)} 片段 (max_chars={max_chars})")
    return final


def merge_batch_issues(batch_results: dict[int, dict]) -> dict:
    """聚合多批审查结果（P1：单批失败不丢整份）

    Args:
        batch_results: {片段号: {"fatal": [...], "important": [...], "suggestion": [...], "error": str?}}

    Returns:
        聚合结果 + 未审片段标注
    """
    aggregated = {
        "fatal": [],
        "important": [],
        "suggestion": [],
        "unreviewed": [],   # 未完成审查的片段号
        "errors": [],
    }
    for seg_id, r in batch_results.items():
        if r.get("error"):
            aggregated["unreviewed"].append(seg_id)
            aggregated["errors"].append(f"片段{seg_id}: {r['error']}")
            continue
        aggregated["fatal"].extend(r.get("fatal", []))
        aggregated["important"].extend(r.get("important", []))
        aggregated["suggestion"].extend(r.get("suggestion", []))
    return aggregated
