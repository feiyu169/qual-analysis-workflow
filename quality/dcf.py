"""
quality/dcf.py — DCF估值模块

实现DCF（现金流折现）估值：
- FCF预测
- WACC计算
- 终值计算
- 敏感性分析
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DCFInputs:
    """DCF输入参数"""
    # FCF预测
    fcf_projections: list[float]  # 未来N年FCF预测（亿元）
    projection_years: int = 5     # 预测年数
    
    # WACC参数
    risk_free_rate: float = 0.03      # 无风险利率
    equity_risk_premium: float = 0.06  # 股权风险溢价
    beta: float = 1.0                   # Beta系数
    cost_of_debt: float = 0.05         # 债务成本
    tax_rate: float = 0.25             # 税率
    debt_ratio: float = 0.0            # 债务比例（D/V）
    
    # 终值参数
    terminal_growth_rate: float = 0.02  # 永续增长率
    terminal_method: str = "gordon"     # "gordon" | "exit_multiple"
    
    # 退出倍数法参数（可选）
    terminal_ebitda_multiple: float = 10.0  # 终值EBITDA倍数
    terminal_ebitda: float = 0.0            # 终值年EBITDA
    
    # 其他
    shares_outstanding: float = 1.0  # 总股本（亿股）
    current_price: float = 0.0       # 当前股价
    currency: str = "CNY"


@dataclass
class DCFResult:
    """DCF输出结果"""
    # 估值结果
    equity_value: float        # 股权价值（亿元）
    per_share_value: float     # 每股价值（元）
    current_price: float       # 当前股价
    upside: float              # 上行空间（%）
    
    # WACC
    wacc: float                # 加权平均资本成本
    cost_of_equity: float      # 股权成本
    
    # 终值
    terminal_value: float      # 终值（亿元）
    terminal_value_pv: float   # 终值现值（亿元）
    
    # FCF现值
    fcf_pv: float              # FCF现值合计（亿元）
    
    # 敏感性分析
    sensitivity: Optional['DCFSensitivity'] = None
    
    # 详细数据
    yearly_data: list[dict] = field(default_factory=list)
    
    # 警告
    warnings: list[str] = field(default_factory=list)


@dataclass
class DCFSensitivity:
    """DCF敏感性分析"""
    wacc_range: list[float]           # WACC范围
    growth_range: list[float]         # 增长率范围
    value_matrix: list[list[float]]   # 估值矩阵 [wacc][growth]
    

class DCFCalculator:
    """DCF计算器"""
    
    def calculate(self, inputs: DCFInputs) -> DCFResult:
        """执行DCF估值
        
        Args:
            inputs: DCF输入参数
            
        Returns:
            DCFResult: DCF估值结果
        """
        logger.info("开始DCF估值")
        
        # 1. 计算WACC
        wacc, cost_of_equity = self._calculate_wacc(inputs)
        logger.info(f"WACC: {wacc:.2%}, 股权成本: {cost_of_equity:.2%}")
        
        # 2. 计算FCF现值
        fcf_pv, yearly_data = self._calculate_fcf_pv(inputs, wacc)
        logger.info(f"FCF现值: {fcf_pv:.2f}亿元")
        
        # 3. 计算终值
        terminal_value, terminal_value_pv = self._calculate_terminal_value(inputs, wacc)
        logger.info(f"终值: {terminal_value:.2f}亿元, 终值现值: {terminal_value_pv:.2f}亿元")
        
        # 4. 计算股权价值
        enterprise_value = fcf_pv + terminal_value_pv
        equity_value = enterprise_value  # 简化：假设无净债务
        
        # 5. 计算每股价值
        if inputs.shares_outstanding > 0:
            per_share_value = equity_value / inputs.shares_outstanding
        else:
            per_share_value = 0
        
        # 6. 计算上行空间
        if inputs.current_price > 0:
            upside = (per_share_value - inputs.current_price) / inputs.current_price * 100
        else:
            upside = 0
        
        # 7. 生成警告
        warnings = self._generate_warnings(inputs, wacc, terminal_value, enterprise_value)
        
        result = DCFResult(
            equity_value=equity_value,
            per_share_value=per_share_value,
            current_price=inputs.current_price,
            upside=upside,
            wacc=wacc,
            cost_of_equity=cost_of_equity,
            terminal_value=terminal_value,
            terminal_value_pv=terminal_value_pv,
            fcf_pv=fcf_pv,
            yearly_data=yearly_data,
            warnings=warnings
        )
        
        logger.info(f"DCF估值完成: 每股价值={per_share_value:.2f}元, 上行空间={upside:.1f}%")
        
        return result
    
    def _calculate_wacc(self, inputs: DCFInputs) -> tuple[float, float]:
        """计算WACC
        
        Returns:
            tuple: (wacc, cost_of_equity)
        """
        # CAPM计算股权成本
        cost_of_equity = inputs.risk_free_rate + inputs.beta * inputs.equity_risk_premium
        
        # WACC
        debt_ratio = inputs.debt_ratio
        equity_ratio = 1 - debt_ratio
        
        wacc = (equity_ratio * cost_of_equity + 
                debt_ratio * inputs.cost_of_debt * (1 - inputs.tax_rate))
        
        return wacc, cost_of_equity
    
    def _calculate_fcf_pv(
        self, 
        inputs: DCFInputs, 
        wacc: float
    ) -> tuple[float, list[dict]]:
        """计算FCF现值
        
        Returns:
            tuple: (fcf_pv, yearly_data)
        """
        fcf_pv = 0.0
        yearly_data = []
        
        for i, fcf in enumerate(inputs.fcf_projections):
            year = i + 1
            discount_factor = 1 / (1 + wacc) ** year
            pv = fcf * discount_factor
            fcf_pv += pv
            
            yearly_data.append({
                "year": year,
                "fcf": fcf,
                "discount_factor": discount_factor,
                "pv": pv
            })
        
        return fcf_pv, yearly_data
    
    def _calculate_terminal_value(
        self, 
        inputs: DCFInputs, 
        wacc: float
    ) -> tuple[float, float]:
        """计算终值
        
        Returns:
            tuple: (terminal_value, terminal_value_pv)
        """
        if inputs.terminal_method == "gordon":
            # Gordon增长模型
            last_fcf = inputs.fcf_projections[-1] if inputs.fcf_projections else 0
            next_fcf = last_fcf * (1 + inputs.terminal_growth_rate)
            
            if wacc <= inputs.terminal_growth_rate:
                # WACC必须大于永续增长率
                terminal_value = 0
                logger.warning("WACC <= 永续增长率，终值计算无效")
            else:
                terminal_value = next_fcf / (wacc - inputs.terminal_growth_rate)
        
        elif inputs.terminal_method == "exit_multiple":
            # 退出倍数法
            terminal_value = inputs.terminal_ebitda_multiple * inputs.terminal_ebitda
        
        else:
            terminal_value = 0
        
        # 终值现值
        projection_years = len(inputs.fcf_projections)
        terminal_value_pv = terminal_value / (1 + wacc) ** projection_years
        
        return terminal_value, terminal_value_pv
    
    def _generate_warnings(
        self, 
        inputs: DCFInputs, 
        wacc: float, 
        terminal_value: float, 
        enterprise_value: float
    ) -> list[str]:
        """生成警告"""
        warnings = []
        
        # WACC合理性检查
        if wacc < 0.05 or wacc > 0.20:
            warnings.append(f"WACC={wacc:.2%}，超出正常范围(5%-20%)")
        
        # 永续增长率合理性检查
        if inputs.terminal_growth_rate > 0.05:
            warnings.append(f"永续增长率={inputs.terminal_growth_rate:.2%}，过高（通常<5%）")
        
        # 终值占比检查
        if enterprise_value > 0:
            terminal_pct = terminal_value / enterprise_value * 100
            if terminal_pct > 80:
                warnings.append(f"终值占比={terminal_pct:.1f}%，过高（通常<80%）")
        
        # FCF预测年数检查
        if len(inputs.fcf_projections) < 3:
            warnings.append(f"FCF预测年数={len(inputs.fcf_projections)}，过少（通常>=3年）")
        
        return warnings
    
    def sensitivity_analysis(
        self, 
        inputs: DCFInputs, 
        wacc_range: list[float], 
        growth_range: list[float]
    ) -> DCFSensitivity:
        """敏感性分析
        
        Args:
            inputs: DCF输入参数
            wacc_range: WACC范围
            growth_range: 永续增长率范围
            
        Returns:
            DCFSensitivity: 敏感性分析结果
        """
        value_matrix = []
        
        for wacc in wacc_range:
            row = []
            for growth in growth_range:
                # 修改参数
                modified_inputs = DCFInputs(
                    fcf_projections=inputs.fcf_projections,
                    projection_years=inputs.projection_years,
                    risk_free_rate=inputs.risk_free_rate,
                    equity_risk_premium=inputs.equity_risk_premium,
                    beta=inputs.beta,
                    cost_of_debt=inputs.cost_of_debt,
                    tax_rate=inputs.tax_rate,
                    debt_ratio=inputs.debt_ratio,
                    terminal_growth_rate=growth,
                    terminal_method=inputs.terminal_method,
                    shares_outstanding=inputs.shares_outstanding,
                    current_price=inputs.current_price,
                    currency=inputs.currency
                )
                
                # 计算估值
                result = self.calculate(modified_inputs)
                row.append(result.per_share_value)
            
            value_matrix.append(row)
        
        return DCFSensitivity(
            wacc_range=wacc_range,
            growth_range=growth_range,
            value_matrix=value_matrix
        )


def format_dcf_report(result: DCFResult) -> str:
    """格式化DCF报告"""
    lines = []
    lines.append("## DCF估值分析")
    lines.append("")
    lines.append("### 核心参数")
    lines.append(f"- WACC: {result.wacc:.2%}")
    lines.append(f"- 股权成本: {result.cost_of_equity:.2%}")
    lines.append(f"- 终值: {result.terminal_value:.2f}亿元")
    lines.append(f"- 终值现值: {result.terminal_value_pv:.2f}亿元")
    lines.append("")
    lines.append("### 估值结果")
    lines.append(f"- 股权价值: {result.equity_value:.2f}亿元")
    lines.append(f"- 每股价值: {result.per_share_value:.2f}元")
    lines.append(f"- 当前股价: {result.current_price:.2f}元")
    lines.append(f"- 上行空间: {result.upside:.1f}%")
    lines.append("")
    
    if result.yearly_data:
        lines.append("### FCF预测")
        lines.append("| 年份 | FCF(亿元) | 折现系数 | 现值(亿元) |")
        lines.append("|------|-----------|----------|------------|")
        for data in result.yearly_data:
            lines.append(f"| {data['year']} | {data['fcf']:.2f} | {data['discount_factor']:.4f} | {data['pv']:.2f} |")
        lines.append("")
    
    if result.sensitivity:
        lines.append("### 敏感性分析")
        lines.append("| WACC \\ 增长率 | " + " | ".join([f"{g:.1%}" for g in result.sensitivity.growth_range]) + " |")
        lines.append("|---" + "---" * len(result.sensitivity.growth_range) + "|")
        for i, wacc in enumerate(result.sensitivity.wacc_range):
            row = [f"{wacc:.1%}"]
            for j, growth in enumerate(result.sensitivity.growth_range):
                row.append(f"{result.sensitivity.value_matrix[i][j]:.2f}")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    
    if result.warnings:
        lines.append("### 警告")
        for warning in result.warnings:
            lines.append(f"- ⚠️ {warning}")
        lines.append("")
    
    return "\n".join(lines)
