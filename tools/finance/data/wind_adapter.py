"""
Wind 字段映射适配层（v10 新建，HeavySkill K8 审查 P0-2）。

将 Wind MCP 返回的原始 dict 转换为 Financials 契约。
缺失字段 fail-fast，禁止静默返回 None 或硬编码默认值。
"""
from __future__ import annotations

import logging
from typing import Any

from ..contracts.financials import Financials

logger = logging.getLogger(__name__)

# Wind 原始字段 → Financials 属性映射
_WIND_FIELD_MAP: dict[tuple[str, str], tuple[str, bool]] = {
    # (section, field_name) → (attr_name, required)
    # 使用 canonical 键名（Wind MCP 经 assemble_wind_data 转换后的形态）
    ("income", "营业收入"): ("revenue", True),
    ("income", "营业利润"): ("operating_profit", True),
    ("income", "归母净利润"): ("net_profit_parent", True),
    ("income", "年毛利润"): ("gross_profit", False),
    ("income", "净利润"): ("net_profit_parent", False),  # alias fallback
    ("balance", "总资产"): ("total_assets", True),
    ("balance", "年负债合计"): ("total_liabilities", True),
    ("balance", "年所有者权益合计"): ("equity_parent", True),
    ("balance", "归母净资产"): ("equity_parent", False),  # alias fallback
    ("balance", "货币资金"): ("cash", False),
    ("balance", "有息负债"): ("interest_bearing_debt", False),
    ("cashflow", "经营活动现金流量净额"): ("operating_cashflow", True),
    ("cashflow", "购建固定资产、无形资产和其他长期资产支付的现金"): ("capex", False),
}


def wind_to_financials(
    wind_data: dict[str, Any],
    ticker: str = "",
    company_name: str = "",
    shares: float = 0,
    current_price: float = 0,
    currency: str = "CNY",
    fiscal_year: int = 0,
) -> Financials:
    """将 Wind 原始数据转换为 Financials 契约。

    Args:
        wind_data: Wind MCP 返回的原始 dict（含 income/balance/cashflow）
        ticker: 股票代码
        company_name: 公司名称
        shares: 总股本（亿股）
        current_price: 当前股价
        currency: 股价币种
        fiscal_year: 财年

    Returns:
        Financials 契约（不可变）

    Raises:
        ValueError: 必填字段缺失时 fail-fast
    """
    errors: list[str] = []
    values: dict[str, float | None] = {}

    for (section, field_name), (attr_name, required) in _WIND_FIELD_MAP.items():
        # 如果该属性已经有值（来自更优先的 key），跳过 alias fallback
        if attr_name in values and values[attr_name] is not None:
            continue

        section_data = wind_data.get(section, {})
        field_list = section_data.get(field_name, [])

        if not field_list:
            if not required:
                # 不覆盖已有值
                if attr_name not in values:
                    values[attr_name] = None
                continue
            errors.append(f"Wind 字段缺失: {section}.{field_name}")
            continue

        raw_value = field_list[-1]
        if raw_value is None:
            if not required:
                if attr_name not in values:
                    values[attr_name] = None
                continue
            errors.append(f"Wind 字段值为 None: {section}.{field_name}")
            continue

        values[attr_name] = float(raw_value)

    if errors:
        raise ValueError(
            f"Wind 数据转换失败（{len(errors)} 项缺失）:\n"
            + "\n".join(f"  - {e}" for e in errors[:10])
        )

    return Financials(
        revenue=values["revenue"],
        operating_profit=values["operating_profit"],
        net_profit_parent=values["net_profit_parent"],
        gross_profit=values.get("gross_profit"),
        total_assets=values["total_assets"],
        total_liabilities=values["total_liabilities"],
        equity_parent=values["equity_parent"],
        cash=values.get("cash"),
        interest_bearing_debt=values.get("interest_bearing_debt"),
        operating_cashflow=values["operating_cashflow"],
        capex=values.get("capex"),
        shares=shares,
        current_price=current_price,
        currency=currency,  # type: ignore[arg-type]
        ticker=ticker,
        company_name=company_name,
        fiscal_year=fiscal_year,
        source="Wind",
    )
