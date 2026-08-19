"""
数据合理性验证模块

功能：
1. 验证财务数据是否在合理范围
2. 验证估值参数是否合理
3. 验证计算结果是否合理

解决批判性审阅发现的问题：
- F3: 翻转阈值营收为虚构数
- I2: WACC口径不一致
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ReasonablenessIssue:
    """数据合理性问题"""
    issue_type: str  # "out_of_range", "implausible", "inconsistent_unit"
    severity: str  # "fatal", "important", "suggestion"
    description: str
    field_name: str
    actual_value: float
    expected_range: Tuple[float, float]
    chapter: int
    line: int


@dataclass
class ReasonablenessResult:
    """数据合理性检查结果"""
    passed: bool
    issues: List[ReasonablenessIssue] = field(default_factory=list)
    score: float = 100.0


class DataReasonablenessChecker:
    """数据合理性检查器"""
    
    def __init__(self):
        # 财务数据合理范围（基于行业特征）
        self.financial_ranges = {
            # 营收增长率（年度）
            "营收增长率": (-0.5, 2.0),  # -50% 到 200%
            
            # 毛利率
            "毛利率": (-0.5, 0.8),  # -50% 到 80%
            
            # 净利率
            "净利率": (-1.0, 0.5),  # -100% 到 50%
            
            # 资产负债率
            "资产负债率": (0.0, 1.0),  # 0% 到 100%
            
            # WACC
            "WACC": (0.03, 0.25),  # 3% 到 25%
            
            # 永续增长率
            "永续增长率": (0.0, 0.05),  # 0% 到 5%
            
            # PE倍数
            "PE": (0.0, 100.0),  # 0 到 100
            
            # PB倍数
            "PB": (0.0, 20.0),  # 0 到 20
            
            # PS倍数
            "PS": (0.0, 30.0),  # 0 到 30
        }
        
        # 估值参数合理范围
        self.valuation_ranges = {
            # 营收基数（亿元）- 应该在实际营收的0.5-2倍范围内
            "营收基数_ratio": (0.5, 2.0),
            
            # EBIT利润率
            "EBIT利润率": (-0.5, 0.3),  # -50% 到 30%
            
            # 翻转阈值（应该是实际值的0.5-5倍范围内）
            "翻转阈值_ratio": (0.5, 5.0),
        }
    
    def check(
        self,
        chapters: Dict[int, str],
        actual_financials: Optional[Dict[str, float]] = None,
    ) -> ReasonablenessResult:
        """
        检查数据合理性
        
        Args:
            chapters: 各章节内容 {chapter_num: content}
            actual_financials: 实际财务数据（用于比对）
        
        Returns:
            ReasonablenessResult
        """
        issues = []
        
        # 1. 检查财务数据范围
        financial_issues = self._check_financial_ranges(chapters)
        issues.extend(financial_issues)
        
        # 2. 检查估值参数合理性
        valuation_issues = self._check_valuation_parameters(chapters, actual_financials)
        issues.extend(valuation_issues)
        
        # 3. 检查计算结果合理性
        calculation_issues = self._check_calculation_results(chapters, actual_financials)
        issues.extend(calculation_issues)
        
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
            logger.warning(f"数据合理性检查不通过: score={score:.0f}, issues={len(issues)}")
        
        return ReasonablenessResult(
            passed=passed,
            issues=issues,
            score=score,
        )
    
    def _check_financial_ranges(self, chapters: Dict[int, str]) -> List[ReasonablenessIssue]:
        """检查财务数据范围"""
        issues = []
        
        for ch_num, content in chapters.items():
            # 提取财务数据
            financial_data = self._extract_financial_data(content)
            
            # 检查每个数据是否在合理范围内
            for field_name, value in financial_data.items():
                if field_name in self.financial_ranges:
                    min_val, max_val = self.financial_ranges[field_name]
                    
                    if value < min_val or value > max_val:
                        # 判断严重程度
                        if field_name in ["WACC", "永续增长率"]:
                            severity = "fatal"  # 这些参数对估值影响大
                        elif field_name in ["毛利率", "净利率"]:
                            severity = "important"
                        else:
                            severity = "suggestion"
                        
                        line = self._find_line_number(content, field_name)
                        issues.append(ReasonablenessIssue(
                            issue_type="out_of_range",
                            severity=severity,
                            description=f"{field_name}={value}超出合理范围[{min_val}, {max_val}]",
                            field_name=field_name,
                            actual_value=value,
                            expected_range=(min_val, max_val),
                            chapter=ch_num,
                            line=line,
                        ))
        
        return issues
    
    def _check_valuation_parameters(
        self,
        chapters: Dict[int, str],
        actual_financials: Optional[Dict[str, float]] = None,
    ) -> List[ReasonablenessIssue]:
        """检查估值参数合理性"""
        issues = []
        
        if not actual_financials:
            return issues
        
        # 提取实际营收
        actual_revenue = actual_financials.get("营业收入", 0)
        if actual_revenue <= 0:
            return issues
        
        for ch_num, content in chapters.items():
            # 提取估值参数
            valuation_data = self._extract_valuation_data(content)
            
            # 检查营收基数是否合理
            if "营收基数" in valuation_data:
                base_revenue = valuation_data["营收基数"]
                ratio = base_revenue / actual_revenue
                
                min_ratio, max_ratio = self.valuation_ranges["营收基数_ratio"]
                
                if ratio < min_ratio or ratio > max_ratio:
                    line = self._find_line_number(content, "营收")
                    issues.append(ReasonablenessIssue(
                        issue_type="implausible",
                        severity="fatal",
                        description=f"估值使用的营收基数{base_revenue}亿是实际营收{actual_revenue}亿的{ratio:.1f}倍，超出合理范围[{min_ratio}, {max_ratio}]",
                        field_name="营收基数",
                        actual_value=base_revenue,
                        expected_range=(actual_revenue * min_ratio, actual_revenue * max_ratio),
                        chapter=ch_num,
                        line=line,
                    ))
            
            # 检查EBIT利润率是否合理
            if "EBIT利润率" in valuation_data:
                ebit_margin = valuation_data["EBIT利润率"]
                min_val, max_val = self.valuation_ranges["EBIT利润率"]
                
                if ebit_margin < min_val or ebit_margin > max_val:
                    line = self._find_line_number(content, "EBIT")
                    issues.append(ReasonablenessIssue(
                        issue_type="out_of_range",
                        severity="important",
                        description=f"EBIT利润率={ebit_margin*100:.1f}%超出合理范围[{min_val*100:.1f}%, {max_val*100:.1f}%]",
                        field_name="EBIT利润率",
                        actual_value=ebit_margin,
                        expected_range=(min_val, max_val),
                        chapter=ch_num,
                        line=line,
                    ))
        
        return issues
    
    def _check_calculation_results(
        self,
        chapters: Dict[int, str],
        actual_financials: Optional[Dict[str, float]] = None,
    ) -> List[ReasonablenessIssue]:
        """检查计算结果合理性"""
        issues = []
        
        if not actual_financials:
            return issues
        
        actual_revenue = actual_financials.get("营业收入", 0)
        if actual_revenue <= 0:
            return issues
        
        for ch_num, content in chapters.items():
            # 提取翻转阈值
            flip_thresholds = self._extract_flip_thresholds(content)
            
            # 检查翻转阈值是否合理
            if "营收翻转点" in flip_thresholds:
                flip_value = flip_thresholds["营收翻转点"]
                ratio = flip_value / actual_revenue
                
                min_ratio, max_ratio = self.valuation_ranges["翻转阈值_ratio"]
                
                if ratio < min_ratio or ratio > max_ratio:
                    line = self._find_line_number(content, "翻转点")
                    issues.append(ReasonablenessIssue(
                        issue_type="implausible",
                        severity="fatal",
                        description=f"营收翻转点{flip_value}亿是实际营收{actual_revenue}亿的{ratio:.1f}倍，超出合理范围[{min_ratio}, {max_ratio}]",
                        field_name="营收翻转点",
                        actual_value=flip_value,
                        expected_range=(actual_revenue * min_ratio, actual_revenue * max_ratio),
                        chapter=ch_num,
                        line=line,
                    ))
        
        return issues
    
    def _extract_financial_data(self, content: str) -> Dict[str, float]:
        """从章节内容中提取财务数据"""
        data = {}
        
        # 营收增长率
        growth_pattern = r"增长.*?(\d+\.?\d*)\s*%"
        matches = re.findall(growth_pattern, content)
        if matches:
            try:
                data["营收增长率"] = float(matches[0]) / 100
            except ValueError:
                pass
        
        # 毛利率
        margin_pattern = r"毛利率.*?(\d+\.?\d*)\s*%"
        matches = re.findall(margin_pattern, content)
        if matches:
            try:
                data["毛利率"] = float(matches[0]) / 100
            except ValueError:
                pass
        
        # 净利率
        net_margin_pattern = r"净利率.*?(-?\d+\.?\d*)\s*%"
        matches = re.findall(net_margin_pattern, content)
        if matches:
            try:
                data["净利率"] = float(matches[0]) / 100
            except ValueError:
                pass
        
        # WACC
        wacc_pattern = r"WACC.*?(\d+\.?\d*)\s*%"
        matches = re.findall(wacc_pattern, content)
        if matches:
            try:
                data["WACC"] = float(matches[0]) / 100
            except ValueError:
                pass
        
        return data
    
    def _extract_valuation_data(self, content: str) -> Dict[str, float]:
        """从章节内容中提取估值参数"""
        data = {}
        
        # 营收基数
        revenue_pattern = r"营收.*?(\d+\.?\d*)\s*亿"
        matches = re.findall(revenue_pattern, content)
        if matches:
            try:
                data["营收基数"] = float(matches[0])
            except ValueError:
                pass
        
        # EBIT利润率
        ebit_pattern = r"EBIT.*?利润率.*?(\d+\.?\d*)\s*%"
        matches = re.findall(ebit_pattern, content)
        if matches:
            try:
                data["EBIT利润率"] = float(matches[0]) / 100
            except ValueError:
                pass
        
        return data
    
    def _extract_flip_thresholds(self, content: str) -> Dict[str, float]:
        """从章节内容中提取翻转阈值"""
        data = {}
        
        # 营收翻转点
        flip_pattern = r"营收.*?翻转点.*?(\d+\.?\d*)\s*亿"
        matches = re.findall(flip_pattern, content)
        if matches:
            try:
                data["营收翻转点"] = float(matches[0])
            except ValueError:
                pass
        
        return data
    
    def _find_line_number(self, content: str, keyword: str) -> int:
        """查找关键词所在行号"""
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if keyword in line:
                return i + 1
        return 0


def check_data_reasonableness(
    chapters: Dict[int, str],
    actual_financials: Optional[Dict[str, float]] = None,
) -> ReasonablenessResult:
    """
    检查数据合理性（入口函数）
    
    Args:
        chapters: 各章节内容 {chapter_num: content}
        actual_financials: 实际财务数据（用于比对）
    
    Returns:
        ReasonablenessResult
    """
    checker = DataReasonablenessChecker()
    return checker.check(chapters, actual_financials)
