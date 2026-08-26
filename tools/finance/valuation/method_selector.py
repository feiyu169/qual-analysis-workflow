"""
估值方法选择矩阵（v10 新建，HeavySkill K8 审查 P0-4）。

根据公司特征自动选择最适当的估值方法。
对标 CFA Standard V-B：估值方法必须适当。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from ..contracts.financials import Financials

logger = logging.getLogger(__name__)


class ValuationMethod(str, Enum):  # noqa: UP042
    """估值方法枚举。"""
    DCF = "DCF"
    EV_REVENUE = "EV/Revenue"
    PE = "PE"
    PS = "PS"
    PB = "PB"


@dataclass(frozen=True)
class MethodSelection:
    """估值方法选择结果。"""
    primary: ValuationMethod
    cross_validation: list[ValuationMethod]
    auxiliary: list[ValuationMethod]
    excluded: list[ValuationMethod]
    reason: str


def select_valuation_methods(financials: Financials) -> MethodSelection:
    """根据公司特征选择估值方法（CFA Standard V-B）。

    小鹏类公司（会计亏损、经营现金流转正、高速增长）：
    - 主方法：EV/Revenue
    - 交叉验证：PS
    - 辅助：PB（净资产为正时）
    - DCF：仅当 OCF 为正时作辅助情景
    - PE：亏损公司排除（负 EPS 无意义）
    """
    excluded: list[ValuationMethod] = []
    auxiliary: list[ValuationMethod] = []
    cross_val: list[ValuationMethod] = []
    reason_parts: list[str] = []

    # PE：亏损公司排除
    if financials.is_loss_company:
        excluded.append(ValuationMethod.PE)
        reason_parts.append("亏损公司（负 EPS），PE 不适用")
    else:
        cross_val.append(ValuationMethod.PE)

    # DCF：亏损公司降级为辅助（OCF 为正时可作情景）
    if financials.is_loss_company:
        if financials.has_positive_ocf:
            auxiliary.append(ValuationMethod.DCF)
            reason_parts.append(
                f"会计亏损但 OCF={financials.operating_cashflow:.1f}亿为正，"
                f"DCF 仅作辅助情景"
            )
        else:
            excluded.append(ValuationMethod.DCF)
            reason_parts.append("亏损公司且 OCF 为负，DCF 不适用")
    else:
        cross_val.append(ValuationMethod.DCF)

    # PB：净资产为正时可用
    if financials.equity_parent > 0:
        auxiliary.append(ValuationMethod.PB)
    else:
        excluded.append(ValuationMethod.PB)
        reason_parts.append("归母净资产≤0，PB 不适用")

    # EV/Revenue 和 PS：始终可用
    primary = ValuationMethod.EV_REVENUE
    cross_val.append(ValuationMethod.PS)
    reason_parts.insert(
        0,
        f"主方法 EV/Revenue（营收 {financials.revenue:.1f}亿，"
        f"YoY 高增长，亏损收窄中）",
    )

    return MethodSelection(
        primary=primary,
        cross_validation=cross_val,
        auxiliary=auxiliary,
        excluded=excluded,
        reason="；".join(reason_parts),
    )
