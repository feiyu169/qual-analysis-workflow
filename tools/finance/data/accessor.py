"""
Wind 数据统一访问层（v10 新建，解决 63 处直接 dict 访问问题）。

所有 Wind 数据访问必须通过此模块，禁止直接 `income.get('年营业总收入')`。
使用 canonical.py 的别名映射自动处理 key 不匹配。

用法:
    from .data.accessor import get_revenue, get_net_profit, get_operating_profit
    rev = get_revenue(wind_data)  # 自动处理 key 别名
"""
from __future__ import annotations

import logging
from typing import Any

from ..canonical import canonicalize

logger = logging.getLogger(__name__)


def _get_income_series(wind_data: dict[str, Any], canonical_key: str) -> list:
    """从 income 表获取 canonical 指标的序列（自动 canonicalize）。"""
    if not wind_data:
        return []
    # 先尝试 canonical 形态
    income = wind_data.get('income', {})
    if canonical_key in income and isinstance(income[canonical_key], list):
        return income[canonical_key]
    # fallback: canonicalize 后再取
    try:
        norm = canonicalize(wind_data)
        return norm.get('income', {}).get(canonical_key, [])
    except Exception:
        return []


def get_revenue(wind_data: dict[str, Any], year_index: int = -1) -> float:
    """获取营业收入（自动 canonical 化）。"""
    series = _get_income_series(wind_data, '营业收入')
    if not series:
        return 0.0
    try:
        return float(series[year_index])
    except (IndexError, TypeError, ValueError):
        return 0.0


def get_net_profit(wind_data: dict[str, Any], year_index: int = -1) -> float:
    """获取归母净利润（自动 canonical 化）。"""
    series = _get_income_series(wind_data, '归母净利润')
    if not series:
        return 0.0
    try:
        return float(series[year_index])
    except (IndexError, TypeError, ValueError):
        return 0.0


def get_operating_profit(wind_data: dict[str, Any], year_index: int = -1) -> float:
    """获取营业利润（自动 canonical 化）。"""
    series = _get_income_series(wind_data, '营业利润')
    if not series:
        return 0.0
    try:
        return float(series[year_index])
    except (IndexError, TypeError, ValueError):
        return 0.0


def get_revenue_series(wind_data: dict[str, Any]) -> list[float]:
    """获取营业收入 3 年序列。"""
    return [float(v) for v in _get_income_series(wind_data, '营业收入') if v is not None]


def get_net_profit_series(wind_data: dict[str, Any]) -> list[float]:
    """获取归母净利润 3 年序列。"""
    return [float(v) for v in _get_income_series(wind_data, '归母净利润') if v is not None]


def get_total_assets(wind_data: dict[str, Any], year_index: int = -1) -> float:
    """获取总资产。"""
    balance = wind_data.get('balance', {})
    for key in ['总资产']:
        series = balance.get(key, [])
        if series:
            try:
                return float(series[year_index])
            except (IndexError, TypeError, ValueError):
                pass
    return 0.0


def get_operating_cashflow(wind_data: dict[str, Any], year_index: int = -1) -> float:
    """获取经营活动现金流量净额。"""
    cashflow = wind_data.get('cashflow', {})
    for key in ['经营活动现金流量净额']:
        series = cashflow.get(key, [])
        if series:
            try:
                return float(series[year_index])
            except (IndexError, TypeError, ValueError):
                pass
    return 0.0
