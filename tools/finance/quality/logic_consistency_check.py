"""
逻辑一致性检查模块

功能：
1. 检查估值模型与叙述结论是否一致
2. 检查量化结论与定性结论是否一致
3. 检查投资评级与风险评估是否一致

解决批判性审阅发现的问题：
- F2: 估值量化模型与叙述结论矛盾
- F4: 三套估值方法互不收敛
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class LogicIssue:
    """逻辑一致性问题"""
    issue_type: str  # "valuation_contradiction", "rating_contradiction", "logic_gap"
    severity: str  # "fatal", "important", "suggestion"
    description: str
    chapter: int
    line: int
    content: str


@dataclass
class LogicResult:
    """逻辑一致性检查结果"""
    passed: bool
    issues: list[LogicIssue] = field(default_factory=list)
    score: float = 100.0


class LogicConsistencyChecker:
    """逻辑一致性检查器"""

    def __init__(self):
        # 估值相关模式
        self.valuation_patterns = {
            "情景分析": [
                r"基准.*?(\d+\.?\d*)\s*元",
                r"乐观.*?(\d+\.?\d*)\s*元",
                r"悲观.*?(\d+\.?\d*)\s*元",
            ],
            "概率加权": [
                r"概率加权.*?(\d+\.?\d*)\s*元",
                r"加权.*?(\d+\.?\d*)\s*元",
            ],
            "上行空间": [
                r"上行.*?(\d+\.?\d*)\s*%",
                r"上涨.*?(\d+\.?\d*)\s*%",
                r"(\d+\.?\d*)\s*%\s*上行",
            ],
            "当前股价": [
                r"当前.*?(\d+\.?\d*)\s*港元",
                r"现价.*?(\d+\.?\d*)\s*港元",
                r"收盘.*?(\d+\.?\d*)\s*港元",
            ],
        }

        # 投资评级模式
        self.rating_patterns = {
            "评级": [
                r"评级[：:]\s*(买入|增持|中性|减持|卖出)",
                r"(买入|增持|中性|减持|卖出)\s*评级",
            ],
            "估值判断": [
                r"估值.*?合理",
                r"估值.*?偏高",
                r"估值.*?偏低",
                r"估值.*?低估",
                r"估值.*?高估",
            ],
            "安全边际": [
                r"安全边际.*?强",
                r"安全边际.*?弱",
                r"安全边际.*?中等",
            ],
        }

    def check(self, chapters: dict[int, str]) -> LogicResult:
        """
        检查逻辑一致性

        Args:
            chapters: 各章节内容 {chapter_num: content}

        Returns:
            LogicResult
        """
        issues = []

        # 1. 检查估值逻辑一致性
        valuation_issues = self._check_valuation_consistency(chapters)
        issues.extend(valuation_issues)

        # 2. 检查评级逻辑一致性
        rating_issues = self._check_rating_consistency(chapters)
        issues.extend(rating_issues)

        # 3. 检查投资逻辑一致性
        logic_issues = self._check_investment_logic(chapters)
        issues.extend(logic_issues)

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
            logger.warning(f"逻辑一致性检查不通过: score={score:.0f}, issues={len(issues)}")

        return LogicResult(
            passed=passed,
            issues=issues,
            score=score,
        )

    def _check_valuation_consistency(self, chapters: dict[int, str]) -> list[LogicIssue]:
        """检查估值逻辑一致性"""
        issues = []

        # 提取估值相关数据
        valuation_data = self._extract_valuation_data(chapters)

        # 检查1：情景分析基准值 vs 上行空间
        if "情景分析" in valuation_data and "上行空间" in valuation_data:
            base_value = valuation_data["情景分析"].get("基准", 0)
            upside = valuation_data["上行空间"].get("上行空间", 0)
            current_price = valuation_data.get("当前股价", {}).get("当前股价", 0)

            if base_value > 0 and current_price > 0:
                # 计算隐含上行空间
                implied_upside = (base_value / current_price - 1) * 100

                # 如果声称的上行空间与隐含上行空间差距超过50%，报告问题
                if abs(upside - implied_upside) > 50:
                    # 找到相关章节和行号
                    for ch_num, content in chapters.items():
                        if "上行空间" in content:
                            line = self._find_line_number(content, "上行空间")
                            issues.append(LogicIssue(
                                issue_type="valuation_contradiction",
                                severity="fatal",
                                description=f"情景分析基准值{base_value}元隐含上行空间{implied_upside:.1f}%，但叙述声称上行空间{upside}%",
                                chapter=ch_num,
                                line=line,
                                content=f"基准值{base_value}元 vs 上行空间{upside}%",
                            ))
                            break

        # 检查2：情景分析基准值 vs 估值判断
        if "情景分析" in valuation_data and "估值判断" in valuation_data:
            base_value = valuation_data["情景分析"].get("基准", 0)
            valuation_judgment = valuation_data["估值判断"].get("估值判断", "")
            current_price = valuation_data.get("当前股价", {}).get("当前股价", 0)

            if base_value > 0 and current_price > 0:
                # 判断是否低估/高估
                ratio = base_value / current_price

                if ratio < 0.8 and "低估" not in valuation_judgment:
                    # 基准值低于现价20%以上，但叙述说"合理"或"低估"
                    for ch_num, content in chapters.items():
                        if "估值" in content and ("合理" in content or "低估" in content):
                            line = self._find_line_number(content, "估值")
                            issues.append(LogicIssue(
                                issue_type="valuation_contradiction",
                                severity="fatal",
                                description=f"情景分析基准值{base_value}元低于现价{current_price}港元{(1-ratio)*100:.1f}%，但叙述说{valuation_judgment}",
                                chapter=ch_num,
                                line=line,
                                content=f"基准值{base_value}元 vs 现价{current_price}港元",
                            ))
                            break

        # 检查3：三套估值方法是否收敛
        if "情景分析" in valuation_data and "概率加权" in valuation_data:
            base_value = valuation_data["情景分析"].get("基准", 0)
            weighted_value = valuation_data["概率加权"].get("概率加权", 0)

            if base_value > 0 and weighted_value > 0:
                # 如果基准值和概率加权值差距超过100%，报告问题
                if abs(weighted_value - base_value) / base_value > 1.0:
                    for ch_num, content in chapters.items():
                        if "情景分析" in content or "概率加权" in content:
                            line = self._find_line_number(content, "情景")
                            issues.append(LogicIssue(
                                issue_type="valuation_contradiction",
                                severity="important",
                                description=f"情景分析基准值{base_value}元与概率加权值{weighted_value}元差距过大",
                                chapter=ch_num,
                                line=line,
                                content=f"基准值{base_value}元 vs 概率加权值{weighted_value}元",
                            ))
                            break

        return issues

    def _check_rating_consistency(self, chapters: dict[int, str]) -> list[LogicIssue]:
        """检查评级逻辑一致性"""
        issues = []

        # 提取评级相关数据
        rating_data = self._extract_rating_data(chapters)

        # 检查1：评级与估值判断是否一致
        if "评级" in rating_data and "估值判断" in rating_data:
            rating = rating_data["评级"]
            judgment = rating_data["估值判断"]

            # 买入评级应该对应低估判断
            if rating == "买入" and "高估" in judgment:
                for ch_num, content in chapters.items():
                    if "评级" in content:
                        line = self._find_line_number(content, "评级")
                        issues.append(LogicIssue(
                            issue_type="rating_contradiction",
                            severity="fatal",
                            description=f"投资评级为{rating}，但估值判断为{judgment}",
                            chapter=ch_num,
                            line=line,
                            content=f"评级{rating} vs 估值{judgment}",
                        ))
                        break

            # 中性评级应该对应合理判断
            if rating == "中性" and ("低估" in judgment or "高估" in judgment):
                for ch_num, content in chapters.items():
                    if "评级" in content:
                        line = self._find_line_number(content, "评级")
                        issues.append(LogicIssue(
                            issue_type="rating_contradiction",
                            severity="important",
                            description=f"投资评级为{rating}，但估值判断为{judgment}",
                            chapter=ch_num,
                            line=line,
                            content=f"评级{rating} vs 估值{judgment}",
                        ))
                        break

        return issues

    def _check_investment_logic(self, chapters: dict[int, str]) -> list[LogicIssue]:
        """检查投资逻辑一致性"""
        issues = []

        # 提取投资逻辑相关数据
        logic_data = self._extract_investment_logic(chapters)

        # 检查看多逻辑与看空逻辑是否平衡
        if "看多逻辑" in logic_data and "看空逻辑" in logic_data:
            bullish = logic_data["看多逻辑"]
            bearish = logic_data["看空逻辑"]

            # 如果看多逻辑明显强于看空逻辑，但评级是中性，可能有问题
            if len(bullish) > len(bearish) * 2:
                for ch_num, content in chapters.items():
                    if "看多" in content and "看空" in content:
                        line = self._find_line_number(content, "看多")
                        issues.append(LogicIssue(
                            issue_type="logic_gap",
                            severity="suggestion",
                            description=f"看多逻辑({len(bullish)}条)明显多于看空逻辑({len(bearish)}条)，但评级可能偏中性",
                            chapter=ch_num,
                            line=line,
                            content=f"看多{len(bullish)}条 vs 看空{len(bearish)}条",
                        ))
                        break

        return issues

    def _extract_valuation_data(self, chapters: dict[int, str]) -> dict:
        """提取估值相关数据"""
        data = {}

        for ch_num, content in chapters.items():
            # 提取情景分析
            for pattern in self.valuation_patterns["情景分析"]:
                match = re.search(pattern, content)
                if match:
                    if "情景分析" not in data:
                        data["情景分析"] = {}
                    if "基准" in pattern:
                        data["情景分析"]["基准"] = float(match.group(1))
                    elif "乐观" in pattern:
                        data["情景分析"]["乐观"] = float(match.group(1))
                    elif "悲观" in pattern:
                        data["情景分析"]["悲观"] = float(match.group(1))

            # 提取概率加权
            for pattern in self.valuation_patterns["概率加权"]:
                match = re.search(pattern, content)
                if match:
                    data["概率加权"] = {"概率加权": float(match.group(1))}

            # 提取上行空间
            for pattern in self.valuation_patterns["上行空间"]:
                match = re.search(pattern, content)
                if match:
                    data["上行空间"] = {"上行空间": float(match.group(1))}

            # 提取当前股价
            for pattern in self.valuation_patterns["当前股价"]:
                match = re.search(pattern, content)
                if match:
                    data["当前股价"] = {"当前股价": float(match.group(1))}

        return data

    def _extract_rating_data(self, chapters: dict[int, str]) -> dict:
        """提取评级相关数据"""
        data = {}

        for ch_num, content in chapters.items():
            # 提取评级
            for pattern in self.rating_patterns["评级"]:
                match = re.search(pattern, content)
                if match:
                    data["评级"] = match.group(1)
                    break

            # 提取估值判断
            for pattern in self.rating_patterns["估值判断"]:
                match = re.search(pattern, content)
                if match:
                    data["估值判断"] = match.group(0)
                    break

        return data

    def _extract_investment_logic(self, chapters: dict[int, str]) -> dict:
        """提取投资逻辑"""
        data = {}

        for ch_num, content in chapters.items():
            # 提取看多逻辑
            if "看多" in content:
                bullish_points = re.findall(r"看多.*?[。\n]", content)
                data["看多逻辑"] = bullish_points

            # 提取看空逻辑
            if "看空" in content:
                bearish_points = re.findall(r"看空.*?[。\n]", content)
                data["看空逻辑"] = bearish_points

        return data

    def _find_line_number(self, content: str, keyword: str) -> int:
        """查找关键词所在行号"""
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if keyword in line:
                return i + 1
        return 0


def check_logic_consistency(chapters: dict[int, str]) -> LogicResult:
    """
    检查逻辑一致性（入口函数）

    Args:
        chapters: 各章节内容 {chapter_num: content}

    Returns:
        LogicResult
    """
    checker = LogicConsistencyChecker()
    return checker.check(chapters)
