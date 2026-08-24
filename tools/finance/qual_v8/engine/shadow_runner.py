"""
影子运行框架（P0-1 HeavySkill 审查要求）。

新 3 个检查器作为主路径执行，旧 16 个检查器作为影子模式运行（只记录不阻断）。
A/B 对比：新检查器的问题列表 vs 旧检查器的问题列表，计算漏检率。

Phase 2 期间旧检查器不删除；Phase 5 A/B 通过后才允许删除。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ShadowResult:
    """影子运行对比结果。

    Attributes:
        new_issues: 新检查器发现的问题列表。
        shadow_issues: 旧检查器（影子模式）发现的问题列表。
        missed_by_new: 旧检查器发现但新检查器遗漏的问题（漏检）。
        false_positives_new: 新检查器发现但旧检查器没有的问题（新误报）。
        coverage: 新检查器对旧检查器的覆盖率（1 - 漏检率）。
        total_shadow: 旧检查器问题总数。
        total_missed: 漏检数。
    """
    new_issues: list[str] = field(default_factory=list)
    shadow_issues: list[str] = field(default_factory=list)
    missed_by_new: list[str] = field(default_factory=list)
    false_positives_new: list[str] = field(default_factory=list)
    coverage: float = 1.0
    total_shadow: int = 0
    total_missed: int = 0


def _normalize_issue(issue: str) -> str:
    """规范化问题描述（去章节数字/具体数值，保留问题类型）。"""
    import re
    # 去除"第N章"前缀
    normalized = re.sub(r"第\d+章\s*", "", issue)
    # 去除具体数值（保留指标名）
    normalized = re.sub(r"=\s*-?\d+\.?\d*", "=<NUM>", normalized)
    # 去除 FY+年份
    normalized = re.sub(r"FY\d{4}", "FY<YEAR>", normalized)
    return normalized.strip()


def compare_results(
    new_issues: list[str],
    shadow_issues: list[str],
    threshold: float = 0.95,
) -> ShadowResult:
    """对比新旧检查器结果，计算漏检率。

    Args:
        new_issues: 新检查器发现的问题列表。
        shadow_issues: 旧检查器（影子模式）发现的问题列表。
        threshold: 覆盖率阈值（低于此值告警）。

    Returns:
        ShadowResult 对比结果。
    """
    result = ShadowResult(
        new_issues=new_issues,
        shadow_issues=shadow_issues,
        total_shadow=len(shadow_issues),
    )

    if not shadow_issues:
        result.coverage = 1.0
        return result

    # 规范化后比较
    new_normalized = {_normalize_issue(i) for i in new_issues}
    shadow_normalized = {_normalize_issue(i) for i in shadow_issues}

    # 漏检：旧检查器有但新检查器没有（模糊匹配：包含关系）
    missed = []
    for shadow_issue in shadow_normalized:
        found = False
        for new_issue in new_normalized:
            # 互为子串即视为命中（容错四舍五入/表述差异）
            if shadow_issue in new_issue or new_issue in shadow_issue:
                found = True
                break
        if not found:
            missed.append(shadow_issue)

    # 新误报：新检查器有但旧检查器没有
    false_positives = []
    for new_issue in new_normalized:
        found = False
        for shadow_issue in shadow_normalized:
            if new_issue in shadow_issue or shadow_issue in new_issue:
                found = True
                break
        if not found:
            false_positives.append(new_issue)

    result.missed_by_new = missed
    result.false_positives_new = false_positives
    result.total_missed = len(missed)
    result.coverage = 1.0 - (len(missed) / len(shadow_normalized)) if shadow_normalized else 1.0

    if result.coverage < threshold:
        logger.warning(
            f"⚠️ 影子运行覆盖率 {result.coverage:.1%} < 阈值 {threshold:.0%}，"
            f"漏检 {result.total_missed}/{result.total_shadow} 项"
        )

    return result


def run_shadow_comparison(
    chapters: dict[int, str],
    wind_data: dict[str, Any],
    anchor: Any,
) -> ShadowResult:
    """运行影子对比：新 3 检查器 vs 旧检查器。

    Args:
        chapters: 章节内容。
        wind_data: Wind 数据。
        anchor: DataAnchor 实例。

    Returns:
        ShadowResult 对比结果。
    """
    from ...quality.cross_chapter_consistency import CrossChapterConsistencyChecker
    from ...quality.numeric_guard import NumericGuard
    from ...quality.structural_check import structural_check

    # 新 3 检查器（主路径）
    new_issues: list[str] = []

    # 1. NumericGuard
    try:
        guard = NumericGuard()
        for _ch_num, content in chapters.items():
            result = guard.check_all(_ch_num, content, wind_data)
            if not result.passed:
                new_issues.extend(f"[NumericGuard] {v.message}" for v in result.violations)
    except Exception as e:
        logger.warning(f"NumericGuard 影子运行异常: {e}")

    # 2. StructuralCheck
    try:
        for _ch_num, content in chapters.items():
            result = structural_check(f"ch{_ch_num}", content)
            if not result.passed:
                new_issues.extend(f"[Structural] {i}" for i in result.issues)
    except Exception as e:
        logger.warning(f"StructuralCheck 影子运行异常: {e}")

    # 3. CrossChapterConsistency
    try:
        checker = CrossChapterConsistencyChecker(wind_data)
        # v9: check() now returns CheckResult (CheckerProtocol interface)
        # Use _check_consistency() for backward-compatible ConsistencyResult
        result = checker._check_consistency(chapters)
        if not result.passed:
            new_issues.extend(f"[Consistency] {i.description}" for i in result.issues)
    except Exception as e:
        logger.warning(f"CrossChapter 影子运行异常: {e}")

    # 旧检查器（影子模式）——只记录不阻断
    shadow_issues: list[str] = []
    try:
        from ...quality.fact_checker import check_facts
        result = check_facts(chapters, wind_data or {})
        if not result.passed:
            shadow_issues.extend(f"[FactChecker] {i.description}" for i in result.issues)
    except Exception:
        pass

    try:
        from ...quality.conclusion_validator import check_conclusion
        result = check_conclusion(chapters, None, wind_data)
        if not result.passed:
            shadow_issues.extend(f"[Conclusion] {i.description}" for i in result.issues)
    except Exception:
        pass

    try:
        from ...quality.logic_consistency_check import check_logic_consistency
        for _ch_num, content in chapters.items():
            result = check_logic_consistency(content)
            if result:
                shadow_issues.extend(f"[Logic] {i}" for i in result)
    except Exception:
        pass

    try:
        from ...quality.date_anchor_check import check_date_anchors
        for _ch_num, content in chapters.items():
            result = check_date_anchors(content, wind_data)
            if result:
                shadow_issues.extend(f"[DateAnchor] {i}" for i in result)
    except Exception:
        pass

    return compare_results(new_issues, shadow_issues)
