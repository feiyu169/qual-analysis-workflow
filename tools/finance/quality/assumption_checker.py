"""
假设合理性审查模块

功能：
1. 检查估值假设是否合理（WACC、永续增长率等）
2. 检查增长假设是否与行业一致
3. 检查利润率假设是否合理
4. 检查假设是否有数据支撑

审查原则：不降低买方报告分析的专业性和质量
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class AssumptionIssue:
    """假设合理性问题"""
    issue_type: str  # "out_of_range", "inconsistent", "unsupported"
    severity: str  # "fatal", "important", "suggestion"
    description: str
    field_name: str
    actual_value: float
    expected_range: tuple
    chapter: int
    line: int


@dataclass
class AssumptionCheckResult:
    """假设合理性审查结果"""
    passed: bool
    issues: List[AssumptionIssue] = field(default_factory=list)
    score: float = 100.0
    extracted_assumptions: Dict[str, float] = field(default_factory=dict)


class AssumptionChecker:
    """假设合理性审查器"""
    
    def __init__(self):
        # 估值假设合理范围
        self.valuation_ranges = {
            "WACC": {
                "patterns": [
                    r"WACC.*?(\d+\.?\d*)\s*%",
                    r"加权.*?资本.*?成本.*?(\d+\.?\d*)\s*%",
                ],
                "min": 0.05,  # 5%
                "max": 0.15,  # 15%
                "typical": 0.08,  # 8%
            },
            "永续增长率": {
                "patterns": [
                    r"永续.*?增长.*?(\d+\.?\d*)\s*%",
                    r"终值.*?增长.*?(\d+\.?\d*)\s*%",
                    r"terminal.*?growth.*?(\d+\.?\d*)\s*%",
                ],
                "min": 0.01,  # 1%
                "max": 0.05,  # 5%
                "typical": 0.02,  # 2%
            },
            "EBIT利润率": {
                "patterns": [
                    r"EBIT.*?利润.*?率.*?(\d+\.?\d*)\s*%",
                    r"营业.*?利润.*?率.*?(\d+\.?\d*)\s*%",
                ],
                "min": -0.50,  # -50%
                "max": 0.30,  # 30%
                "typical": 0.10,  # 10%
            },
            "营收增长率": {
                "patterns": [
                    r"营收.*?增长.*?(\d+\.?\d*)\s*%",
                    r"收入.*?增长.*?(\d+\.?\d*)\s*%",
                ],
                "min": -0.30,  # -30%
                "max": 1.00,  # 100%
                "typical": 0.15,  # 15%
            },
            "税率": {
                "patterns": [
                    r"税率.*?(\d+\.?\d*)\s*%",
                    r"所得税.*?率.*?(\d+\.?\d*)\s*%",
                ],
                "min": 0.10,  # 10%
                "max": 0.35,  # 35%
                "typical": 0.25,  # 25%
            },
        }
        
        # 行业平均值（用于对比）
        self.industry_averages = {
            "新能源汽车": {
                "WACC": 0.10,
                "永续增长率": 0.02,
                "EBIT利润率": 0.05,
                "营收增长率": 0.20,
                "税率": 0.15,
            },
            "科技": {
                "WACC": 0.12,
                "永续增长率": 0.03,
                "EBIT利润率": 0.15,
                "营收增长率": 0.25,
                "税率": 0.15,
            },
            "消费": {
                "WACC": 0.09,
                "永续增长率": 0.02,
                "EBIT利润率": 0.10,
                "营收增长率": 0.10,
                "税率": 0.25,
            },
        }
    
    def check(
        self,
        chapters: Dict[int, str],
        industry: Optional[str] = None,
        wind_data: Optional[Dict[str, Any]] = None,
    ) -> AssumptionCheckResult:
        """
        执行假设合理性审查
        
        Args:
            chapters: 各章节内容 {chapter_num: content}
            industry: 行业类型（用于对比）
            wind_data: Wind数据（用于验证）
        
        Returns:
        AssumptionCheckResult
        """
        issues = []
        extracted_assumptions = {}
        
        # 1. 提取估值假设
        for ch_num, content in chapters.items():
            assumptions = self._extract_assumptions(content, ch_num)
            extracted_assumptions.update(assumptions)
        
        # 2. 检查每个假设是否在合理范围内
        for field_name, value in extracted_assumptions.items():
            if field_name in self.valuation_ranges:
                range_config = self.valuation_ranges[field_name]
                min_val = range_config["min"]
                max_val = range_config["max"]
                
                if value < min_val or value > max_val:
                    # 判断严重程度
                    if field_name in ["WACC", "永续增长率"]:
                        severity = "fatal"  # 这些参数对估值影响大
                    else:
                        severity = "important"
                    
                    # 找到相关章节和行号
                    for ch_num, content in chapters.items():
                        for pattern in range_config["patterns"]:
                            if re.search(pattern, content):
                                line = self._find_line_number(content, field_name)
                                issues.append(AssumptionIssue(
                                    issue_type="out_of_range",
                                    severity=severity,
                                    description=f"{field_name}={value*100:.1f}%超出合理范围[{min_val*100:.1f}%, {max_val*100:.1f}%]",
                                    field_name=field_name,
                                    actual_value=value,
                                    expected_range=(min_val, max_val),
                                    chapter=ch_num,
                                    line=line,
                                ))
                                break
        
        # 3. 与行业平均值对比
        if industry and industry in self.industry_averages:
            industry_avg = self.industry_averages[industry]
            
            for field_name, value in extracted_assumptions.items():
                if field_name in industry_avg:
                    industry_value = industry_avg[field_name]
                    
                    # 如果偏差超过50%，报告问题
                    if industry_value != 0:
                        deviation = abs(value - industry_value) / abs(industry_value)
                        if deviation > 0.50:
                            for ch_num, content in chapters.items():
                                for pattern in self.valuation_ranges.get(field_name, {}).get("patterns", []):
                                    if re.search(pattern, content):
                                        line = self._find_line_number(content, field_name)
                                        issues.append(AssumptionIssue(
                                            issue_type="inconsistent",
                                            severity="suggestion",
                                            description=f"{field_name}={value*100:.1f}%与行业平均{industry_value*100:.1f}%偏差{deviation*100:.1f}%",
                                            field_name=field_name,
                                            actual_value=value,
                                            expected_range=(industry_value * 0.5, industry_value * 1.5),
                                            chapter=ch_num,
                                            line=line,
                                        ))
                                        break
        
        # 4. 检查假设是否有数据支撑
        unsupported_issues = self._check_assumption_support(chapters, extracted_assumptions)
        issues.extend(unsupported_issues)
        
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
            logger.warning(f"假设合理性审查不通过: score={score:.0f}, issues={len(issues)}")
        
        return AssumptionCheckResult(
            passed=passed,
            issues=issues,
            score=score,
            extracted_assumptions=extracted_assumptions,
        )
    
    def _extract_assumptions(self, content: str, ch_num: int) -> Dict[str, float]:
        """从内容中提取估值假设"""
        assumptions = {}
        
        for field_name, config in self.valuation_ranges.items():
            for pattern in config["patterns"]:
                match = re.search(pattern, content)
                if match:
                    try:
                        value = float(match.group(1)) / 100  # 转换为小数
                        assumptions[field_name] = value
                        break
                    except ValueError:
                        continue
        
        return assumptions
    
    def _check_assumption_support(
        self,
        chapters: Dict[int, str],
        assumptions: Dict[str, float],
    ) -> List[AssumptionIssue]:
        """检查假设是否有数据支撑"""
        issues = []
        
        # 检查是否有支撑关键词
        support_keywords = ["来源", "依据", "根据", "基于", "参考", "Wind", "年报"]
        
        for field_name, value in assumptions.items():
            has_support = False
            
            for ch_num, content in chapters.items():
                # 检查假设附近是否有支撑说明
                for pattern in self.valuation_ranges.get(field_name, {}).get("patterns", []):
                    match = re.search(pattern, content)
                    if match:
                        # 获取假设周围的上下文
                        start = max(0, match.start() - 200)
                        end = min(len(content), match.end() + 200)
                        context = content[start:end]
                        
                        # 检查是否有支撑关键词
                        for keyword in support_keywords:
                            if keyword in context:
                                has_support = True
                                break
                
                if has_support:
                    break
            
            if not has_support and field_name in ["WACC", "永续增长率"]:
                # 这些关键假设必须有支撑
                for ch_num, content in chapters.items():
                    for pattern in self.valuation_ranges.get(field_name, {}).get("patterns", []):
                        if re.search(pattern, content):
                            line = self._find_line_number(content, field_name)
                            issues.append(AssumptionIssue(
                                issue_type="unsupported",
                                severity="suggestion",
                                description=f"{field_name}={value*100:.1f}%缺少数据支撑说明",
                                field_name=field_name,
                                actual_value=value,
                                expected_range=(0, 0),
                                chapter=ch_num,
                                line=line,
                            ))
                            break
        
        return issues
    
    def _find_line_number(self, content: str, keyword: str) -> int:
        """查找关键词所在行号"""
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if keyword in line:
                return i + 1
        return 0


def check_assumptions(
    chapters: Dict[int, str],
    industry: Optional[str] = None,
    wind_data: Optional[Dict[str, Any]] = None,
) -> AssumptionCheckResult:
    """
    假设合理性审查（入口函数）
    
    Args:
        chapters: 各章节内容 {chapter_num: content}
        industry: 行业类型
        wind_data: Wind数据
    
    Returns:
        AssumptionCheckResult
    """
    checker = AssumptionChecker()
    return checker.check(chapters, industry, wind_data)
