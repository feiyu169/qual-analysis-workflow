"""
估值输入校验器（v10 新建，HeavySkill K8 审查 P0-8 扩展版）。

不能仅检查 5 项，须覆盖 WACC/永续增长/汇率/PS/PB/EV-Rev 等所有关键参数。
"""
from __future__ import annotations

import logging

from ..contracts.financials import Financials

logger = logging.getLogger(__name__)


def validate_valuation_inputs(
    financials: Financials,
    wacc: float | None = None,
    terminal_growth: float | None = None,
    ps_multiple: float | None = None,
    pb_multiple: float | None = None,
    ev_revenue_multiple: float | None = None,
) -> list[str]:
    """估值输入校验（扩展版，8 类检查）。

    Returns:
        错误列表（空 = 通过）。警告记录但不阻断。
    """
    errors: list[str] = []
    warnings: list[str] = []

    # 1. 营业收入
    if financials.revenue < 1:
        errors.append(f"营业收入 {financials.revenue:.2f} 亿过小（<1亿），可能单位错误")
    elif financials.revenue > 100000:
        errors.append(f"营业收入 {financials.revenue:.2f} 亿过大（>10万亿），可能单位错误")

    # 2. 总股本
    if financials.shares <= 0:
        errors.append(f"总股本 {financials.shares} 必须 > 0")
    elif financials.shares > 1000:
        errors.append(f"总股本 {financials.shares:.2f} 亿股过大（>1000亿）")

    # 3. 当前股价
    if financials.current_price <= 0:
        errors.append(f"当前股价 {financials.current_price} 必须 > 0")
    elif financials.current_price > 10000:
        errors.append(f"当前股价 {financials.current_price:.2f} 过大（>10000）")

    # 4. EBIT 利润率
    if financials.ebit_margin < -1.0:
        errors.append(f"EBIT 利润率 {financials.ebit_margin:.2%} 超出范围（<-100%）")
    elif financials.ebit_margin > 1.0:
        errors.append(f"EBIT 利润率 {financials.ebit_margin:.2%} 超出范围（>100%）")

    # 5. 资产负债率
    if financials.total_assets > 0:
        lev = financials.total_liabilities / financials.total_assets
        if lev > 1.0:
            warnings.append(f"资产负债率 {lev:.2%} > 100%（资不抵债），PB 不适用")

    # 6. WACC
    if wacc is not None:
        if wacc < 0.03:
            errors.append(f"WACC {wacc:.2%} 过低（<3%）")
        elif wacc > 0.15:
            errors.append(f"WACC {wacc:.2%} 过高（>15%）")

    # 7. 永续增长率
    if terminal_growth is not None:
        if terminal_growth < -0.01:
            errors.append(f"永续增长率 {terminal_growth:.2%} 过低（<-1%）")
        elif terminal_growth > 0.04:
            errors.append(f"永续增长率 {terminal_growth:.2%} 过高（>4%）")
        if wacc is not None and terminal_growth >= wacc:
            errors.append(f"永续增长率 {terminal_growth:.2%} ≥ WACC {wacc:.2%}（模型崩溃）")

    # 8. 估值乘数
    if ps_multiple is not None and (ps_multiple < 0.2 or ps_multiple > 5.0):
        warnings.append(f"PS {ps_multiple:.2f} 超出合理范围 [0.2, 5.0]")
    if pb_multiple is not None:
        if pb_multiple < 0.2 or pb_multiple > 8.0:
            warnings.append(f"PB {pb_multiple:.2f} 超出合理范围 [0.2, 8.0]")
        if financials.equity_parent <= 0:
            errors.append(f"归母净资产 {financials.equity_parent:.2f} ≤ 0，PB 不适用")
    if ev_revenue_multiple is not None and (ev_revenue_multiple < 0.1 or ev_revenue_multiple > 10.0):
        warnings.append(f"EV/Revenue {ev_revenue_multiple:.2f} 超出合理范围 [0.1, 10.0]")

    # 币种
    if financials.currency not in ("CNY", "HKD", "USD"):
        errors.append(f"币种 {financials.currency} 不支持")

    for w in warnings:
        logger.warning(f"估值输入校验警告: {w}")

    return errors
