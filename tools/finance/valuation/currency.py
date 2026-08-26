"""
币种统一模块（v10 新建，HeavySkill K8 审查 P0-3）。

内部统一为人民币计算，最终目标价按报告日汇率折算为港元。
禁止在估值比较中混用 CNY/HKD。
"""
from __future__ import annotations

from dataclasses import dataclass

# 默认汇率（Wind 实时行情获取，此处为 fallback）
_DEFAULT_RATES: dict[tuple[str, str], float] = {
    ("CNY", "HKD"): 1.08,
    ("HKD", "CNY"): 0.926,
    ("CNY", "USD"): 0.137,
    ("USD", "CNY"): 7.30,
}


@dataclass(frozen=True)
class PriceResult:
    """估值结果（含多币种）。"""
    value_cny: float
    value_hkd: float
    value_usd: float
    currency_used: str
    exchange_rate: float


def convert_to_cny(
    value: float,
    from_currency: str,
    rates: dict[tuple[str, str], float] | None = None,
) -> float:
    """将任意币种转换为人民币。"""
    if from_currency == "CNY":
        return value
    r = (rates or _DEFAULT_RATES).get((from_currency, "CNY"), 1.0)
    return value * r


def convert_from_cny(
    value_cny: float,
    to_currency: str,
    rates: dict[tuple[str, str], float] | None = None,
) -> float:
    """将人民币转换为任意币种。"""
    if to_currency == "CNY":
        return value_cny
    r = (rates or _DEFAULT_RATES).get(("CNY", to_currency), 1.0)
    return value_cny * r


def make_price_result(
    value: float,
    source_currency: str,
    rates: dict[tuple[str, str], float] | None = None,
) -> PriceResult:
    """创建统一币种的估值结果。"""
    value_cny = convert_to_cny(value, source_currency, rates)
    value_hkd = convert_from_cny(value_cny, "HKD", rates)
    value_usd = convert_from_cny(value_cny, "USD", rates)
    rate = (rates or _DEFAULT_RATES).get((source_currency, "CNY"), 1.0)
    return PriceResult(
        value_cny=round(value_cny, 2),
        value_hkd=round(value_hkd, 2),
        value_usd=round(value_usd, 2),
        currency_used=source_currency,
        exchange_rate=rate,
    )
