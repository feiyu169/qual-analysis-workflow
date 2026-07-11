"""
Gate 4.1: 结构化预检 (Structural Check)

在语义审计之前执行快速的结构化检查，验证章节格式和必需组件。
无需 LLM 调用，纯规则引擎。

检查项:
- 章节是否存在
- 必需小节是否存在（结论要点/详细情况/证据与出处）
- 证据溯源是否存在
- 内容最小长度
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------
# 数据模型
# --------------------------------------------------

@dataclass
class AuditResult:
    """审计结果"""
    passed: bool                          # 是否通过
    issues: list[str] = field(default_factory=list)  # 问题列表
    score: Optional[float] = None         # 评分（可选）
    details: dict[str, Any] = field(default_factory=dict)  # 详细信息


# --------------------------------------------------
# 常量定义
# --------------------------------------------------

# 每章必需的小节标题（中文模式 + 英文模式）
_REQUIRED_SECTIONS = [
    {
        "name": "结论要点",
        "patterns": [
            r"#+\s*结论",
            r"#+\s*核心.*?观点",
            r"#+\s*投资.*?要点",
            r"#+\s*总结",
            r"#+\s*Key\s*(?:Takeaway|Point|Conclusion)",
            r"#+\s*Summary",
            r"#+\s*Conclusion",
        ],
    },
    {
        "name": "详细情况",
        "patterns": [
            r"#+\s*详细",
            r"#+\s*分析",
            r"#+\s*深入",
            r"#+\s*核心.*?分析",
            r"#+\s*详细.*?分析",
            r"#+\s*(?:Detail|Analysis|Deep\s*Dive)",
        ],
    },
    {
        "name": "证据与出处",
        "patterns": [
            r"#+\s*证据",
            r"#+\s*出处",
            r"#+\s*数据.*?来源",
            r"#+\s*参考",
            r"#+\s*(?:Evidence|Source|Reference|Data\s*Source)",
        ],
    },
]

# 证据溯源标记模式
_EVIDENCE_PATTERNS = [
    r"\[来源[:：]",
    r"\[Source[:：]",
    r"根据.*?(财报|年报|季报|公告|报告)",
    r"据.*?(Wind|SEC|巨潮|披露易)",
    r"data\s+from",
    r"source\s*:",
    r"来源[:：]",
    r"引用自",
    r"according\s+to",
    r"per\s+(?:the\s+)?(?:filing|report|10-K|10-Q|20-F)",
]

# 章节标题模式（检测章节是否真的存在内容）
_CHAPTER_HEADING_PATTERNS = [
    r"^#+\s+第?\s*\d+\s*[章回节]",
    r"^#+\s+Chapter\s+\d+",
    r"^#+\s+Section\s+\d+",
    r"^#\s+",  # 任何一级标题
]

# 最小内容长度（字符）
_MIN_CONTENT_LENGTH = 200


# --------------------------------------------------
# 主函数
# --------------------------------------------------

def structural_check(
    chapter_id: str,
    content: str,
    contract: Optional[dict] = None,
) -> AuditResult:
    """结构化预检

    在语义审计前执行的快速格式检查，无需 LLM。

    Args:
        chapter_id: 章节标识（如 "ch1", "ch2_business"）
        content: 章节 Markdown 内容
        contract: 章节契约（可选，包含 must_answer / must_not_cover 等）

    Returns:
        AuditResult(passed, issues)
    """
    issues: list[str] = []
    details: dict[str, Any] = {
        "chapter_id": chapter_id,
        "content_length": len(content) if content else 0,
        "checks": {},
    }

    # ---- 检查 0: 章节是否存在 ----
    if not content or not content.strip():
        issues.append(f"[critical] 章节 {chapter_id} 内容为空")
        details["checks"]["exists"] = False
        return AuditResult(passed=False, issues=issues, score=0.0, details=details)
    details["checks"]["exists"] = True

    # ---- 检查 1: 内容最小长度 ----
    if len(content.strip()) < _MIN_CONTENT_LENGTH:
        issues.append(
            f"[critical] 章节 {chapter_id} 内容过短"
            f"（{len(content.strip())} < {_MIN_CONTENT_LENGTH} 字符）"
        )
        details["checks"]["min_length"] = False
    else:
        details["checks"]["min_length"] = True

    # ---- 检查 2: 必需小节是否存在 ----
    missing_sections: list[str] = []
    found_sections: list[str] = []

    for section_def in _REQUIRED_SECTIONS:
        section_found = False
        for pattern in section_def["patterns"]:
            if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                section_found = True
                break
        if section_found:
            found_sections.append(section_def["name"])
        else:
            missing_sections.append(section_def["name"])

    details["checks"]["required_sections"] = {
        "found": found_sections,
        "missing": missing_sections,
    }

    if missing_sections:
        severity = "critical" if len(missing_sections) >= 2 else "major"
        issues.append(
            f"[{severity}] 缺少必需小节: {', '.join(missing_sections)}"
        )

    # ---- 检查 3: 证据溯源 ----
    evidence_count = 0
    for pattern in _EVIDENCE_PATTERNS:
        evidence_count += len(re.findall(pattern, content, re.IGNORECASE))

    details["checks"]["evidence_count"] = evidence_count

    if evidence_count == 0:
        issues.append("[major] 未找到任何证据溯源标记")
    elif evidence_count < 3:
        issues.append(
            f"[minor] 证据溯源偏少（仅 {evidence_count} 处），建议增加数据来源说明"
        )

    # ---- 检查 4: Markdown 格式规范 ----
    has_heading = bool(re.search(r"^#{1,6}\s+", content, re.MULTILINE))
    details["checks"]["has_heading"] = has_heading

    if not has_heading:
        issues.append("[medium] 缺少 Markdown 标题，格式不规范")

    # ---- 检查 5: 占位符检查 ----
    placeholder_patterns = [
        r"\[LLM_GENERATE",
        r"\{\{[^}]+\}\}",
        r"TODO",
        r"TBD",
        r"待补充",
        r"待完善",
        r"\[请在此处",
        r"\[请填写",
        r"\[待填写",
        r"\[插入",
        r"\[占位",
        r"\[placeholder",
        r"\[TBD",
        r"\[TODO",
    ]
    placeholders_found: list[str] = []
    for pattern in placeholder_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            placeholders_found.extend(matches)

    details["checks"]["placeholders"] = placeholders_found

    if placeholders_found:
        issues.append(
            f"[major] 发现 {len(placeholders_found)} 处未填充的占位符: "
            + ", ".join(set(placeholders_found)[:5])
        )

    # ---- 检查 6: 契约条件项（如果提供了 contract） ----
    if contract:
        item_rules = contract.get("item_rules", [])
        for rule in item_rules:
            # 简单检查：条件项的关键词是否在内容中出现
            keywords = rule.get("keywords", [])
            if keywords:
                found_any = any(
                    kw.lower() in content.lower() for kw in keywords
                )
                if not found_any:
                    issues.append(
                        f"[medium] 条件项未满足: {rule.get('name', 'unknown')} "
                        f"(关键词: {', '.join(keywords[:3])})"
                    )

    # ---- 计算评分 ----
    critical_count = sum(1 for i in issues if "[critical]" in i)
    major_count = sum(1 for i in issues if "[major]" in i)
    medium_count = sum(1 for i in issues if "[medium]" in i)
    minor_count = sum(1 for i in issues if "[minor]" in i)

    score = 100.0
    score -= critical_count * 40
    score -= major_count * 20
    score -= medium_count * 10
    score -= minor_count * 5
    score = max(0.0, min(100.0, score))

    details["score_breakdown"] = {
        "critical": critical_count,
        "major": major_count,
        "medium": medium_count,
        "minor": minor_count,
    }

    # 通过条件：无 critical 问题，评分 >= 60
    passed = critical_count == 0 and score >= 60.0

    if passed:
        logger.info(f"结构化预检通过: {chapter_id} (score={score:.0f})")
    else:
        logger.warning(
            f"结构化预检不通过: {chapter_id} "
            f"(score={score:.0f}, issues={len(issues)})"
        )

    return AuditResult(
        passed=passed,
        issues=issues,
        score=score,
        details=details,
    )
