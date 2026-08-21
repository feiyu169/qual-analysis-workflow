#!/usr/bin/env python3
"""报告完整性检查器 — V5.0"""

import re
from typing import Any

REQUIRED_SECTIONS = [
    "投资摘要", "公司概况", "行业分析", "财务分析",
    "估值分析", "风险提示", "投资建议",
]

REQUIRED_ELEMENTS = [
    {"name": "敏感性分析", "patterns": ["敏感性", "敏感性分析", "敏感性矩阵"]},
    {"name": "数据来源", "patterns": ["数据来源", "来源:", "数据来源:"]},
    {"name": "免责声明", "patterns": ["免责声明", "仅供参考", "不构成投资建议"]},
    {"name": "行业比较", "patterns": ["同行", "同业", "行业平均", "可比公司", "Peer"]},
]

FORBIDDEN_PATTERNS = [
    {"name": "跳过章节", "pattern": r"(跳过|省略|不需要).{0,10}(章节|部分)",
     "exclude_context": ["在.*中", "如果.*则"]},
    {"name": "伪造数据", "pattern": r"(虚构|编造|假造).{0,10}(数据|数字)", "exclude_context": []},
]

TABLE_SEPARATOR_PATTERN = re.compile(r'^\|[\s\-:]+\|', re.MULTILINE)


def _is_in_excluded_context(text: str, pos: int, exclude_contexts: list[str]) -> bool:
    """检查匹配位置是否在排除上下文中"""
    start = max(0, pos - 50)
    end = min(len(text), pos + 50)
    context = text[start:end]
    for exclude_pattern in exclude_contexts:
        if re.search(exclude_pattern, context):
            return True
    return False


def lint_report(report: str) -> dict[str, Any]:
    """检查报告完整性

    Args:
        report: 报告全文（Markdown 格式）

    Returns:
        包含 passed, issues, warnings, section_count 等字段的字典
    """
    issues = []
    warnings = []

    # 检查必须章节
    for section in REQUIRED_SECTIONS:
        if section not in report:
            issues.append(f"缺失章节: {section}")

    # 检查必须元素
    for element in REQUIRED_ELEMENTS:
        found = any(p in report for p in element["patterns"])
        if not found:
            issues.append(f"缺失元素: {element['name']}")

    # 禁止行为检测
    for forbidden in FORBIDDEN_PATTERNS:
        for match in re.finditer(forbidden["pattern"], report):
            if not _is_in_excluded_context(report, match.start(), forbidden.get("exclude_context", [])):
                warnings.append(f"疑似禁止行为: {forbidden['name']}")
                break

    # 来源密度检查
    source_count = len(re.findall(r'\[.*?来源.*?\]|数据来源：|来源：', report))
    if source_count < 3:
        warnings.append(f"数据来源标注较少（仅 {source_count} 处）")

    # 报告长度检查
    if len(report) < 3000:
        warnings.append(f"报告内容较短（{len(report)} 字符），可能不完整")

    # 表格检测
    if not TABLE_SEPARATOR_PATTERN.search(report):
        warnings.append("报告中未包含有效的 Markdown 表格")

    # 关键词覆盖检查
    analysis_keywords = ["竞争", "护城河", "增长", "风险", "估值"]
    missing_keywords = [kw for kw in analysis_keywords if kw not in report]
    if len(missing_keywords) > 2:
        warnings.append(f"缺少关键分析内容: {', '.join(missing_keywords)}")

    return {
        "passed": len(issues) == 0,
        "issues": issues, "warnings": warnings,
        "section_count": sum(1 for s in REQUIRED_SECTIONS if s in report),
        "total_sections": len(REQUIRED_SECTIONS),
        "source_count": source_count, "report_length": len(report),
    }
