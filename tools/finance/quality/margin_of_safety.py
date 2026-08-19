"""
quality/margin_of_safety.py — 安全边际分析模块

实现投资分析中的安全边际：
- 内在价值计算
- 安全边际评估
- 估值区间分析
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ValuationRange:
    """估值区间"""
    method: str                    # 估值方法
    low: float                     # 低估区间
    mid: float                     # 中位估值
    high: float                    # 高估区间
    confidence: float              # 置信度（0-1）


@dataclass
class SafetyMarginResult:
    """安全边际分析结果"""
    # 当前市场价格
    current_price: float           # 当前股价
    market_cap: float              # 当前市值
    
    # 内在价值
    intrinsic_value: float         # 内在价值（每股）
    intrinsic_value_range: ValuationRange  # 内在价值区间
    
    # 安全边际
    safety_margin: float           # 安全边际（%）
    safety_margin_level: str       # 安全边际等级（低/中/高）
    
    # 估值方法
    valuation_methods: list[ValuationRange] = field(default_factory=list)
    
    # 风险调整
    risk_adjusted_value: float = 0.0  # 风险调整后价值
    
    # 建议
    recommendations: list[str] = field(default_factory=list)


class MarginOfSafetyAnalyzer:
    """安全边际分析器"""
    
    def analyze(
        self,
        current_price: float,
        market_cap: float,
        intrinsic_value: float,
        intrinsic_value_range: Optional[ValuationRange] = None,
        valuation_methods: Optional[list[ValuationRange]] = None,
        risk_adjustment: float = 0.0
    ) -> SafetyMarginResult:
        """分析安全边际
        
        Args:
            current_price: 当前股价
            market_cap: 当前市值
            intrinsic_value: 内在价值（每股）
            intrinsic_value_range: 内在价值区间
            valuation_methods: 估值方法列表
            risk_adjustment: 风险调整系数（0-1，用于降低内在价值）
            
        Returns:
            SafetyMarginResult: 安全边际分析结果
        """
        # 计算安全边际
        if intrinsic_value > 0:
            safety_margin = (intrinsic_value - current_price) / intrinsic_value * 100
        else:
            safety_margin = 0.0
        
        # 安全边际等级
        if safety_margin > 50:
            safety_margin_level = "极高"
        elif safety_margin > 30:
            safety_margin_level = "高"
        elif safety_margin > 15:
            safety_margin_level = "中"
        elif safety_margin > 0:
            safety_margin_level = "低"
        else:
            safety_margin_level = "负（高估）"
        
        # 风险调整后价值
        risk_adjusted_value = intrinsic_value * (1 - risk_adjustment)
        
        # 如果没有提供估值区间，使用默认值
        if intrinsic_value_range is None:
            intrinsic_value_range = ValuationRange(
                method="DCF",
                low=intrinsic_value * 0.8,
                mid=intrinsic_value,
                high=intrinsic_value * 1.2,
                confidence=0.7
            )
        
        if valuation_methods is None:
            valuation_methods = []
        
        # 生成建议
        recommendations = self._generate_recommendations(
            current_price, intrinsic_value, safety_margin, safety_margin_level
        )
        
        return SafetyMarginResult(
            current_price=current_price,
            market_cap=market_cap,
            intrinsic_value=intrinsic_value,
            intrinsic_value_range=intrinsic_value_range,
            safety_margin=safety_margin,
            safety_margin_level=safety_margin_level,
            valuation_methods=valuation_methods,
            risk_adjusted_value=risk_adjusted_value,
            recommendations=recommendations
        )
    
    def _generate_recommendations(
        self,
        current_price: float,
        intrinsic_value: float,
        safety_margin: float,
        safety_margin_level: str
    ) -> list[str]:
        """生成投资建议"""
        recommendations = []
        
        if safety_margin > 50:
            recommendations.append("安全边际极高，强烈建议买入")
            recommendations.append("当前价格大幅低于内在价值，具备极高的投资价值")
        elif safety_margin > 30:
            recommendations.append("安全边际较高，建议买入")
            recommendations.append("当前价格明显低于内在价值，具备较高的投资价值")
        elif safety_margin > 15:
            recommendations.append("安全边际中等，建议关注")
            recommendations.append("当前价格略低于内在价值，具备一定的投资价值")
        elif safety_margin > 0:
            recommendations.append("安全边际较低，建议谨慎")
            recommendations.append("当前价格接近内在价值，投资价值有限")
        else:
            recommendations.append("安全边际为负，当前价格高于内在价值")
            recommendations.append("建议等待价格回调至合理区间再考虑买入")
        
        return recommendations


def format_safety_margin_report(result: SafetyMarginResult) -> str:
    """格式化安全边际分析报告"""
    lines = []
    lines.append("## 安全边际分析")
    lines.append("")
    
    # 估值概览
    lines.append("### 估值概览")
    lines.append(f"- 当前股价: {result.current_price:.2f}元")
    lines.append(f"- 当前市值: {result.market_cap:.2f}亿元")
    lines.append(f"- 内在价值: {result.intrinsic_value:.2f}元")
    lines.append(f"- 内在价值区间: {result.intrinsic_value_range.low:.2f} - {result.intrinsic_value_range.high:.2f}元")
    lines.append("")
    
    # 安全边际
    lines.append("### 安全边际")
    lines.append(f"- 安全边际: {result.safety_margin:.1f}%")
    lines.append(f"- 安全边际等级: {result.safety_margin_level}")
    lines.append(f"- 风险调整后价值: {result.risk_adjusted_value:.2f}元")
    lines.append("")
    
    # 估值方法
    if result.valuation_methods:
        lines.append("### 估值方法")
        lines.append("| 方法 | 低估 | 中位 | 高估 | 置信度 |")
        lines.append("|---|---|---|---|---|")
        for method in result.valuation_methods:
            lines.append(f"| {method.method} | {method.low:.2f} | {method.mid:.2f} | {method.high:.2f} | {method.confidence:.1%} |")
        lines.append("")
    
    # 建议
    if result.recommendations:
        lines.append("### 投资建议")
        for rec in result.recommendations:
            lines.append(f"- {rec}")
        lines.append("")
    
    return "\n".join(lines)
