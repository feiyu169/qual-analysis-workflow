"""
结论合理性审查模块

功能：
1. 检查投资评级是否与分析结论一致
2. 检查估值是否合理（与行业对比）
3. 检查风险收益比是否合理
4. 检查触发条件是否合理

审查原则：不降低买方报告分析的专业性和质量
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

# v3.1 P0-A-3：确定性/终止性异常白名单（不降级，fail-closed 上抛）
from ..llm_errors import (
    DeterministicLLMFailure,
    LLMCallBudgetExceeded,
    WallClockDeadlineExceeded,
)

logger = logging.getLogger(__name__)


@dataclass
class ConclusionIssue:
    """结论合理性问题"""
    issue_type: str  # "rating_contradiction", "valuation_mismatch", "trigger_issue"
    severity: str  # "fatal", "important", "suggestion"
    description: str
    chapter: int
    line: int


@dataclass
class ConclusionValidationResult:
    """结论合理性审查结果"""
    passed: bool
    issues: list[ConclusionIssue] = field(default_factory=list)
    score: float = 100.0
    extracted_rating: str | None = None
    extracted_valuation: dict | None = None


class ConclusionValidator:
    """结论合理性审查器"""

    def __init__(self):
        # 投资评级模式
        self.rating_patterns = [
            r"评级[：:]\s*(买入|增持|推荐|中性|持有|减持|卖出|回避)",
            r"(买入|增持|推荐|中性|持有|减持|卖出|回避)\s*评级",
            r"投资.*?(买入|增持|推荐|中性|持有|减持|卖出|回避)",
        ]

        # 估值判断模式
        self.valuation_patterns = [
            r"估值.*?(合理|偏低|偏高|低估|高估|均衡)",
            r"(合理|偏低|偏高|低估|高估|均衡).*?估值",
            r"安全边际.*?(强|中等|弱|充足|不足)",
        ]

        # 上行空间模式
        self.upside_patterns = [
            r"上行.*?(\d+\.?\d*)\s*%",
            r"上涨.*?(\d+\.?\d*)\s*%",
            r"目标价.*?(\d+\.?\d*)\s*港元",
        ]

        # 触发条件模式
        self.trigger_patterns = [
            r"触发.*?买入.*?条件",
            r"触发.*?卖出.*?条件",
            r"升级.*?推荐.*?条件",
            r"降级.*?回避.*?条件",
        ]

        # 评级与估值的对应关系
        self.rating_valuation_map = {
            "买入": ["低估", "偏低", "强", "充足"],
            "增持": ["低估", "偏低", "中等"],
            "推荐": ["低估", "偏低", "中等"],
            "中性": ["合理", "均衡", "中等"],
            "持有": ["合理", "均衡", "中等"],
            "减持": ["高估", "偏高", "弱", "不足"],
            "卖出": ["高估", "偏高", "弱", "不足"],
            "回避": ["高估", "偏高", "弱", "不足"],
        }

    def check(
        self,
        chapters: dict[int, str],
        llm_caller: Callable[[str, str], str] | None = None,
        wind_data: dict | None = None,
    ) -> ConclusionValidationResult:
        """
        执行结论合理性审查

        Args:
            chapters: 各章节内容 {chapter_num: content}
            llm_caller: LLM调用函数（可选）
            wind_data: Wind 数据（注入锚点表，供 LLM 评估估值/数据合理性）

        Returns:
            ConclusionValidationResult
        """
        issues = []

        # 1. 提取投资评级
        rating = self._extract_rating(chapters)

        # 2. 提取估值判断
        valuation_judgment = self._extract_valuation_judgment(chapters)

        # 3. 提取上行空间
        upside = self._extract_upside(chapters)

        # 4. 检查评级与估值的一致性
        if rating and valuation_judgment:
            consistency_issue = self._check_rating_valuation_consistency(
                rating, valuation_judgment, chapters
            )
            if consistency_issue:
                issues.append(consistency_issue)

        # 5. 检查上行空间与评级的一致性
        if rating and upside:
            upside_issue = self._check_upside_consistency(
                rating, upside, chapters
            )
            if upside_issue:
                issues.append(upside_issue)

        # 6. 检查触发条件的合理性
        trigger_issues = self._check_trigger_conditions(chapters)
        issues.extend(trigger_issues)

        # 7. 使用LLM进行深度审查（如果可用）
        if llm_caller:
            llm_issues = self._check_by_llm(chapters, rating, llm_caller, wind_data)
            issues.extend(llm_issues)

        # 计算评分
        fatal_count = sum(1 for i in issues if i.severity == "fatal")
        important_count = sum(1 for i in issues if i.severity == "important")
        suggestion_count = sum(1 for i in issues if i.severity == "suggestion")

        score = 100.0
        score -= fatal_count * 40
        score -= important_count * 15
        score -= suggestion_count * 5
        score = max(0.0, min(100.0, score))

        passed = fatal_count == 0 and score >= 60.0

        if not passed:
            logger.warning(f"结论合理性审查不通过: score={score:.0f}, issues={len(issues)}")

        return ConclusionValidationResult(
            passed=passed,
            issues=issues,
            score=score,
            extracted_rating=rating,
            extracted_valuation=valuation_judgment,
        )

    def _extract_rating(self, chapters: dict[int, str]) -> str | None:
        """提取投资评级"""
        for ch_num, content in chapters.items():  # noqa: PERF102
            for pattern in self.rating_patterns:
                match = re.search(pattern, content)
                if match:
                    return match.group(1)
        return None

    def _extract_valuation_judgment(self, chapters: dict[int, str]) -> dict | None:
        """提取估值判断"""
        judgment = {}

        for ch_num, content in chapters.items():  # noqa: PERF102
            for pattern in self.valuation_patterns:
                match = re.search(pattern, content)
                if match:
                    judgment["估值判断"] = match.group(1)
                    break

            # 提取安全边际
            safety_pattern = r"安全边际.*?(强|中等|弱|充足|不足)"
            match = re.search(safety_pattern, content)
            if match:
                judgment["安全边际"] = match.group(1)

        return judgment if judgment else None

    def _extract_upside(self, chapters: dict[int, str]) -> dict | None:
        """提取上行空间"""
        upside = {}

        for ch_num, content in chapters.items():  # noqa: PERF102
            for pattern in self.upside_patterns:
                match = re.search(pattern, content)
                if match:
                    if "%" in pattern:
                        upside["上行空间"] = float(match.group(1))
                    elif "目标价" in pattern:
                        upside["目标价"] = float(match.group(1))
                    break

        return upside if upside else None

    def _check_rating_valuation_consistency(
        self,
        rating: str,
        valuation_judgment: dict,
        chapters: dict[int, str],
    ) -> ConclusionIssue | None:
        """检查评级与估值的一致性"""

        # 获取评级对应的合理估值判断
        expected_valuations = self.rating_valuation_map.get(rating, [])

        # 检查实际估值判断是否在预期范围内
        actual_valuation = valuation_judgment.get("估值判断", "")
        actual_safety = valuation_judgment.get("安全边际", "")

        # 判断是否一致
        is_consistent = False

        for expected in expected_valuations:
            if expected in actual_valuation or expected in actual_safety:
                is_consistent = True
                break

        if not is_consistent:
            # 找到相关章节和行号
            for ch_num, content in chapters.items():
                if "评级" in content:
                    line = self._find_line_number(content, "评级")
                    return ConclusionIssue(
                        issue_type="rating_contradiction",
                        severity="fatal",
                        description=f"投资评级'{rating}'与估值判断'{actual_valuation}'不一致",
                        chapter=ch_num,
                        line=line,
                    )

        return None

    def _check_upside_consistency(
        self,
        rating: str,
        upside: dict,
        chapters: dict[int, str],
    ) -> ConclusionIssue | None:
        """检查上行空间与评级的一致性"""

        upside_pct = upside.get("上行空间", 0)

        # 判断上行空间是否与评级一致
        if rating in ["买入", "增持", "推荐"] and upside_pct < 10:
            # 买入评级但上行空间不足10%
            for ch_num, content in chapters.items():
                if "上行" in content:
                    line = self._find_line_number(content, "上行")
                    return ConclusionIssue(
                        issue_type="valuation_mismatch",
                        severity="important",
                        description=f"投资评级'{rating}'但上行空间仅{upside_pct:.1f}%，不足以支撑买入",
                        chapter=ch_num,
                        line=line,
                    )

        elif rating in ["中性", "持有"] and upside_pct > 50:
            # 中性评级但上行空间超过50%
            for ch_num, content in chapters.items():
                if "上行" in content:
                    line = self._find_line_number(content, "上行")
                    return ConclusionIssue(
                        issue_type="valuation_mismatch",
                        severity="important",
                        description=f"投资评级'{rating}'但上行空间达{upside_pct:.1f}%，应考虑升级评级",
                        chapter=ch_num,
                        line=line,
                    )

        return None

    def _check_trigger_conditions(self, chapters: dict[int, str]) -> list[ConclusionIssue]:
        """检查触发条件的合理性"""
        issues = []

        # 提取触发条件
        triggers = self._extract_triggers(chapters)

        # 检查是否有买入触发条件
        if not triggers.get("买入"):
            for ch_num, content in chapters.items():
                if "触发" in content or "条件" in content:
                    line = self._find_line_number(content, "触发")
                    issues.append(ConclusionIssue(
                        issue_type="trigger_issue",
                        severity="suggestion",
                        description="报告缺少明确的买入触发条件",
                        chapter=ch_num,
                        line=line,
                    ))
                    break

        # 检查是否有卖出触发条件
        if not triggers.get("卖出"):
            for ch_num, content in chapters.items():
                if "触发" in content or "条件" in content:
                    line = self._find_line_number(content, "触发")
                    issues.append(ConclusionIssue(
                        issue_type="trigger_issue",
                        severity="suggestion",
                        description="报告缺少明确的卖出触发条件",
                        chapter=ch_num,
                        line=line,
                    ))
                    break

        return issues

    def _extract_triggers(self, chapters: dict[int, str]) -> dict[str, list[str]]:
        """提取触发条件"""
        triggers = {"买入": [], "卖出": []}

        for ch_num, content in chapters.items():  # noqa: PERF102
            # 提取买入触发条件
            buy_pattern = r"触发.*?买入.*?[：:]\s*(.+?)(?:\n|触发|$)"
            matches = re.findall(buy_pattern, content, re.DOTALL)
            triggers["买入"].extend(matches)

            # 提取卖出触发条件
            sell_pattern = r"触发.*?卖出.*?[：:]\s*(.+?)(?:\n|触发|$)"
            matches = re.findall(sell_pattern, content, re.DOTALL)
            triggers["卖出"].extend(matches)

        return triggers

    def _check_by_llm(
        self,
        chapters: dict[int, str],
        rating: str | None,
        llm_caller: Callable[[str, str], str],
        wind_data: dict | None = None,
    ) -> list[ConclusionIssue]:
        """使用LLM进行深度审查（审查改进：注入 Wind 锚点供评估对照）"""
        issues = []

        try:
            # 构建 Wind 锚点表
            wind_anchor = ""
            if wind_data:
                try:
                    from ..qual_v8.data_anchor import get_data_anchor
                    anchor = get_data_anchor(wind_data)
                    all_a = anchor.get_all_anchors()
                    if all_a:
                        fys = sorted({dp.fiscal_year for pts in all_a.values()
                                      for dp in pts if dp.fiscal_year is not None})
                        rows = []
                        for k, pts in all_a.items():
                            row = {dp.fiscal_year: f"{dp.value:.2f}" for dp in pts if dp.fiscal_year is not None}
                            rows.append(f"| {k} | " + " | ".join(row.get(fy, "—") for fy in fys) + " |")
                        wind_anchor = "| 指标 | " + " | ".join(f"FY{fy}" for fy in fys) + " |\n|------|" + \
                            "--------|" * len(fys) + "\n" + "\n".join(rows)
                except Exception as e:
                    logger.warning(f"结论审查锚点构建失败: {e}")

            # 构建审查prompt
            prompt = f"""
请审查以下投资报告的结论合理性：

投资评级：{rating or '未提取到'}

## Wind 验证数据（评估数据/估值合理性的标准答案）
{wind_anchor}

报告内容摘要：
{self._get_content_summary(chapters)}

请评估：
1. 投资评级是否与分析结论一致？
2. 估值是否合理？（对照 Wind 锚点：PE/PB/市值等）
3. 风险收益比是否合理？
4. 是否存在逻辑矛盾？
5. 结论是否被数据支撑？（对照 Wind 锚点检查财务数字）

如果存在问题，请指出具体问题。
"""

            # 调用LLM
            response = llm_caller("conclusion_validation", prompt)

            # 解析响应
            if "矛盾" in response or "不一致" in response or "问题" in response:
                issues.append(ConclusionIssue(
                    issue_type="rating_contradiction",
                    severity="important",
                    description=f"LLM审查发现结论问题: {response[:200]}",
                    chapter=0,
                    line=0,
                ))

        except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded):
            raise  # v3.1 P0-A-3 白名单：预算/墙钟/确定性失败不降级（fail-closed）
        except Exception as e:
            logger.warning(f"LLM结论审查失败: {e}")

        return issues

    def _get_content_summary(self, chapters: dict[int, str]) -> str:
        """获取内容摘要"""
        summary = []
        for ch_num, content in chapters.items():
            # 提取前500字符
            summary.append(f"第{ch_num}章: {content[:500]}...")
        return "\n".join(summary[:5])  # 只取前5章

    def _find_line_number(self, content: str, keyword: str) -> int:
        """查找关键词所在行号"""
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if keyword in line:
                return i + 1
        return 0


def check_conclusion(
    chapters: dict[int, str],
    llm_caller: Callable[[str, str], str] | None = None,
    wind_data: dict | None = None,
) -> ConclusionValidationResult:
    """
    结论合理性审查（入口函数）

    Args:
        chapters: 各章节内容 {chapter_num: content}
        llm_caller: LLM调用函数（可选）
        wind_data: Wind 数据（注入锚点表）

    Returns:
        ConclusionValidationResult
    """
    validator = ConclusionValidator()
    return validator.check(chapters, llm_caller, wind_data)
