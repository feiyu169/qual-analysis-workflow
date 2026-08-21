"""Wind 缺失字段处置表（B5-1：财务数据 100% Wind 的字段契约）

盘点 FinancialFacts 全部财务字段的 Wind 来源：
- source: 有 canonical 源（经 canonical.get_series 直接取）
- derived: 可派生（公式 + 标注，不允许 LLM 补值）
- unavailable: 不可得（Wind 无源、无可靠派生 → 空缺 + 报告标注"未披露"，禁止启发式回填）

原则（证券专家 Top 4 + B5-1）：
1. 财务 100% Wind——LLM 不从年报提取财务数字
2. 无源字段显式"未披露"，禁止用 0/估算/行业均值回填
3. 派生字段带公式标注，供复核
"""

# 处置表：FinancialFacts 字段 → 处置方式
# source = canonical 键（canonical.get_series 取 3 年序列，取最新）
# derived = (公式说明, 依赖的 canonical 键)
# unavailable = 原因说明
FINANCIAL_FIELD_DISPOSITION: dict[str, dict] = {
    "revenue": {"kind": "source", "canonical": "营业收入"},
    "net_profit": {"kind": "source", "canonical": "归母净利润"},
    "operating_cashflow": {"kind": "source", "canonical": "经营活动现金流量净额"},
    "capex": {"kind": "source", "canonical": "购建固定资产、无形资产和其他长期资产支付的现金"},
    "total_assets": {"kind": "source", "canonical": "总资产"},
    "total_liabilities": {"kind": "source", "canonical": "年负债合计"},
    "equity": {"kind": "source", "canonical": "年所有者权益合计"},
    "gross_margin": {
        "kind": "derived",
        "formula": "营业利润 / 营业收入（最新财年；毛利率口径近似，标注派生）",
        "deps": ["营业利润", "营业收入"],
    },
    "operating_margin": {
        "kind": "derived",
        "formula": "营业利润 / 营业收入（最新财年）",
        "deps": ["营业利润", "营业收入"],
    },
    "net_margin": {
        "kind": "derived",
        "formula": "归母净利润 / 营业收入（最新财年；亏损为负值）",
        "deps": ["归母净利润", "营业收入"],
    },
    "cash_and_equivalents": {
        "kind": "unavailable",
        "reason": "Wind 无'现金及等价物'canonical 列（xpev-wind.json balance 无现金字段）→ 标注未披露",
    },
    "interest_bearing_debt": {
        "kind": "unavailable",
        "reason": "Wind 无'有息负债'canonical 列 → 标注未披露（禁止启发式回填）",
    },
}


def resolve_financial_from_wind(wind_data: dict) -> tuple[dict, list[str]]:
    """按处置表从 Wind 解析全部 FinancialFacts 字段。

    Returns:
        (字段值 dict {field: float|None}, 标注列表)
    """
    from .canonical import get_series

    values: dict = {}
    annotations: list[str] = []

    def _latest(canonical: str):
        series = get_series(wind_data, canonical)
        if series and isinstance(series, list) and series:
            return series[-1]
        return None

    for field, disp in FINANCIAL_FIELD_DISPOSITION.items():
        kind = disp["kind"]
        if kind == "source":
            values[field] = _latest(disp["canonical"])
            if values[field] is None:
                annotations.append(f"{field}：Wind 无'{disp['canonical']}'数据（未披露）")
        elif kind == "derived":
            deps = [get_series(wind_data, c) for c in disp["deps"]]
            if all(d and isinstance(d, list) and d for d in deps):
                a, b = deps[0][-1], deps[1][-1]
                if b:
                    values[field] = a / b
                    annotations.append(f"{field}：派生（{disp['formula']}）")
                else:
                    values[field] = None
                    annotations.append(f"{field}：派生依赖营收为 0/缺失（未披露）")
            else:
                values[field] = None
                annotations.append(f"{field}：派生依赖缺失（{disp['deps']}）")
        else:  # unavailable
            values[field] = None
            annotations.append(f"{field}：{disp['reason']}")
    return values, annotations
