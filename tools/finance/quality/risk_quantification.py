"""
quality/risk_quantification.py — 风险量化分析模块

实现投资分析中的风险量化：
- 风险识别
- 风险概率评估
- 风险影响量化
- 压力测试
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskFactor:
    """风险因素"""
    name: str                    # 风险名称
    description: str             # 风险描述
    category: str                # 风险类别（市场/行业/公司/财务/运营）
    probability: float           # 发生概率（0-1）
    impact: float                # 影响程度（0-1）
    impact_value: float = 0.0    # 影响金额（亿元）
    mitigation: str = ""         # 缓解措施
    monitoring_indicators: list[str] = field(default_factory=list)  # 监控指标


@dataclass
class RiskAssessment:
    """风险评估结果"""
    risk_factors: list[RiskFactor]
    total_risk_score: float      # 总风险得分（0-1）
    risk_level: str              # 风险等级（低/中/高/极高）
    expected_loss: float         # 期望损失（亿元）
    worst_case_loss: float       # 最坏情况损失（亿元）
    var_95: float                # 95% VaR（亿元）
    recommendations: list[str] = field(default_factory=list)


@dataclass
class StressTestScenario:
    """压力测试情景"""
    name: str                    # 情景名称
    description: str             # 情景描述
    probability: float           # 发生概率
    variables: dict[str, float]  # 变量变化
    impact: float                # 影响金额（亿元）


@dataclass
class StressTestResult:
    """压力测试结果"""
    scenarios: list[StressTestScenario]
    worst_case_loss: float       # 最坏情况损失
    worst_case_scenario: str     # 最坏情况情景
    expected_loss: float         # 期望损失
    recommendations: list[str] = field(default_factory=list)


class RiskQuantifier:
    """风险量化器"""
    
    def assess_risks(
        self,
        risk_factors: list[RiskFactor],
        base_value: float = 0.0
    ) -> RiskAssessment:
        """评估风险
        
        Args:
            risk_factors: 风险因素列表
            base_value: 基准价值（用于计算损失）
            
        Returns:
            RiskAssessment: 风险评估结果
        """
        if not risk_factors:
            return RiskAssessment(
                risk_factors=[],
                total_risk_score=0.0,
                risk_level="低",
                expected_loss=0.0,
                worst_case_loss=0.0,
                var_95=0.0
            )
        
        # 计算每个风险的风险得分
        risk_scores = []
        expected_losses = []
        worst_case_losses = []
        
        for risk in risk_factors:
            # 风险得分 = 概率 × 影响
            risk_score = risk.probability * risk.impact
            risk_scores.append(risk_score)
            
            # 期望损失 = 概率 × 影响金额
            expected_loss = risk.probability * risk.impact_value
            expected_losses.append(expected_loss)
            
            # 最坏情况损失 = 影响金额（假设发生）
            worst_case_losses.append(risk.impact_value)
        
        # 总风险得分（平均）
        total_risk_score = sum(risk_scores) / len(risk_scores)
        
        # 风险等级
        if total_risk_score < 0.2:
            risk_level = "低"
        elif total_risk_score < 0.4:
            risk_level = "中"
        elif total_risk_score < 0.6:
            risk_level = "高"
        else:
            risk_level = "极高"
        
        # 期望损失
        expected_loss = sum(expected_losses)
        
        # 最坏情况损失
        worst_case_loss = sum(worst_case_losses)
        
        # 95% VaR（简化计算：使用最坏情况的95%）
        var_95 = worst_case_loss * 0.95
        
        # 生成建议
        recommendations = self._generate_recommendations(
            risk_factors, total_risk_score, risk_level
        )
        
        return RiskAssessment(
            risk_factors=risk_factors,
            total_risk_score=total_risk_score,
            risk_level=risk_level,
            expected_loss=expected_loss,
            worst_case_loss=worst_case_loss,
            var_95=var_95,
            recommendations=recommendations
        )
    
    def stress_test(
        self,
        scenarios: list[StressTestScenario],
        base_value: float = 0.0
    ) -> StressTestResult:
        """压力测试
        
        Args:
            scenarios: 压力测试情景
            base_value: 基准价值
            
        Returns:
            StressTestResult: 压力测试结果
        """
        if not scenarios:
            return StressTestResult(
                scenarios=[],
                worst_case_loss=0.0,
                worst_case_scenario="",
                expected_loss=0.0
            )
        
        # 找出最坏情况
        worst_case = max(scenarios, key=lambda s: s.impact)
        
        # 计算期望损失
        expected_loss = sum(
            s.probability * s.impact for s in scenarios
        )
        
        # 生成建议
        recommendations = []
        if worst_case.impact > base_value * 0.2:
            recommendations.append(f"最坏情况损失({worst_case.impact:.2f}亿)超过基准价值的20%，需要制定应对预案")
        
        if expected_loss > base_value * 0.1:
            recommendations.append(f"期望损失({expected_loss:.2f}亿)超过基准价值的10%，需要加强风险管理")
        
        return StressTestResult(
            scenarios=scenarios,
            worst_case_loss=worst_case.impact,
            worst_case_scenario=worst_case.name,
            expected_loss=expected_loss,
            recommendations=recommendations
        )
    
    def _generate_recommendations(
        self,
        risk_factors: list[RiskFactor],
        total_risk_score: float,
        risk_level: str
    ) -> list[str]:
        """生成风险管理建议"""
        recommendations = []
        
        # 基于风险等级的建议
        if risk_level == "极高":
            recommendations.append("风险等级极高，建议暂停投资或大幅减仓")
        elif risk_level == "高":
            recommendations.append("风险等级高，建议减仓或设置严格止损")
        elif risk_level == "中":
            recommendations.append("风险等级中等，建议密切关注风险指标变化")
        
        # 基于具体风险的建议
        for risk in risk_factors:
            if risk.probability > 0.5 and risk.impact > 0.5:
                recommendations.append(f"高概率高影响风险：{risk.name}，建议制定专项应对方案")
        
        return recommendations


def format_risk_report(assessment: RiskAssessment) -> str:
    """格式化风险评估报告"""
    lines = []
    lines.append("## 风险量化分析")
    lines.append("")
    
    # 风险概览
    lines.append("### 风险概览")
    lines.append(f"- 总风险得分: {assessment.total_risk_score:.2f}")
    lines.append(f"- 风险等级: {assessment.risk_level}")
    lines.append(f"- 期望损失: {assessment.expected_loss:.2f}亿元")
    lines.append(f"- 最坏情况损失: {assessment.worst_case_loss:.2f}亿元")
    lines.append(f"- 95% VaR: {assessment.var_95:.2f}亿元")
    lines.append("")
    
    # 风险因素
    if assessment.risk_factors:
        lines.append("### 风险因素")
        lines.append("| 风险 | 类别 | 概率 | 影响 | 影响金额 | 缓解措施 |")
        lines.append("|---|---|---|---|---|---|")
        for risk in assessment.risk_factors:
            lines.append(f"| {risk.name} | {risk.category} | {risk.probability:.1%} | {risk.impact:.1%} | {risk.impact_value:.2f}亿 | {risk.mitigation} |")
        lines.append("")
    
    # 建议
    if assessment.recommendations:
        lines.append("### 风险管理建议")
        for rec in assessment.recommendations:
            lines.append(f"- {rec}")
        lines.append("")
    
    return "\n".join(lines)


def format_stress_test_report(result: StressTestResult) -> str:
    """格式化压力测试报告"""
    lines = []
    lines.append("### 压力测试")
    lines.append("")
    lines.append(f"- 最坏情况损失: {result.worst_case_loss:.2f}亿元")
    lines.append(f"- 最坏情况情景: {result.worst_case_scenario}")
    lines.append(f"- 期望损失: {result.expected_loss:.2f}亿元")
    lines.append("")
    
    if result.scenarios:
        lines.append("| 情景 | 描述 | 概率 | 影响 |")
        lines.append("|---|---|---|---|")
        for scenario in result.scenarios:
            lines.append(f"| {scenario.name} | {scenario.description} | {scenario.probability:.1%} | {scenario.impact:.2f}亿 |")
        lines.append("")
    
    if result.recommendations:
        lines.append("### 压力测试建议")
        for rec in result.recommendations:
            lines.append(f"- {rec}")
        lines.append("")
    
    return "\n".join(lines)
