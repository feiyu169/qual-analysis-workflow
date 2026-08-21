"""
quality/templates/management_incentive.py — 管理层激励分析模板

定义管理层激励分析的标准模板：
- 薪酬结构分析
- KPI考核分析
- 股权激励分析
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CompensationStructure:
    """薪酬结构"""
    base_salary: float = 0.0          # 基本工资（万元）
    bonus: float = 0.0                # 奖金（万元）
    equity_incentive: float = 0.0     # 股权激励（万元）
    other_compensation: float = 0.0   # 其他薪酬（万元）
    total_compensation: float = 0.0   # 总薪酬（万元）
    
    @property
    def equity_ratio(self) -> float:
        """股权激励占比"""
        if self.total_compensation > 0:
            return self.equity_incentive / self.total_compensation
        return 0.0


@dataclass
class KPIMetrics:
    """KPI考核指标"""
    revenue_growth: Optional[float] = None      # 营收增长率目标
    profit_growth: Optional[float] = None       # 利润增长率目标
    roe_target: Optional[float] = None          # ROE目标
    market_share: Optional[float] = None        # 市场份额目标
    other_metrics: dict = field(default_factory=dict)  # 其他指标


@dataclass
class EquityIncentivePlan:
    """股权激励计划"""
    plan_name: str = ""                    # 计划名称
    plan_type: str = ""                    # 计划类型（期权/限制性股票/股票增值权）
    total_shares: float = 0.0              # 授予股份总数（万股）
    exercise_price: float = 0.0            # 行权价格（元）
    vesting_period: str = ""               # 归属期
    performance_conditions: list[str] = field(default_factory=list)  # 绩效条件
    expiration_date: str = ""              # 到期日


@dataclass
class ManagementIncentiveAnalysis:
    """管理层激励分析"""
    company_name: str
    ticker: str
    
    # 核心管理层
    ceo: str = ""
    cfo: str = ""
    chairman: str = ""
    
    # 薪酬结构
    compensation: CompensationStructure = field(default_factory=CompensationStructure)
    
    # KPI考核
    kpi: KPIMetrics = field(default_factory=KPIMetrics)
    
    # 股权激励计划
    equity_plans: list[EquityIncentivePlan] = field(default_factory=list)
    
    # 分析结论
    incentive_alignment: str = ""  # 激励一致性评估
    risk_factors: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def format_management_incentive_report(analysis: ManagementIncentiveAnalysis) -> str:
    """格式化管理层激励分析报告"""
    lines = []
    lines.append("## 管理层、治理与激励")
    lines.append("")
    
    # 核心管理层
    lines.append("### 核心管理层")
    lines.append(f"- CEO: {analysis.ceo}")
    lines.append(f"- CFO: {analysis.cfo}")
    lines.append(f"- 董事长: {analysis.chairman}")
    lines.append("")
    
    # 薪酬结构
    lines.append("### 薪酬结构")
    comp = analysis.compensation
    lines.append(f"- 基本工资: {comp.base_salary:.0f}万元")
    lines.append(f"- 奖金: {comp.bonus:.0f}万元")
    lines.append(f"- 股权激励: {comp.equity_incentive:.0f}万元")
    lines.append(f"- 其他薪酬: {comp.other_compensation:.0f}万元")
    lines.append(f"- 总薪酬: {comp.total_compensation:.0f}万元")
    lines.append(f"- 股权激励占比: {comp.equity_ratio:.1%}")
    lines.append("")
    
    # KPI考核
    lines.append("### KPI考核")
    kpi = analysis.kpi
    if kpi.revenue_growth is not None:
        lines.append(f"- 营收增长率目标: {kpi.revenue_growth:.1%}")
    if kpi.profit_growth is not None:
        lines.append(f"- 利润增长率目标: {kpi.profit_growth:.1%}")
    if kpi.roe_target is not None:
        lines.append(f"- ROE目标: {kpi.roe_target:.1%}")
    if kpi.market_share is not None:
        lines.append(f"- 市场份额目标: {kpi.market_share:.1%}")
    if kpi.other_metrics:
        for key, value in kpi.other_metrics.items():
            lines.append(f"- {key}: {value}")
    lines.append("")
    
    # 股权激励计划
    if analysis.equity_plans:
        lines.append("### 股权激励计划")
        for plan in analysis.equity_plans:
            lines.append(f"**{plan.plan_name}**")
            lines.append(f"- 类型: {plan.plan_type}")
            lines.append(f"- 授予股份: {plan.total_shares:.0f}万股")
            lines.append(f"- 行权价格: {plan.exercise_price:.2f}元")
            lines.append(f"- 归属期: {plan.vesting_period}")
            lines.append(f"- 到期日: {plan.expiration_date}")
            if plan.performance_conditions:
                lines.append("- 绩效条件:")
                for condition in plan.performance_conditions:
                    lines.append(f"  - {condition}")
            lines.append("")
    
    # 分析结论
    if analysis.incentive_alignment:
        lines.append("### 激励一致性评估")
        lines.append(analysis.incentive_alignment)
        lines.append("")
    
    if analysis.risk_factors:
        lines.append("### 风险因素")
        for risk in analysis.risk_factors:
            lines.append(f"- {risk}")
        lines.append("")
    
    if analysis.recommendations:
        lines.append("### 建议")
        for rec in analysis.recommendations:
            lines.append(f"- {rec}")
        lines.append("")
    
    return "\n".join(lines)
