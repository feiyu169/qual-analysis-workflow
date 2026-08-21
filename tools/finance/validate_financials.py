"""
三表勾稽验证模块

验证利润表、资产负债表、现金流量表之间的勾稽关系。
"""

import logging

from .data_context import has_field, safe_get

logger = logging.getLogger(__name__)




def validate_financial_logic_extended(financial_data: dict) -> dict:
    """扩展的三表勾稽验证

    Args:
        financial_data: {
            "income": {...},
            "balance": {...},
            "cashflow": {...}
        }

    Returns:
        {
            "passed": bool,
            "rules": [
                {"name": "现金流勾稽", "passed": True, "detail": "..."},
                {"name": "资产负债表勾稽", "passed": True, "detail": "..."},
                {"name": "利润表勾稽", "passed": True, "detail": "..."},
                {"name": "留存收益勾稽", "passed": True, "detail": "..."},
            ],
            "summary": "4 条规则校验，0 条失败"
        }
    """
    rules = []

    income = financial_data.get("income", {})
    balance = financial_data.get("balance", {})
    cashflow = financial_data.get("cashflow", {})

    # 规则 1: 现金流勾稽
    # OCF ≈ NI + D&A - △WC
    if not has_field(cashflow, "经营活动现金流量净额"):
        rules.append({
            "name": "现金流勾稽",
            "passed": None,
            "detail": "缺少经营活动现金流量净额字段，无法校验"
        })
    else:
        ocf = safe_get(cashflow, "经营活动现金流量净额")
        ni = safe_get(income, "净利润")
        da = safe_get(cashflow, "折旧摊销")
        delta_wc = safe_get(balance, "营运资本变动")

        expected_ocf = ni + da - delta_wc
        if abs(expected_ocf) < 1:  # 避免除零
            rule1_passed = abs(ocf - expected_ocf) < 1
        else:
            rule1_passed = abs(ocf - expected_ocf) / abs(expected_ocf) < 0.2

        rules.append({
            "name": "现金流勾稽",
            "passed": rule1_passed,
            "detail": f"OCF={ocf:.2f}, NI+DA-△WC={expected_ocf:.2f}"
        })

    # 规则 2: 资产负债表勾稽
    # 总资产 = 总负债 + 股东权益
    total_assets = safe_get(balance, "总资产")
    total_liabilities = safe_get(balance, "总负债")
    equity = safe_get(balance, "股东权益")

    if total_assets == 0:
        rules.append({
            "name": "资产负债表勾稽",
            "passed": None,
            "detail": "总资产为 0，无法校验"
        })
    else:
        rule2_passed = abs(total_assets - total_liabilities - equity) / total_assets < 0.01
        rules.append({
            "name": "资产负债表勾稽",
            "passed": rule2_passed,
            "detail": f"资产={total_assets:.2f}, 负债+权益={total_liabilities + equity:.2f}"
        })

    # 规则 3: 利润表勾稽（使用完整公式）
    # 营业利润 ≈ 营业收入 - 营业成本 - 税金及附加 - 销售费用 - 管理费用 - 研发费用 - 财务费用 + 其他收益 + 投资收益
    revenue = safe_get(income, "营业收入")
    cost = safe_get(income, "营业成本")
    tax_surcharge = safe_get(income, "税金及附加")
    selling_exp = safe_get(income, "销售费用")
    admin_exp = safe_get(income, "管理费用")
    rd_exp = safe_get(income, "研发费用")
    finance_exp = safe_get(income, "财务费用")
    other_income = safe_get(income, "其他收益")
    invest_income = safe_get(income, "投资收益")
    operating_profit = safe_get(income, "营业利润")

    expected_profit = (revenue - cost - tax_surcharge - selling_exp - admin_exp - rd_exp - finance_exp + other_income + invest_income)

    if abs(expected_profit) < 1:  # 避免除零
        rule3_passed = abs(operating_profit - expected_profit) < 1
    else:
        rule3_passed = abs(operating_profit - expected_profit) / abs(expected_profit) < 0.1

    rules.append({
        "name": "利润表勾稽",
        "passed": rule3_passed,
        "detail": f"营业利润={operating_profit:.2f}, 计算值={expected_profit:.2f}"
    })

    # 规则 4: 留存收益勾稽
    # 期末未分配利润 = 期初未分配利润 + 本期净利润 - 本期分红
    net_profit = safe_get(income, "净利润")
    retained_earnings_current = safe_get(balance, "未分配利润")
    retained_earnings_previous = safe_get(balance, "未分配利润_上期")

    if retained_earnings_previous == 0:
        rules.append({
            "name": "留存收益勾稽",
            "passed": None,
            "detail": "缺少上期未分配利润数据，无法校验"
        })
    else:
        retained_change = retained_earnings_current - retained_earnings_previous
        # 净利润应大于等于未分配利润变动（因为可能有分红）
        rule4_passed = net_profit >= retained_change * 0.8  # 允许 20% 误差
        rules.append({
            "name": "留存收益勾稽",
            "passed": rule4_passed,
            "detail": f"净利润={net_profit:.2f}, 未分配利润变动={retained_change:.2f}"
        })

    # 汇总结果
    passed_rules = [r for r in rules if r["passed"] is not None]
    failed_rules = [r for r in passed_rules if not r["passed"]]

    return {
        "passed": len(failed_rules) == 0,
        "rules": rules,
        "summary": f"{len(passed_rules)} 条规则校验，{len(failed_rules)} 条失败"
    }


def validate_financials(wind_data: dict, dayu_data: dict, threshold: float = 0.05) -> dict:
    """验证 Wind 和 Dayu 数据的一致性

    Args:
        wind_data: Wind 数据
        dayu_data: Dayu 数据
        threshold: 差异阈值（默认 5%）

    Returns:
        {
            "passed": bool,
            "issues": list
        }
    """
    issues = []

    # 比较关键字段
    compare_fields = [
        ("营业收入", "revenue"),
        ("净利润", "net_income"),
        ("总资产", "total_assets"),
    ]

    for cn_field, en_field in compare_fields:
        wind_value = safe_get(wind_data, cn_field)
        dayu_value = safe_get(dayu_data, en_field)

        if wind_value == 0 and dayu_value == 0:
            continue

        if wind_value == 0 or dayu_value == 0:
            issues.append(f"{cn_field} 数据缺失: Wind={wind_value}, Dayu={dayu_value}")
            continue

        diff = abs(wind_value - dayu_value) / max(abs(wind_value), abs(dayu_value))
        if diff > threshold:
            issues.append(f"{cn_field} 差异 {diff:.1%} > {threshold:.1%}: Wind={wind_value:.2f}, Dayu={dayu_value:.2f}")

    return {
        "passed": len(issues) == 0,
        "issues": issues
    }


def validate_valuation_cross_check(dcf_value: float, comps_range: dict, market_cap: float, threshold: float = 0.20) -> dict:
    """验证估值交叉检查

    Args:
        dcf_value: DCF 估值
        comps_range: 可比公司估值区间 {"low": ..., "mid": ..., "high": ...}
        market_cap: 当前市值
        threshold: 偏差阈值（默认 20%）

    Returns:
        {
            "passed": bool,
            "deviation": float,
            "detail": str
        }
    """
    # DCF vs 市值偏差
    if market_cap == 0:
        return {
            "passed": None,
            "deviation": 0,
            "detail": "市值为 0，无法校验"
        }

    dcf_deviation = abs(dcf_value - market_cap) / market_cap

    # DCF vs 可比公司偏差
    comps_mid = comps_range.get("mid", 0)
    if comps_mid == 0:
        comps_deviation = 0
    else:
        comps_deviation = abs(dcf_value - comps_mid) / comps_mid

    passed = dcf_deviation < threshold and comps_deviation < threshold

    return {
        "passed": passed,
        "deviation": dcf_deviation,
        "detail": f"DCF={dcf_value:.2f}, 市值={market_cap:.2f}, 偏差={dcf_deviation:.1%}"
    }


def check_terminal_value_ratio(equity_value: float, terminal_value: float, threshold: float = 0.85) -> dict:
    """检查终值依赖度

    Args:
        equity_value: 股权价值
        terminal_value: 终值
        threshold: 依赖度阈值（默认 85%）

    Returns:
        {
            "passed": bool,
            "ratio": float,
            "detail": str
        }
    """
    if equity_value == 0:
        return {
            "passed": None,
            "ratio": 0,
            "detail": "股权价值为 0，无法校验"
        }

    ratio = terminal_value / equity_value
    passed = ratio < threshold

    return {
        "passed": passed,
        "ratio": ratio,
        "detail": f"终值依赖度={ratio:.1%}, 阈值={threshold:.1%}"
    }
