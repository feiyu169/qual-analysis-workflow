"""
报告组装模块（v9 Phase 4：从 workflow.py 拆出）。

负责报告章节组装、质量标注、目录生成。
属于 Service 层的"报告组装"职责。

设计参照：dayu services/internal/write_pipeline/report_assembler.py
"""
from __future__ import annotations

import re

# 章节写入顺序（1-9章，不含第0章概览和第10章决策）
CHAPTER_WRITE_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 9]


def assemble_report(
    overview: str,
    chapters: dict[int, str],
    decision: str,
    company_name: str,
    ticker: str,
    market: str = "",
    data_quality: str = "",
    filing_source: str = "",
    wind_source: str = "",
    chapter_defs: dict[int, dict] | None = None,
) -> str:
    """组装完整分析报告（从 workflow.py _assemble_report 提取）。

    Args:
        overview: 第0章内容
        chapters: 第1-9章内容
        decision: 第10章内容
        company_name: 公司名
        ticker: 股票代码
        market: 市场
        data_quality: 数据质量
        filing_source: 财报来源
        wind_source: Wind 来源
        chapter_defs: 章节定义字典（可选，缺省用内置）

    Returns:
        完整 Markdown 报告
    """
    from ..workflow import CHAPTERS
    ch_defs = chapter_defs or CHAPTERS

    parts: list[str] = []

    # 报告头部
    parts.append(f"# {company_name} ({ticker}) 买方定性分析报告\n")
    if market or data_quality:
        meta_parts = []
        if market:
            meta_parts.append(f"**市场**: {market.upper()}")
        if data_quality:
            meta_parts.append(f"**数据质量**: {data_quality}")
        if filing_source:
            meta_parts.append(f"**财报来源**: {filing_source}")
        if wind_source:
            meta_parts.append(f"**Wind 来源**: {wind_source}")
        parts.append(" | ".join(meta_parts) + "\n")

    # 第0章: 概览
    parts.append("---\n")
    parts.append(overview)

    # 目录
    parts.append("\n---\n")
    parts.append("## 目录\n")
    for num in [0, *CHAPTER_WRITE_ORDER, 10]:
        ch_def = ch_defs.get(num, {})
        title = ch_def.get("title", f"第{num}章")
        ch_id = ch_def.get("id", f"ch{num}")
        parts.append(f"- [第{num}章: {title}](#{ch_id})")
    parts.append("")

    # 第1-9章
    for num in CHAPTER_WRITE_ORDER:
        parts.append("\n---\n")
        ch_def = ch_defs.get(num, {})
        title = ch_def.get("title", f"第{num}章")
        content = chapters.get(num, f"<!-- 第{num}章内容缺失 -->")
        # 去掉内容自带的首行标题，统一使用规范标题
        stripped = content.lstrip("\n")
        if stripped.startswith("# "):
            stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        # H1 → H2（防章节重号/模板泄漏）
        stripped = re.sub(r"(?m)^# ", "## ", stripped)
        parts.append(f"# 第{num}章 {title}\n")
        parts.append(stripped)

    # 第10章: 决策
    parts.append("\n---\n")
    ch10_def = ch_defs.get(10, {})
    title10 = ch10_def.get("title", "投资决策")
    decision_stripped = decision.lstrip("\n")
    if decision_stripped.startswith("# "):
        decision_stripped = decision_stripped.split("\n", 1)[1] if "\n" in decision_stripped else ""
    parts.append(f"# 第10章 {title10}\n")
    parts.append(decision_stripped)

    return "\n".join(parts)


def annotate_quality(
    report: str,
    qual_mode: str = "",
    failed_gates: list[str] | None = None,
    quality_degraded: bool = False,  # noqa: FBT001,FBT002
    degradation_reasons: list[str] | None = None,
) -> str:
    """在报告头部注入质量受限声明。

    Args:
        report: 原始报告
        qual_mode: 运行模式
        failed_gates: 失败的 Gate 列表
        quality_degraded: 是否降级
        degradation_reasons: 降级原因

    Returns:
        注入质量声明后的报告
    """
    markers = []
    if quality_degraded:
        reasons = degradation_reasons or []
        reasons_str = "; ".join(reasons[:5]) if reasons else "未知"
        markers.append(f"> ⚠️ **质量受限声明**: 本次报告生成过程中存在降级（{reasons_str}），"
                       f"数据和结论仅供参考，投资决策需结合人工判断。")
    if failed_gates:
        markers.append(f"> ⚠️ **未通过 Gate**: {', '.join(failed_gates[:5])}")
    if qual_mode in ("shadow", "soft"):
        markers.append(f"> ℹ️ 运行模式: {qual_mode}（记录模式，不阻断）")

    if not markers:
        return report

    header = "\n".join(markers) + "\n\n"
    # 插入到报告头部（第一个 --- 之前）
    first_sep = report.find("\n---\n")
    if first_sep > 0:
        return report[:first_sep] + "\n" + header + report[first_sep:]
    return header + report
