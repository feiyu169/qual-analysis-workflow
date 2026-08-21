"""
可比公司分析模块 (v3: 纯计算函数，不调用 MCP)
数据收集由 Agent 层负责，本模块仅做 PE/PB 计算和估值区间推导。
"""

import logging

from .data_context import latest_value, safe_get

logger = logging.getLogger(__name__)




def calculate_pe(income: dict, quote: dict) -> float:
    """计算 PE 市盈率

    优先使用 EPS，降级使用 净利润/总股本 近似。
    亏损公司（净利润<=0）返回 0。
    """
    stock_price = safe_get(quote, "最新成交价") or safe_get(quote, "MATCH")
    if stock_price <= 0:
        return 0

    eps = safe_get(income, "基本每股收益")
    if eps > 0:
        return stock_price / eps

    # 降级: 净利润 / 总股本 (Wind 不提供总股本，此路径无法走通)
    net_profit = latest_value(income, "年净利润")
    if net_profit > 0:
        # 无法获取总股本，返回 0 表示无法计算
        logger.warning("无法计算 PE: EPS 缺失且无总股本数据")
        return 0

    return 0


def calculate_pb(balance: dict, quote: dict) -> float:
    """计算 PB 市净率

    优先使用每股净资产，降级使用 总资产/总负债 近似。
    净资产为负或零时返回 0。
    """
    stock_price = safe_get(quote, "最新成交价") or safe_get(quote, "MATCH")
    if stock_price <= 0:
        return 0

    bvps = safe_get(balance, "每股净资产")
    if bvps > 0:
        return stock_price / bvps

    # 降级: 用最新一年所有者权益 (Wind 返回3年数组)
    book_value = latest_value(balance, "最近3年每年所有者权益合计")
    if book_value > 0:
        # 无法获取总股本，返回 0 表示无法计算
        logger.warning("无法计算 PB: 每股净资产缺失且无总股本数据")
        return 0

    return 0


def comps_analysis(
    target_ticker: str,
    target_income: dict,
    target_balance: dict,
    target_quote: dict,
    peers_data: list[dict],
) -> dict:
    """可比公司分析（纯计算函数，不调用 MCP）

    数据收集由 Agent 层负责，通过 Wind MCP 获取后传入本函数。

    Args:
        target_ticker: 目标公司代码
        target_income: 目标公司利润表数据 (Wind 原始字段名)
        target_balance: 目标公司资产负债表数据
        target_quote: 目标公司行情数据
        peers_data: 可比公司数据列表，每项格式:
            {
                "ticker": "600519.SH",
                "name": "贵州茅台",
                "income": {...},  # 利润表
                "balance": {...},  # 资产负债表
                "quote": {...},   # 行情
            }

    Returns:
        {
            "peers": [{"ticker", "name", "pe", "pb", ...}],
            "target_multiples": {"pe": float, "pb": float},
            "pe_median": float,
            "pb_median": float,
            "peer_count": int,
            "warnings": [str],
        }
    """
    warnings = []

    # --- 1. 计算可比公司 PE/PB ---
    peers = []
    for peer in peers_data:
        ticker = peer.get("ticker", "unknown")
        name = peer.get("name", ticker)
        income = peer.get("income", {})
        balance = peer.get("balance", {})
        quote = peer.get("quote", {})

        pe = calculate_pe(income, quote)
        pb = calculate_pb(balance, quote)

        # 过滤无效值
        if pe > 0 and pb > 0 and pe < 1000 and pb < 100:
            peers.append({
                "ticker": ticker,
                "name": name,
                "pe": round(pe, 2),
                "pb": round(pb, 2),
            })

    if not peers:
        warnings.append("无有效的可比公司数据（PE/PB 均为 0 或超出范围）")
        return {
            "peers": [],
            "target_multiples": {"pe": 0, "pb": 0},
            "pe_median": 15,
            "pb_median": 2,
            "peer_count": 0,
            "warnings": warnings,
        }

    # --- 2. 计算目标公司 PE/PB ---
    target_pe = calculate_pe(target_income, target_quote)
    target_pb = calculate_pb(target_balance, target_quote)

    # --- 3. 计算估值区间（可比公司中位数） ---
    pe_values = sorted([p["pe"] for p in peers if p["pe"] > 0])
    pb_values = sorted([p["pb"] for p in peers if p["pb"] > 0])

    pe_median = pe_values[len(pe_values) // 2] if pe_values else 15
    pb_median = pb_values[len(pb_values) // 2] if pb_values else 2

    if not pe_values:
        warnings.append("PE 数据不足，使用默认中位数 15")
    if not pb_values:
        warnings.append("PB 数据不足，使用默认中位数 2")

    return {
        "peers": peers,
        "target_multiples": {"pe": round(target_pe, 2), "pb": round(target_pb, 2)},
        "pe_median": round(pe_median, 2),
        "pb_median": round(pb_median, 2),
        "peer_count": len(peers),
        "warnings": warnings,
    }
