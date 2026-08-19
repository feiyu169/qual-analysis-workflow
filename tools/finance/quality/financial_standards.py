"""
FinancialStandards模块

功能:
- 净利润口径标准化
- FCF定义标准化
- ROIC计算标准化

解决: S06 净利润口径混乱
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProfitStandard:
    """利润标准化"""
    name: str
    standard_name: str
    formula: str
    description: str


# 利润口径定义
PROFIT_STANDARDS = {
    "net_profit_parent": ProfitStandard(
        name="归母净利润",
        standard_name="归属于母公司所有者的净利润",
        formula="Net Income attributable to parent company",
        description="扣除少数股东损益后的净利润",
    ),
    "net_profit_total": ProfitStandard(
        name="净利润",
        standard_name="净利润",
        formula="Net Income",
        description="包含少数股东损益的净利润",
    ),
    "operating_profit": ProfitStandard(
        name="营业利润",
        standard_name="营业利润",
        formula="Operating Profit = Revenue - COGS - OpEx",
        description="主营业务产生的利润",
    ),
    "ebit": ProfitStandard(
        name="EBIT",
        standard_name="息税前利润",
        formula="EBIT = Operating Profit + Interest Income",
        description="息税前利润，不受资本结构影响",
    ),
    "nopat": ProfitStandard(
        name="NOPAT",
        standard_name="税后净营业利润",
        formula="NOPAT = EBIT × (1 - Tax Rate)",
        description="税后净营业利润，用于ROIC计算",
    ),
}

# FCF口径定义
FCF_STANDARDS = {
    "FCFF": {
        "name": "企业自由现金流",
        "formula": "FCFF = EBIT×(1-T) + D&A - CapEx - ΔWC",
        "description": "对全资本提供者(股东+债权人)的现金流",
        "use_case": "DCF估值(企业价值)",
    },
    "FCFE": {
        "name": "股权自由现金流",
        "formula": "FCFE = Net Income + D&A - CapEx - ΔWC + Net Borrowing",
        "description": "对股东的现金流",
        "use_case": "DCF估值(权益价值)",
    },
    "LFCF": {
        "name": "简化自由现金流",
        "formula": "LFCF = Operating CF - CapEx",
        "description": "简化计算，忽略营运资本变动",
        "use_case": "快速估算",
    },
}

# ROIC计算口径
ROIC_STANDARDS = {
    "invested_capital": {
        "name": "投入资本",
        "formula": "IC = Total Equity + Total Debt - Cash - Non-Operating Assets",
        "description": "用于ROIC计算的投入资本",
    },
    "roic_formula": {
        "name": "ROIC",
        "formula": "ROIC = NOPAT / IC",
        "description": "投入资本回报率",
    },
}


class FinancialStandards:
    """财务口径标准化"""
    
    def __init__(self):
        self.profit_standards = PROFIT_STANDARDS
        self.fcf_standards = FCF_STANDARDS
        self.roic_standards = ROIC_STANDARDS
    
    def normalize_profit(
        self,
        net_profit_parent: float,
        net_profit_total: Optional[float] = None,
        minority_interest: Optional[float] = None,
    ) -> Dict[str, float]:
        """标准化利润口径"""
        result = {
            "归母净利润": net_profit_parent,
        }
        
        # 如果有少数股东损益，计算总净利润
        if minority_interest is not None:
            result["净利润"] = net_profit_parent + minority_interest
        elif net_profit_total is not None:
            result["净利润"] = net_profit_total
        
        return result
    
    def validate_profit_consistency(
        self,
        net_profit_parent: float,
        net_profit_total: float,
        tolerance: float = 0.05,
    ) -> List[str]:
        """验证利润一致性"""
        issues = []
        
        # 检查归母净利润是否大于总净利润（不应出现）
        if net_profit_parent > net_profit_total * (1 + tolerance):
            issues.append(f"归母净利润({net_profit_parent:.1f})大于总净利润({net_profit_total:.1f})")
        
        # 检查差异是否过大
        if net_profit_total != 0:
            diff_ratio = abs(net_profit_parent - net_profit_total) / abs(net_profit_total)
            if diff_ratio > tolerance:
                issues.append(f"归母净利润与总净利润差异过大({diff_ratio:.1%} > {tolerance:.1%})")
        
        return issues
    
    def normalize_fcf(
        self,
        operating_cashflow: float,
        capex: float,
        net_income: Optional[float] = None,
        depreciation: Optional[float] = None,
        working_capital_change: Optional[float] = None,
        net_borrowing: Optional[float] = None,
        tax_rate: float = 0.25,
        ebit: Optional[float] = None,
    ) -> Dict[str, float]:
        """标准化FCF口径"""
        result = {}
        
        # LFCF = Operating CF - CapEx
        result["LFCF"] = operating_cashflow - capex
        
        # FCFF (如果有足够数据)
        if ebit is not None and depreciation is not None and working_capital_change is not None:
            nopat = ebit * (1 - tax_rate)
            result["FCFF"] = nopat + depreciation - capex - working_capital_change
        
        # FCFE (如果有足够数据)
        if net_income is not None and depreciation is not None and working_capital_change is not None and net_borrowing is not None:
            result["FCFE"] = net_income + depreciation - capex - working_capital_change + net_borrowing
        
        return result
    
    def validate_fcf_consistency(
        self,
        fcf: float,
        operating_cashflow: float,
        net_income: float,
        fcf_type: str = "LFCF",
    ) -> List[str]:
        """验证FCF一致性"""
        issues = []
        
        # FCF/OCF比值检查
        if operating_cashflow != 0:
            fcf_ocf_ratio = fcf / operating_cashflow
            if fcf_ocf_ratio < 0.5:
                issues.append(f"FCF/OCF比值({fcf_ocf_ratio:.2f})低于0.5")
        
        # FCF/NI比值检查
        if net_income != 0:
            fcf_ni_ratio = fcf / net_income
            if fcf_ni_ratio < 0.3 or fcf_ni_ratio > 3.0:
                issues.append(f"FCF/NI比值({fcf_ni_ratio:.2f})超出[0.3, 3.0]区间")
        
        return issues
    
    def calculate_roic(
        self,
        nopat: float,
        invested_capital: float,
    ) -> float:
        """计算ROIC"""
        if invested_capital == 0:
            return 0.0
        return nopat / invested_capital
    
    def calculate_invested_capital(
        self,
        total_equity: float,
        total_debt: float,
        cash: float,
        non_operating_assets: float = 0,
    ) -> float:
        """计算投入资本"""
        return total_equity + total_debt - cash - non_operating_assets
    
    def generate_standards_report(self) -> str:
        """生成口径报告"""
        lines = [
            "## 财务口径标准化报告",
            "",
            "### 利润口径",
            "",
            "| 名称 | 标准名称 | 公式 |",
            "|------|----------|------|",
        ]
        
        for key, standard in self.profit_standards.items():
            lines.append(f"| {standard.name} | {standard.standard_name} | {standard.formula} |")
        
        lines.extend([
            "",
            "### FCF口径",
            "",
            "| 名称 | 公式 | 用途 |",
            "|------|------|------|",
        ])
        
        for key, standard in self.fcf_standards.items():
            lines.append(f"| {standard['name']} | {standard['formula']} | {standard['use_case']} |")
        
        return "\n".join(lines)
