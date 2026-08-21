"""
事实核查模块

功能：
1. 将报告中的数据与Wind MCP数据比对
2. 验证计算结果是否正确
3. 检查引用的事实是否有可靠来源

审查原则：不降低买方报告分析的专业性和质量
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FactIssue:
    """事实核查问题"""
    issue_type: str  # "data_mismatch", "calculation_error", "source_missing"
    severity: str  # "fatal", "important", "suggestion"
    description: str
    field_name: str
    report_value: float
    actual_value: float
    deviation: float  # 偏差百分比
    chapter: int
    line: int


@dataclass
class FactCheckResult:
    """事实核查结果"""
    passed: bool
    issues: list[FactIssue] = field(default_factory=list)
    score: float = 100.0
    checked_count: int = 0
    error_count: int = 0


class FactChecker:
    """事实核查器"""

    def __init__(self):
        # 需要核查的财务指标（wind_field 一律用 canonical 键，见 canonical.py 唯一真源）
        self.financial_indicators = {
            "营业收入": {
                "patterns": [
                    r"营业收入.*?(\d+\.?\d*)\s*亿",
                    r"营收.*?(\d+\.?\d*)\s*亿",
                    r"总收入.*?(\d+\.?\d*)\s*亿",
                ],
                "wind_field": "营业收入",
                "tolerance": 0.05,  # 允许5%误差
            },
            "净利润": {
                "patterns": [
                    r"净利润.*?(-?\d+\.?\d*)\s*亿",
                    r"净亏损.*?(\d+\.?\d*)\s*亿",
                ],
                "wind_field": "归母净利润",
                "tolerance": 0.05,
            },
            "营业利润": {
                "patterns": [
                    r"营业利润.*?(-?\d+\.?\d*)\s*亿",
                    r"营业亏损.*?(\d+\.?\d*)\s*亿",
                ],
                "wind_field": "营业利润",
                "tolerance": 0.05,
            },
            "总资产": {
                "patterns": [
                    r"总资产.*?(\d+\.?\d*)\s*亿",
                    r"资产.*?总计.*?(\d+\.?\d*)\s*亿",
                ],
                "wind_field": "总资产",
                "tolerance": 0.05,
            },
            "经营现金流": {
                "patterns": [
                    r"经营.*?现金流.*?(-?\d+\.?\d*)\s*亿",
                    r"经营活动.*?现金流.*?(-?\d+\.?\d*)\s*亿",
                ],
                "wind_field": "经营活动现金流量净额",
                "tolerance": 0.10,  # 现金流允许10%误差
            },
        }

        # 需要核查的计算指标
        self.calculated_indicators = {
            "毛利率": {
                "formula": "(营业收入 - 营业成本) / 营业收入",
                "required_fields": ["营业收入", "营业成本"],
                "tolerance": 0.02,  # 毛利率允许2%误差
            },
            "营收增长率": {
                "formula": "(本期营收 - 上期营收) / 上期营收",
                "required_fields": ["营业收入"],
                "tolerance": 0.05,
            },
            "净利润增长率": {
                "formula": "(本期净利润 - 上期净利润) / |上期净利润|",
                "required_fields": ["归母净利润"],
                "tolerance": 0.05,
            },
        }

    def check(
        self,
        chapters: dict[int, str],
        wind_data: dict[str, Any],
    ) -> FactCheckResult:
        """
        执行事实核查

        Args:
            chapters: 各章节内容 {chapter_num: content}
            wind_data: Wind数据

        Returns:
            FactCheckResult
        """
        issues = []
        checked_count = 0
        error_count = 0

        # 1. 核查直接引用的数据
        for ch_num, content in chapters.items():
            for indicator, config in self.financial_indicators.items():
                result = self._check_direct_data(
                    content, ch_num, indicator, config, wind_data
                )
                if result:
                    checked_count += 1
                    if result.severity in ["fatal", "important"]:
                        error_count += 1
                    issues.append(result)

        # 2. 核查计算结果
        for ch_num, content in chapters.items():
            for indicator, config in self.calculated_indicators.items():
                result = self._check_calculated_data(
                    content, ch_num, indicator, config, wind_data
                )
                if result:
                    checked_count += 1
                    if result.severity in ["fatal", "important"]:
                        error_count += 1
                    issues.append(result)

        # 3. 核查同比变化
        for ch_num, content in chapters.items():
            yoy_issues = self._check_yoy_changes(content, ch_num, wind_data)
            issues.extend(yoy_issues)
            checked_count += len(yoy_issues)
            error_count += sum(1 for i in yoy_issues if i.severity in ["fatal", "important"])

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
            logger.warning(f"事实核查不通过: score={score:.0f}, issues={len(issues)}")

        return FactCheckResult(
            passed=passed,
            issues=issues,
            score=score,
            checked_count=checked_count,
            error_count=error_count,
        )

    def _check_direct_data(
        self,
        content: str,
        ch_num: int,
        indicator: str,
        config: dict,
        wind_data: dict,
    ) -> FactIssue | None:
        """核查直接引用的数据"""

        # 从报告中提取数据
        report_value = self._extract_value(content, config["patterns"])
        if report_value is None:
            return None

        # 从Wind数据中获取实际值
        wind_field = config["wind_field"]
        actual_value = self._get_wind_value(wind_data, wind_field)
        if actual_value is None:
            return None

        # 计算偏差
        if actual_value != 0:
            deviation = abs(report_value - actual_value) / abs(actual_value)
        else:
            deviation = abs(report_value - actual_value)

        # 检查是否超出容忍度
        tolerance = config["tolerance"]
        if deviation > tolerance:
            # 判断严重程度
            if deviation > 0.50:  # 偏差超过50%
                severity = "fatal"
            elif deviation > 0.20:  # 偏差超过20%
                severity = "important"
            else:
                severity = "suggestion"

            line = self._find_line_number(content, indicator)

            return FactIssue(
                issue_type="data_mismatch",
                severity=severity,
                description=f"{indicator}报告值{report_value}亿与Wind数据{actual_value}亿偏差{deviation*100:.1f}%",
                field_name=indicator,
                report_value=report_value,
                actual_value=actual_value,
                deviation=deviation,
                chapter=ch_num,
                line=line,
            )

        return None

    def _check_calculated_data(
        self,
        content: str,
        ch_num: int,
        indicator: str,
        config: dict,
        wind_data: dict,
    ) -> FactIssue | None:
        """核查计算结果"""

        # 从报告中提取计算结果
        report_value = self._extract_value(content, [fr"{indicator}.*?(\d+\.?\d*)\s*%"])
        if report_value is None:
            return None

        # 根据指标类型计算实际值
        actual_value = None

        if indicator == "毛利率":
            revenue = self._get_wind_value(wind_data, "年营业收入")
            cost = self._get_wind_value(wind_data, "年营业成本")
            if revenue and cost and revenue > 0:
                actual_value = (revenue - cost) / revenue * 100

        elif indicator == "营收增长率":
            revenues = self._get_wind_list(wind_data, "年营业收入")
            if len(revenues) >= 2 and revenues[-2] > 0:
                actual_value = (revenues[-1] - revenues[-2]) / revenues[-2] * 100

        elif indicator == "净利润增长率":
            profits = self._get_wind_list(wind_data, "年净利润")
            if len(profits) >= 2 and profits[-2] != 0:
                actual_value = (profits[-1] - profits[-2]) / abs(profits[-2]) * 100

        if actual_value is None:
            return None

        # 计算偏差
        if actual_value != 0:
            deviation = abs(report_value - actual_value) / abs(actual_value)
        else:
            deviation = abs(report_value - actual_value)

        # 检查是否超出容忍度
        tolerance = config["tolerance"]
        if deviation > tolerance:
            severity = "important" if deviation > 0.20 else "suggestion"
            line = self._find_line_number(content, indicator)

            return FactIssue(
                issue_type="calculation_error",
                severity=severity,
                description=f"{indicator}报告值{report_value:.1f}%与计算值{actual_value:.1f}%偏差{deviation*100:.1f}%",
                field_name=indicator,
                report_value=report_value,
                actual_value=actual_value,
                deviation=deviation,
                chapter=ch_num,
                line=line,
            )

        return None

    def _check_yoy_changes(
        self,
        content: str,
        ch_num: int,
        wind_data: dict,
    ) -> list[FactIssue]:
        """核查同比变化"""
        issues = []

        # 提取同比变化描述
        yoy_patterns = [
            r"同比增长.*?(\d+\.?\d*)\s*%",
            r"增长.*?(\d+\.?\d*)\s*%",
            r"同比.*?(\d+\.?\d*)\s*%",
        ]

        for pattern in yoy_patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                try:
                    report_growth = float(match)

                    # 计算实际增长率
                    revenues = self._get_wind_list(wind_data, "年营业收入")
                    if len(revenues) >= 2 and revenues[-2] > 0:
                        actual_growth = (revenues[-1] - revenues[-2]) / revenues[-2] * 100

                        # 检查偏差
                        deviation = abs(report_growth - actual_growth) / abs(actual_growth)

                        if deviation > 0.10:  # 偏差超过10%
                            line = self._find_line_number(content, "增长")
                            issues.append(FactIssue(
                                issue_type="data_mismatch",
                                severity="important",
                                description=f"营收增长率报告值{report_growth:.1f}%与实际值{actual_growth:.1f}%偏差{deviation*100:.1f}%",
                                field_name="营收增长率",
                                report_value=report_growth,
                                actual_value=actual_growth,
                                deviation=deviation,
                                chapter=ch_num,
                                line=line,
                            ))
                except ValueError:
                    continue

        return issues

    def _extract_value(self, content: str, patterns: list[str]) -> float | None:
        """从内容中提取数值"""
        for pattern in patterns:
            matches = re.findall(pattern, content)
            if matches:
                try:
                    return float(matches[0])
                except ValueError:
                    continue
        return None

    def _get_wind_value(self, wind_data: dict, field: str) -> float | None:
        """从Wind数据中获取单个值（canonical 别名兜底）"""
        if not wind_data:
            return None

        income = wind_data.get("income", {})
        balance = wind_data.get("balance", {})
        cashflow = wind_data.get("cashflow", {})

        # 在各个表中查找（先精确，再 canonical 别名）
        for table in [income, balance, cashflow]:
            if field in table:
                values = table[field]
                if isinstance(values, list) and values:
                    return values[-1]  # 返回最新值
        # canonical 别名兜底
        try:
            from ..canonical import get_series
            series = get_series(wind_data, field)
            if series:
                return series[-1]
        except ImportError:
            pass

        return None

    def _get_wind_list(self, wind_data: dict, field: str) -> list[float]:
        """从Wind数据中获取列表（canonical 别名兜底）"""
        if not wind_data:
            return []

        income = wind_data.get("income", {})
        balance = wind_data.get("balance", {})
        cashflow = wind_data.get("cashflow", {})

        for table in [income, balance, cashflow]:
            if field in table:
                values = table[field]
                if isinstance(values, list):
                    return values
        # canonical 别名兜底
        try:
            from ..canonical import get_series
            return get_series(wind_data, field)
        except ImportError:
            pass

        return []

    def _find_line_number(self, content: str, keyword: str) -> int:
        """查找关键词所在行号"""
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if keyword in line:
                return i + 1
        return 0


def check_facts(
    chapters: dict[int, str],
    wind_data: dict[str, Any],
) -> FactCheckResult:
    """
    事实核查（入口函数）

    Args:
        chapters: 各章节内容 {chapter_num: content}
        wind_data: Wind数据

    Returns:
        FactCheckResult
    """
    checker = FactChecker()
    return checker.check(chapters, wind_data)
