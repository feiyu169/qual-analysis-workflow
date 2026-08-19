"""
估值假设（共用参数层+假设审计）

功能：
1. 统一估值假设
2. 假设审计
3. 假设验证
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class AssumptionSource(Enum):
    """假设来源"""
    WIND = "wind"  # Wind数据
    ANNUAL_REPORT = "annual_report"  # 年报
    ANALYST = "analyst"  # 分析师估计
    DEFAULT = "default"  # 默认值
    CALCULATED = "calculated"  # 计算值


@dataclass
class AssumptionAudit:
    """假设审计"""
    name: str
    value: float
    source: AssumptionSource
    confidence: float  # 0-100
    justification: str
    last_verified: str  # ISO日期


@dataclass
class ValuationAssumptions:
    """
    估值假设（共用参数层）
    
    所有估值方法（DCF、情景分析等）必须使用同一套假设
    """
    
    # 营收假设
    base_revenue: float  # 基础营收（亿）
    revenue_growth_rates: List[float]  # 5年营收增速假设
    
    # 利润率假设
    ebit_margins: List[float]  # 5年EBIT利润率假设
    
    # 折现率假设
    wacc: float  # 加权平均资本成本
    terminal_growth: float  # 永续增长率
    
    # 其他假设
    tax_rate: float = 0.25  # 税率
    da_ratio: float = 0.03  # 折旧率
    capex_ratio: float = 0.04  # 资本开支率
    wc_ratio: float = 0.02  # 营运资金变动率
    
    # 情景分析假设
    scenario_weights: Dict[str, float] = field(default_factory=lambda: {
        "基准": 0.5,
        "乐观": 0.2,
        "悲观": 0.2,
        "高增长": 0.05,
        "利润率压缩": 0.05,
    })
    
    # 假设审计
    audits: Dict[str, AssumptionAudit] = field(default_factory=dict)
    
    def add_audit(self, name: str, value: float, source: AssumptionSource,
                  confidence: float, justification: str, last_verified: str = None):
        """添加假设审计"""
        if last_verified is None:
            last_verified = datetime.now().isoformat()
        
        self.audits[name] = AssumptionAudit(
            name=name,
            value=value,
            source=source,
            confidence=confidence,
            justification=justification,
            last_verified=last_verified,
        )
    
    def validate_audits(self) -> List[str]:
        """验证假设审计"""
        errors = []
        
        # 检查关键假设是否有审计
        required_audits = ["wacc", "terminal_growth", "base_revenue"]
        for name in required_audits:
            if name not in self.audits:
                errors.append(f"关键假设'{name}'缺少审计记录")
        
        # 检查假设置信度
        for name, audit in self.audits.items():
            if audit.confidence < 50:
                errors.append(f"假设'{name}'置信度过低: {audit.confidence}%")
        
        return errors
    
    def validate_values(self) -> List[str]:
        """验证假设值"""
        errors = []
        
        # 检查WACC
        if self.wacc < 0.03 or self.wacc > 0.25:
            errors.append(f"WACC {self.wacc} 超出合理范围 [0.03, 0.25]")
        
        # 检查永续增长率
        if self.terminal_growth < 0.01 or self.terminal_growth > 0.05:
            errors.append(f"永续增长率 {self.terminal_growth} 超出合理范围 [0.01, 0.05]")
        
        # 检查WACC > 永续增长率
        if self.wacc <= self.terminal_growth:
            errors.append(f"WACC ({self.wacc}) 必须大于永续增长率 ({self.terminal_growth})")
        
        # 检查税率
        if self.tax_rate < 0 or self.tax_rate > 0.5:
            errors.append(f"税率 {self.tax_rate} 超出合理范围 [0, 0.5]")
        
        # 检查营收增速
        for i, growth in enumerate(self.revenue_growth_rates):
            if growth < -0.5 or growth > 1.0:
                errors.append(f"第{i+1}年营收增速 {growth} 超出合理范围 [-0.5, 1.0]")
        
        # 检查EBIT利润率
        for i, margin in enumerate(self.ebit_margins):
            if margin < -0.5 or margin > 0.5:
                errors.append(f"第{i+1}年EBIT利润率 {margin} 超出合理范围 [-0.5, 0.5]")
        
        return errors
    
    def get_audit_report(self) -> str:
        """生成假设审计报告"""
        report = "# 假设审计报告\n\n"
        
        for name, audit in self.audits.items():
            report += f"## {name}\n"
            report += f"- 值: {audit.value}\n"
            report += f"- 来源: {audit.source.value}\n"
            report += f"- 置信度: {audit.confidence}%\n"
            report += f"- 依据: {audit.justification}\n"
            report += f"- 最后验证: {audit.last_verified}\n\n"
        
        return report


def create_default_assumptions(
    base_revenue: float,
    base_wacc: float = None,
    base_terminal_growth: float = 0.02,
) -> ValuationAssumptions:
    """
    创建默认假设
    
    Args:
        base_revenue: 基础营收（亿）
        base_wacc: 基础WACC（默认使用CAPM计算）
        base_terminal_growth: 基础永续增长率
    
    Returns:
        ValuationAssumptions
    """
    # 计算WACC
    if base_wacc is None:
        rf = 0.023  # 无风险利率
        beta = 1.2  # Beta系数
        erp = 0.055  # 股权风险溢价
        ke = rf + beta * erp  # 0.089
        kd = 0.05  # 债务成本
        tax_rate = 0.25
        d_ratio = 0.15  # 债务比例
        base_wacc = ke * (1 - d_ratio) + kd * (1 - tax_rate) * d_ratio
    
    # 计算EBIT利润率
    # 假设基础利润率为5%，逐年提升
    ebit_margins = [0.05, 0.055, 0.06, 0.065, 0.07]
    
    # 计算营收增速
    # 假设基础增速为5%，逐年递减
    revenue_growth_rates = [0.05, 0.04, 0.03, 0.02, 0.02]
    
    assumptions = ValuationAssumptions(
        base_revenue=base_revenue,
        revenue_growth_rates=revenue_growth_rates,
        ebit_margins=ebit_margins,
        wacc=base_wacc,
        terminal_growth=base_terminal_growth,
    )
    
    # 添加审计记录
    assumptions.add_audit(
        name="wacc",
        value=base_wacc,
        source=AssumptionSource.CALCULATED,
        confidence=80,
        justification="基于CAPM计算: Rf=2.3%, Beta=1.2, ERP=5.5%",
    )
    
    assumptions.add_audit(
        name="terminal_growth",
        value=base_terminal_growth,
        source=AssumptionSource.DEFAULT,
        confidence=70,
        justification="基于名义GDP增速假设",
    )
    
    assumptions.add_audit(
        name="base_revenue",
        value=base_revenue,
        source=AssumptionSource.WIND,
        confidence=90,
        justification="来自Wind财务数据",
    )
    
    return assumptions
