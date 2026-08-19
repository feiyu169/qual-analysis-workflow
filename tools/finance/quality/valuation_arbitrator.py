"""
估值仲裁模块

功能：
1. 比对不同估值方法的结果
2. 检查估值方法是否收敛
3. 提供估值仲裁建议

解决批判性审阅发现的问题：
- F4: 三套估值方法互不收敛
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ValuationMethod:
    """估值方法"""
    name: str  # 方法名称
    value_per_share: float  # 每股价值
    currency: str  # 币种
    probability: Optional[float] = None  # 概率权重


@dataclass
class ArbitrationIssue:
    """仲裁问题"""
    issue_type: str  # "non_convergence", "currency_mismatch", "weight_issue"
    severity: str  # "fatal", "important", "suggestion"
    description: str
    methods: List[str]


@dataclass
class ArbitrationResult:
    """仲裁结果"""
    passed: bool
    issues: List[ArbitrationIssue] = field(default_factory=list)
    score: float = 100.0
    recommended_value: Optional[float] = None  # 推荐的每股价值
    recommended_method: Optional[str] = None  # 推荐的方法


class ValuationArbitrator:
    """估值仲裁器"""
    
    def __init__(self):
        # 估值方法正则模式
        self.valuation_patterns = {
            "情景分析": [
                r"情景分析.*?基准.*?(\d+\.?\d*)\s*元",
                r"基准.*?(\d+\.?\d*)\s*元.*?概率.*?(\d+\.?\d*)\s*%",
            ],
            "PE估值": [
                r"P/E.*?(\d+\.?\d*)\s*倍.*?净利润.*?(\d+\.?\d*)\s*亿",
                r"(\d+\.?\d*)\s*倍.*?P/E.*?(\d+\.?\d*)\s*亿",
            ],
            "PB估值": [
                r"P/B.*?(\d+\.?\d*)\s*倍.*?净资产.*?(\d+\.?\d*)\s*亿",
            ],
            "PS估值": [
                r"P/S.*?(\d+\.?\d*)\s*倍.*?营收.*?(\d+\.?\d*)\s*亿",
            ],
            "DCF估值": [
                r"DCF.*?(\d+\.?\d*)\s*元",
                r"现金流折现.*?(\d+\.?\d*)\s*元",
            ],
            "概率加权": [
                r"概率加权.*?(\d+\.?\d*)\s*元",
                r"加权.*?(\d+\.?\d*)\s*元",
            ],
            "叙述结论": [
                r"上行.*?(\d+\.?\d*)\s*%",
                r"目标价.*?(\d+\.?\d*)\s*港元",
            ],
        }
        
        # 币种转换（港元兑人民币）
        self.hkd_to_cny = 0.92
    
    def check(
        self,
        chapters: Dict[int, str],
        current_price: Optional[float] = None,
        current_currency: str = "HKD",
    ) -> ArbitrationResult:
        """
        检查估值一致性
        
        Args:
            chapters: 各章节内容 {chapter_num: content}
            current_price: 当前股价
            current_currency: 当前股价币种
        
        Returns:
            ArbitrationResult
        """
        issues = []
        
        # 1. 提取所有估值方法
        methods = self._extract_valuation_methods(chapters)
        
        if not methods:
            return ArbitrationResult(
                passed=True,
                issues=[],
                score=100.0,
            )
        
        # 2. 统一币种
        unified_methods = self._unify_currency(methods)
        
        # 3. 检查估值是否收敛
        convergence_issues = self._check_convergence(unified_methods, current_price, current_currency)
        issues.extend(convergence_issues)
        
        # 4. 检查币种一致性
        currency_issues = self._check_currency_consistency(methods)
        issues.extend(currency_issues)
        
        # 5. 计算推荐估值
        recommended_value, recommended_method = self._calculate_recommendation(unified_methods)
        
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
            logger.warning(f"估值仲裁检查不通过: score={score:.0f}, issues={len(issues)}")
        
        return ArbitrationResult(
            passed=passed,
            issues=issues,
            score=score,
            recommended_value=recommended_value,
            recommended_method=recommended_method,
        )
    
    def _extract_valuation_methods(self, chapters: Dict[int, str]) -> List[ValuationMethod]:
        """提取所有估值方法"""
        methods = []
        
        for ch_num, content in chapters.items():
            # 提取情景分析
            for pattern in self.valuation_patterns["情景分析"]:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        value = float(match[0])
                        prob = float(match[1]) / 100 if len(match) > 1 else None
                    else:
                        value = float(match)
                        prob = None
                    
                    methods.append(ValuationMethod(
                        name=f"情景分析_基准",
                        value_per_share=value,
                        currency="CNY",
                        probability=prob,
                    ))
            
            # 提取概率加权
            for pattern in self.valuation_patterns["概率加权"]:
                match = re.search(pattern, content)
                if match:
                    methods.append(ValuationMethod(
                        name="概率加权",
                        value_per_share=float(match.group(1)),
                        currency="CNY",
                    ))
            
            # 提取PE估值
            for pattern in self.valuation_patterns["PE估值"]:
                match = re.search(pattern, content)
                if match:
                    pe_ratio = float(match.group(1))
                    net_income = float(match.group(2))
                    # 计算每股价值（假设总股本19.56亿股）
                    shares = 19.56
                    value = pe_ratio * net_income / shares
                    methods.append(ValuationMethod(
                        name="PE估值",
                        value_per_share=value,
                        currency="CNY",
                    ))
            
            # 提取叙述结论
            for pattern in self.valuation_patterns["叙述结论"]:
                match = re.search(pattern, content)
                if match:
                    if "上行" in pattern:
                        upside = float(match.group(1))
                        # 需要当前股价来计算目标价
                        # 暂时跳过
                    elif "目标价" in pattern:
                        methods.append(ValuationMethod(
                            name="目标价",
                            value_per_share=float(match.group(1)),
                            currency="HKD",
                        ))
        
        return methods
    
    def _unify_currency(self, methods: List[ValuationMethod]) -> List[ValuationMethod]:
        """统一币种为人民币"""
        unified = []
        
        for method in methods:
            if method.currency == "HKD":
                # 转换为人民币
                unified.append(ValuationMethod(
                    name=method.name,
                    value_per_share=method.value_per_share * self.hkd_to_cny,
                    currency="CNY",
                    probability=method.probability,
                ))
            else:
                unified.append(method)
        
        return unified
    
    def _check_convergence(
        self,
        methods: List[ValuationMethod],
        current_price: Optional[float],
        current_currency: str,
    ) -> List[ArbitrationIssue]:
        """检查估值是否收敛"""
        issues = []
        
        if len(methods) < 2:
            return issues
        
        # 提取所有估值值
        values = [m.value_per_share for m in methods]
        
        # 计算标准差和变异系数
        mean_value = sum(values) / len(values)
        variance = sum((v - mean_value) ** 2 for v in values) / len(values)
        std_dev = variance ** 0.5
        cv = std_dev / mean_value if mean_value > 0 else 0
        
        # 如果变异系数超过100%，报告问题
        if cv > 1.0:
            method_names = [m.name for m in methods]
            issues.append(ArbitrationIssue(
                issue_type="non_convergence",
                severity="fatal",
                description=f"估值方法不收敛：变异系数={cv*100:.1f}%，各方法估值差异过大",
                methods=method_names,
            ))
        
        # 检查基准值与概率加权值的差异
        base_values = [m for m in methods if "基准" in m.name]
        weighted_values = [m for m in methods if "加权" in m.name]
        
        if base_values and weighted_values:
            base_val = base_values[0].value_per_share
            weighted_val = weighted_values[0].value_per_share
            
            # 如果差距超过100%，报告问题
            if abs(weighted_val - base_val) / base_val > 1.0:
                issues.append(ArbitrationIssue(
                    issue_type="non_convergence",
                    severity="important",
                    description=f"基准估值{base_val:.1f}元与概率加权估值{weighted_val:.1f}元差距过大",
                    methods=["基准", "概率加权"],
                ))
        
        # 检查估值与当前股价的关系
        if current_price:
            # 统一当前股价币种
            if current_currency == "HKD":
                current_price_cny = current_price * self.hkd_to_cny
            else:
                current_price_cny = current_price
            
            # 检查基准估值与当前股价的差异
            for method in methods:
                ratio = method.value_per_share / current_price_cny
                
                # 如果估值低于当前股价50%以上，但叙述说"低估"，报告问题
                if ratio < 0.5:
                    issues.append(ArbitrationIssue(
                        issue_type="non_convergence",
                        severity="fatal",
                        description=f"{method.name}估值{method.value_per_share:.1f}元低于当前股价{current_price_cny:.1f}元{(1-ratio)*100:.1f}%，暗示高估",
                        methods=[method.name],
                    ))
        
        return issues
    
    def _check_currency_consistency(self, methods: List[ValuationMethod]) -> List[ArbitrationIssue]:
        """检查币种一致性"""
        issues = []
        
        # 检查是否有币种混用
        currencies = set(m.currency for m in methods)
        
        if len(currencies) > 1:
            method_names = [f"{m.name}({m.currency})" for m in methods]
            issues.append(ArbitrationIssue(
                issue_type="currency_mismatch",
                severity="important",
                description=f"估值方法币种不一致：{', '.join(method_names)}",
                methods=method_names,
            ))
        
        return issues
    
    def _calculate_recommendation(
        self,
        methods: List[ValuationMethod],
    ) -> Tuple[Optional[float], Optional[str]]:
        """计算推荐估值"""
        if not methods:
            return None, None
        
        # 如果有概率加权值，使用它
        weighted_methods = [m for m in methods if "加权" in m.name]
        if weighted_methods:
            return weighted_methods[0].value_per_share, "概率加权"
        
        # 否则使用所有方法的平均值
        values = [m.value_per_share for m in methods]
        mean_value = sum(values) / len(values)
        
        return mean_value, "多方法平均"


def check_valuation_arbitration(
    chapters: Dict[int, str],
    current_price: Optional[float] = None,
    current_currency: str = "HKD",
) -> ArbitrationResult:
    """
    检查估值仲裁（入口函数）
    
    Args:
        chapters: 各章节内容 {chapter_num: content}
        current_price: 当前股价
        current_currency: 当前股价币种
    
    Returns:
        ArbitrationResult
    """
    arbitrator = ValuationArbitrator()
    return arbitrator.check(chapters, current_price, current_currency)
