"""
FCFCalculator模块

功能:
- 三层定义: FCFF/FCFE/LFCF
- 一致性检查: FCF/NI比值, FCF/OCF比值
- 验证规则: 6条

解决: S07 FCF定义缺专业深度
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FCFConfig:
    """FCF配置"""
    definition: str = "FCFF"  # FCFF | FCFE | LFCF
    
    # FCFF配置
    fcff_formula: str = "EBIT×(1-T) + D&A - CapEx - ΔWC"
    tax_type: str = "effective"  # effective | marginal | normalized
    capex_type: str = "total"  # maintenance_only | total
    
    # 一致性检查阈值
    fcf_ni_ratio_range: tuple = (0.3, 3.0)
    fcf_ocf_ratio_min: float = 0.5
    negative_fcf_years_max: int = 2


@dataclass
class FCFFResult:
    """企业自由现金流结果"""
    method: str = "FCFF"
    ebit: float = 0.0
    tax_rate: float = 0.0
    nopat: float = 0.0
    depreciation: float = 0.0
    capex: float = 0.0
    working_capital_change: float = 0.0
    fcf: float = 0.0
    formula: str = ""


@dataclass
class FCFEResult:
    """股权自由现金流结果"""
    method: str = "FCFE"
    net_income: float = 0.0
    depreciation: float = 0.0
    capex: float = 0.0
    working_capital_change: float = 0.0
    net_borrowing: float = 0.0
    fcf: float = 0.0
    formula: str = ""


@dataclass
class LFCFResult:
    """简化自由现金流结果"""
    method: str = "LFCF"
    operating_cashflow: float = 0.0
    capex: float = 0.0
    fcf: float = 0.0
    formula: str = ""


@dataclass
class FCFConsistencyCheck:
    """FCF一致性检查结果"""
    fcf_ni_ratio: Optional[float] = None
    fcf_ocf_ratio: Optional[float] = None
    negative_fcf_years: int = 0
    warnings: List[str] = field(default_factory=list)
    passed: bool = True


class FCFCalculator:
    """FCF计算器"""
    
    def __init__(self, config: Optional[FCFConfig] = None):
        self.config = config or FCFConfig()
    
    def calculate_fcff(
        self,
        ebit: float,
        tax_rate: float,
        depreciation: float,
        capex: float,
        working_capital_change: float,
    ) -> FCFFResult:
        """企业自由现金流（对全资本提供者）"""
        # NOPAT = EBIT × (1 - T)
        nopat = ebit * (1 - tax_rate)
        
        # FCFF = NOPAT + D&A - CapEx - ΔWC
        fcf = nopat + depreciation - capex - working_capital_change
        
        formula = (
            f"FCFF = EBIT×(1-T) + D&A - CapEx - ΔWC\n"
            f"     = {ebit:.1f}×(1-{tax_rate:.2%}) + {depreciation:.1f} - {capex:.1f} - {working_capital_change:.1f}\n"
            f"     = {nopat:.1f} + {depreciation:.1f} - {capex:.1f} - {working_capital_change:.1f}\n"
            f"     = {fcf:.1f}"
        )
        
        return FCFFResult(
            method="FCFF",
            ebit=ebit,
            tax_rate=tax_rate,
            nopat=nopat,
            depreciation=depreciation,
            capex=capex,
            working_capital_change=working_capital_change,
            fcf=fcf,
            formula=formula,
        )
    
    def calculate_fcfe(
        self,
        net_income: float,
        depreciation: float,
        capex: float,
        working_capital_change: float,
        net_borrowing: float,
    ) -> FCFEResult:
        """股权自由现金流"""
        # FCFE = Net Income + D&A - CapEx - ΔWC + Net Borrowing
        fcf = net_income + depreciation - capex - working_capital_change + net_borrowing
        
        formula = (
            f"FCFE = Net Income + D&A - CapEx - ΔWC + Net Borrowing\n"
            f"     = {net_income:.1f} + {depreciation:.1f} - {capex:.1f} - {working_capital_change:.1f} + {net_borrowing:.1f}\n"
            f"     = {fcf:.1f}"
        )
        
        return FCFEResult(
            method="FCFE",
            net_income=net_income,
            depreciation=depreciation,
            capex=capex,
            working_capital_change=working_capital_change,
            net_borrowing=net_borrowing,
            fcf=fcf,
            formula=formula,
        )
    
    def calculate_lfcf(
        self,
        operating_cashflow: float,
        capex: float,
    ) -> LFCFResult:
        """简化自由现金流"""
        # LFCF = Operating CF - CapEx
        fcf = operating_cashflow - capex
        
        formula = (
            f"LFCF = Operating CF - CapEx\n"
            f"     = {operating_cashflow:.1f} - {capex:.1f}\n"
            f"     = {fcf:.1f}"
        )
        
        return LFCFResult(
            method="LFCF",
            operating_cashflow=operating_cashflow,
            capex=capex,
            fcf=fcf,
            formula=formula,
        )
    
    def calculate(
        self,
        method: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """主计算入口"""
        method = method or self.config.definition
        
        if method == "FCFF":
            result = self.calculate_fcff(
                ebit=kwargs.get('ebit', 0),
                tax_rate=kwargs.get('tax_rate', 0.25),
                depreciation=kwargs.get('depreciation', 0),
                capex=kwargs.get('capex', 0),
                working_capital_change=kwargs.get('working_capital_change', 0),
            )
        elif method == "FCFE":
            result = self.calculate_fcfe(
                net_income=kwargs.get('net_income', 0),
                depreciation=kwargs.get('depreciation', 0),
                capex=kwargs.get('capex', 0),
                working_capital_change=kwargs.get('working_capital_change', 0),
                net_borrowing=kwargs.get('net_borrowing', 0),
            )
        elif method == "LFCF":
            result = self.calculate_lfcf(
                operating_cashflow=kwargs.get('operating_cashflow', 0),
                capex=kwargs.get('capex', 0),
            )
        else:
            raise ValueError(f"未知FCF方法: {method}")
        
        return {
            "method": method,
            "fcf": result.fcf,
            "formula": result.formula,
            "details": result,
        }
    
    def check_consistency(
        self,
        fcf: float,
        net_income: float,
        operating_cashflow: float,
        negative_fcf_years: int = 0,
    ) -> FCFConsistencyCheck:
        """FCF一致性检查"""
        result = FCFConsistencyCheck()
        
        # FCF/NI比值
        if net_income != 0:
            result.fcf_ni_ratio = fcf / net_income
            min_ratio, max_ratio = self.config.fcf_ni_ratio_range
            if not (min_ratio <= result.fcf_ni_ratio <= max_ratio):
                result.warnings.append(
                    f"FCF/NI比值 {result.fcf_ni_ratio:.2f} 超出合理区间 [{min_ratio}, {max_ratio}]"
                )
                result.passed = False
        
        # FCF/OCF比值
        if operating_cashflow != 0:
            result.fcf_ocf_ratio = fcf / operating_cashflow
            if result.fcf_ocf_ratio < self.config.fcf_ocf_ratio_min:
                result.warnings.append(
                    f"FCF/OCF比值 {result.fcf_ocf_ratio:.2f} 低于最小值 {self.config.fcf_ocf_ratio_min}"
                )
                result.passed = False
        
        # 连续负FCF年数
        result.negative_fcf_years = negative_fcf_years
        if negative_fcf_years > self.config.negative_fcf_years_max:
            result.warnings.append(
                f"连续负FCF年数 {negative_fcf_years} 超过上限 {self.config.negative_fcf_years_max}"
            )
            result.passed = False
        
        return result
    
    def annotate_fcf(self, fcf_value: float, method: str) -> str:
        """FCF标注"""
        return f"FCF({method}) = {fcf_value:.1f}亿"
