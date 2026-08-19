"""
DCFService模块

功能:
- 无状态DCF计算服务
- 整合CAPM和终值计算
- 生成DCF桥接输出

解决: DCF多源矛盾问题

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from .capm_calculator import CAPMCalculator, CAPMResult
from .terminal_value_calculator import TerminalValueCalculator, TerminalValueResult


@dataclass
class DCFInputs:
    """DCF输入参数"""
    # 财务数据
    fcf_projections: List[float]  # FCF预测列表（亿元）
    ebitda_projections: List[float]  # EBITDA预测列表（亿元）
    
    # WACC参数
    rf: float  # 无风险利率
    beta: float  # Beta系数
    erp: float  # 股权风险溢价
    kd: float  # 债务成本
    tax_rate: float  # 税率
    debt_ratio: float  # 负债比率
    
    # 终值参数
    terminal_growth: float  # 永续增长率
    exit_multiple: float  # 退出倍数
    
    # 其他
    net_debt: float  # 净负债（亿元）
    shares: float  # 总股本（亿股）
    current_price: float  # 当前股价
    
    # 可选参数
    size_premium: float = 0.0  # 规模溢价
    alpha: float = 0.0  # α调整


@dataclass
class DCFResult:
    """DCF计算结果"""
    # 估值结果
    enterprise_value: float  # 企业价值（亿元）
    equity_value: float  # 权益价值（亿元）
    per_share_value: float  # 每股价值
    
    # WACC组件
    wacc: float
    capm_result: CAPMResult
    
    # 终值组件
    terminal_value_result: TerminalValueResult
    
    # 现金流折现
    pv_fcf: float  # FCF现值
    pv_terminal: float  # 终值现值
    
    # 桥接输出
    bridge: Dict[str, Any]
    
    # 敏感性分析
    sensitivity: Optional[Dict[str, Any]] = None


class DCFService:
    """DCF计算服务
    
    无状态设计，所有输入通过参数传入
    
    计算流程:
    1. 计算WACC (CAPMCalculator)
    2. 计算FCF现值
    3. 计算终值 (TerminalValueCalculator)
    4. 计算企业价值
    5. 计算权益价值
    6. 生成桥接输出
    """
    
    def __init__(self):
        self.capm_calculator = CAPMCalculator()
        self.terminal_value_calculator = TerminalValueCalculator()
    
    def calculate(self, inputs: DCFInputs) -> DCFResult:
        """执行DCF计算"""
        
        # 1. 计算WACC
        capm_result = self.capm_calculator.calculate(
            rf=inputs.rf,
            beta=inputs.beta,
            erp=inputs.erp,
            size_premium=inputs.size_premium,
            alpha=inputs.alpha
        )
        
        # 计算WACC
        ke = capm_result.ke
        kd_after_tax = inputs.kd * (1 - inputs.tax_rate)
        wacc = ke * (1 - inputs.debt_ratio) + kd_after_tax * inputs.debt_ratio
        
        # 2. 计算FCF现值
        pv_fcf = self._calculate_fcf_pv(
            fcf_projections=inputs.fcf_projections,
            wacc=wacc
        )
        
        # 3. 计算终值
        # 使用最后一年FCF和EBITDA
        last_fcf = inputs.fcf_projections[-1] if inputs.fcf_projections else 0
        last_ebitda = inputs.ebitda_projections[-1] if inputs.ebitda_projections else 0
        
        terminal_value_result = self.terminal_value_calculator.calculate(
            fcf=last_fcf,
            ebitda=last_ebitda,
            wacc=wacc,
            g=inputs.terminal_growth,
            exit_multiple=inputs.exit_multiple,
            ev_estimate=pv_fcf  # 使用FCF现值作为EV估计
        )
        
        # 4. 计算终值现值
        n_years = len(inputs.fcf_projections)
        pv_terminal = terminal_value_result.chosen_tv / (1 + wacc) ** n_years
        
        # 5. 计算企业价值
        enterprise_value = pv_fcf + pv_terminal
        
        # 6. 计算权益价值
        equity_value = enterprise_value - inputs.net_debt
        
        # 7. 计算每股价值
        per_share_value = equity_value / inputs.shares if inputs.shares > 0 else 0
        
        # 8. 生成桥接输出
        bridge = self._generate_bridge(
            inputs=inputs,
            wacc=wacc,
            capm_result=capm_result,
            terminal_value_result=terminal_value_result,
            pv_fcf=pv_fcf,
            pv_terminal=pv_terminal,
            enterprise_value=enterprise_value,
            equity_value=equity_value,
            per_share_value=per_share_value
        )
        
        return DCFResult(
            enterprise_value=enterprise_value,
            equity_value=equity_value,
            per_share_value=per_share_value,
            wacc=wacc,
            capm_result=capm_result,
            terminal_value_result=terminal_value_result,
            pv_fcf=pv_fcf,
            pv_terminal=pv_terminal,
            bridge=bridge
        )
    
    def _calculate_fcf_pv(
        self,
        fcf_projections: List[float],
        wacc: float
    ) -> float:
        """计算FCF现值"""
        
        pv = 0
        for i, fcf in enumerate(fcf_projections):
            pv += fcf / (1 + wacc) ** (i + 1)
        
        return pv
    
    def _generate_bridge(
        self,
        inputs: DCFInputs,
        wacc: float,
        capm_result: CAPMResult,
        terminal_value_result: TerminalValueResult,
        pv_fcf: float,
        pv_terminal: float,
        enterprise_value: float,
        equity_value: float,
        per_share_value: float
    ) -> Dict[str, Any]:
        """生成桥接输出"""
        
        return {
            "wacc": {
                "value": wacc,
                "components": {
                    "ke": capm_result.ke,
                    "kd_after_tax": inputs.kd * (1 - inputs.tax_rate),
                    "debt_ratio": inputs.debt_ratio
                }
            },
            "capm": {
                "rf": capm_result.rf,
                "beta": capm_result.beta,
                "erp": capm_result.erp,
                "size_premium": capm_result.size_premium,
                "alpha": capm_result.alpha,
                "ke": capm_result.ke
            },
            "terminal_value": {
                "perpetuity": terminal_value_result.tv_perpetuity,
                "exit_multiple": terminal_value_result.tv_exit_multiple,
                "chosen": terminal_value_result.chosen_tv,
                "method": terminal_value_result.chosen_method,
                "confidence": terminal_value_result.confidence
            },
            "present_values": {
                "fcf": pv_fcf,
                "terminal": pv_terminal,
                "total": pv_fcf + pv_terminal
            },
            "valuation": {
                "enterprise_value": enterprise_value,
                "net_debt": inputs.net_debt,
                "equity_value": equity_value,
                "shares": inputs.shares,
                "per_share_value": per_share_value,
                "current_price": inputs.current_price,
                "upside": (per_share_value / inputs.current_price - 1) if inputs.current_price > 0 else 0
            }
        }
    
    def generate_bridge_report(self, result: DCFResult) -> str:
        """生成桥接报告"""
        
        bridge = result.bridge
        
        report = f"""## DCF估值桥接报告

### WACC计算

| 组件 | 值 |
|------|-----|
| Ke (权益成本) | {bridge['capm']['ke']:.2%} |
| Kd (税后债务成本) | {bridge['wacc']['components']['kd_after_tax']:.2%} |
| D/(D+E) (负债比率) | {bridge['wacc']['components']['debt_ratio']:.2%} |
| **WACC** | **{bridge['wacc']['value']:.2%}** |

### CAPM分解

| 参数 | 值 |
|------|-----|
| Rf (无风险利率) | {bridge['capm']['rf']:.2%} |
| β (Beta) | {bridge['capm']['beta']:.2f} |
| ERP (股权风险溢价) | {bridge['capm']['erp']:.2%} |
| 规模溢价 | {bridge['capm']['size_premium']:.2%} |
| α调整 | {bridge['capm']['alpha']:.2%} |

### 终值计算

| 方法 | 值 |
|------|-----|
| 永续增长法 | {bridge['terminal_value']['perpetuity']:.0f} |
| 退出倍数法 | {bridge['terminal_value']['exit_multiple']:.0f} |
| 选定方法 | {bridge['terminal_value']['method']} |
| 选定终值 | {bridge['terminal_value']['chosen']:.0f} |
| 置信度 | {bridge['terminal_value']['confidence']} |

### 估值桥接

| 项目 | 值 |
|------|-----|
| FCF现值 | {bridge['present_values']['fcf']:.0f} |
| 终值现值 | {bridge['present_values']['terminal']:.0f} |
| **企业价值** | **{bridge['valuation']['enterprise_value']:.0f}** |
| 减：净负债 | {bridge['valuation']['net_debt']:.0f} |
| **权益价值** | **{bridge['valuation']['equity_value']:.0f}** |
| 总股本 | {bridge['valuation']['shares']:.0f} |
| **每股价值** | **{bridge['valuation']['per_share_value']:.2f}** |
| 当前股价 | {bridge['valuation']['current_price']:.2f} |
| **上行空间** | **{bridge['valuation']['upside']:.1%}** |

### 终值占比

终值占企业价值比例: {bridge['present_values']['terminal'] / bridge['present_values']['total']:.1%}

"""
        
        # 添加警告
        tv_ratio = bridge['present_values']['terminal'] / bridge['present_values']['total']
        if tv_ratio > 0.75:
            report += f"\n⚠️ **警告**: 终值占比{tv_ratio:.1%}>75%，估值对永续增长率假设敏感\n"
        
        return report
