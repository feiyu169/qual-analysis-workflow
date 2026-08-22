"""
valuation_engine.py — Layer 3: 完整估值模块

功能：
1. DCF自动估值：FCF预测 + DCF + 敏感性
2. 可比公司分析：分层可比(核心+补充+分部)
3. 目标价推导：牛/基准/熊三情景
4. 降级链：full_dcf → comparable_only → pe_multiple
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ====================================================================
# 数据结构
# ====================================================================

@dataclass
class FCFProjection:
    """FCF预测"""
    year: int
    revenue: float           # 营收（亿人民币）
    revenue_growth: float    # 营收增速
    ebit_margin: float       # EBIT利润率
    ebit: float              # EBIT
    tax_rate: float          # 税率
    nopat: float             # 税后营业利润
    da: float                # 折旧摊销
    capex: float             # 资本开支
    wc_change: float         # 营运资金变动
    fcf: float               # 自由现金流


@dataclass
class DCFResult:
    """DCF估值结果"""
    fcf_projections: list[FCFProjection] = field(default_factory=list)
    wacc: float = 0.0
    terminal_growth: float = 0.0
    terminal_value: float = 0.0
    pv_fcf: float = 0.0
    pv_terminal: float = 0.0
    enterprise_value: float = 0.0
    equity_value: float = 0.0
    net_debt: float = 0.0
    value_per_share: float = 0.0
    sensitivity_matrix: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ComparableCompany:
    """可比公司"""
    name: str
    ticker: str
    pe: float | None = None
    pb: float | None = None
    ps: float | None = None
    ev_ebitda: float | None = None
    market_cap: float | None = None


@dataclass
class ValuationResult:
    """完整估值结果"""
    ticker: str
    company_name: str

    # DCF估值
    dcf: DCFResult | None = None

    # 可比公司
    comparable_companies: list[ComparableCompany] = field(default_factory=list)
    comparable_median_pe: float | None = None
    comparable_median_pb: float | None = None
    comparable_median_ps: float | None = None
    # 双专家 P0：可比数据是否为静态快照（True=默认静态池，报告应标注）
    comparables_static_snapshot: bool = True

    # 目标价
    target_price_bull: float | None = None
    target_price_base: float | None = None
    target_price_bear: float | None = None

    # 综合估值
    value_per_share: float | None = None
    upside: float | None = None  # 相对当前股价的上行空间

    # 降级信息
    degraded: bool = False
    degradation_reason: str = ""
    warnings: list[str] = field(default_factory=list)


# ====================================================================
# 可比公司（快手对标）
# ====================================================================

# 核心可比公司（在线阅读/数字内容行业）
# 双专家 P0（2026-08-22）：静态池保留但显式标注"静态快照"（非实时行情）；
# 调用方可传实时可比（core_comps/supplementary_comps 参数）
CORE_COMPARABLES = {
    "掌阅科技": {"ticker": "603533.SH", "pe": 25.0, "pb": 2.5, "ps": 3.0},
    "中文在线": {"ticker": "300364.SZ", "pe": 30.0, "pb": 3.0, "ps": 4.0},
    "阅文集团": {"ticker": "00772.HK", "pe": None, "pb": 1.17, "ps": 2.78},
}

# 补充可比公司（内容平台）
# 双专家 P0：移除迪士尼（行业错配——流媒体巨头非在线阅读可比，混入会扭曲 PE/PS 中位数）
SUPPLEMENTARY_COMPARABLES = {
    "B站": {"ticker": "9626.HK", "pe": None, "pb": 2.0, "ps": 2.5},
    "爱奇艺": {"ticker": "IQ", "pe": None, "pb": 1.5, "ps": 1.0},
}


# ====================================================================
# DCF 估值
# ====================================================================

def compute_dcf(
    financials: dict,
    shares: float,
    wacc: float = None,  # 使用CAPM计算
    terminal_growth: float = 0.02,
    projection_years: int = 5,
    revenue_growth_rates: list[float] | None = None,
    ebit_margins: list[float] | None = None,
) -> DCFResult:
    """
    计算DCF估值。

    Args:
        financials: Wind财务数据
        shares: 总股本（亿股）
        wacc: 加权平均资本成本（默认使用CAPM计算）
        terminal_growth: 永续增长率
        projection_years: 预测年数
        revenue_growth_rates: 营收增速假设列表
        ebit_margins: EBIT利润率假设列表

    Returns:
        DCFResult 估值结果
    """
    # 使用CAPM计算WACC（如果未提供）
    if wacc is None:
        rf = 0.023  # 无风险利率
        beta = 1.2  # Beta系数
        erp = 0.055  # 股权风险溢价
        ke = rf + beta * erp  # 0.089
        kd = 0.05  # 债务成本
        tax_rate = 0.25
        # 假设D/(D+E) = 15%
        wacc = ke * 0.85 + kd * (1 - tax_rate) * 0.15  # 0.081

    result = DCFResult(wacc=wacc, terminal_growth=terminal_growth)

    # 获取历史财务数据
    income = financials.get('income', {})
    balance = financials.get('balance', {})
    cashflow = financials.get('cashflow', {})  # noqa: F841

    rev_list = income.get('年营业总收入', [])
    if not rev_list or len(rev_list) < 1:
        result.warnings.append("缺少营收数据，无法进行DCF")
        return result

    base_revenue = rev_list[-1]  # 最新年份营收

    # 默认假设
    if revenue_growth_rates is None:
        # 基于历史3年CAGR
        if len(rev_list) >= 3 and rev_list[0] > 0:
            cagr = (rev_list[-1] / rev_list[0]) ** (1 / (len(rev_list) - 1)) - 1
            revenue_growth_rates = [cagr * 0.9, cagr * 0.8, cagr * 0.7, cagr * 0.6, cagr * 0.5]
        else:
            revenue_growth_rates = [0.12, 0.10, 0.08, 0.06, 0.05]

    if ebit_margins is None:
        # 基于营业利润计算EBIT利润率（而非净利润）
        op_list = income.get('年营业利润', [])
        if op_list and rev_list:
            latest_margin = op_list[-1] / rev_list[-1]
            if latest_margin < 0:
                # B2a-3：亏损公司 fail-fast——禁止 0.05 启发式回填（负 FCF 不输出无意义目标价）
                result.warnings.append(
                    "最新财年营业利润为负（亏损公司），DCF 不适用（fail-fast，"
                    "不采用启发式利润率假设；交由可比/PS 降级链）"
                )
                return result
            ebit_margins = [latest_margin * 1.0, latest_margin * 1.1, latest_margin * 1.2,
                           latest_margin * 1.2, latest_margin * 1.2]
        else:
            ebit_margins = [0.05, 0.06, 0.07, 0.07, 0.07]

    # B2a-3：净利润为负（亏损）但营业利润为正的罕见情形 → FCF 预测仍可能为负，
    # 终值若为负则 DCF 无意义 → fail-fast
    np_list = income.get('年净利润', [])
    if np_list and np_list[-1] < 0:
        result.warnings.append(
            "最新财年净利润为负（持续亏损），DCF 结果不可作为目标价依据（fail-fast 降级）"
        )

    # 计算折旧/资本开支比率
    da_ratio = 0.03  # 默认
    capex_ratio = 0.04  # 默认
    wc_ratio = 0.02  # 默认

    # FCF预测
    revenue = base_revenue
    for i in range(projection_years):
        year = 2026 + i
        growth = revenue_growth_rates[min(i, len(revenue_growth_rates) - 1)]
        margin = ebit_margins[min(i, len(ebit_margins) - 1)]

        revenue = revenue * (1 + growth)
        ebit = revenue * margin
        tax_rate = 0.25
        nopat = ebit * (1 - tax_rate)
        da = revenue * da_ratio
        capex = revenue * capex_ratio
        wc_change = revenue * growth * wc_ratio
        fcf = nopat + da - capex - wc_change

        result.fcf_projections.append(FCFProjection(
            year=year,
            revenue=round(revenue, 2),
            revenue_growth=round(growth, 4),
            ebit_margin=round(margin, 4),
            ebit=round(ebit, 2),
            tax_rate=tax_rate,
            nopat=round(nopat, 2),
            da=round(da, 2),
            capex=round(capex, 2),
            wc_change=round(wc_change, 2),
            fcf=round(fcf, 2),
        ))

    # 终值
    last_fcf = result.fcf_projections[-1].fcf
    if wacc > terminal_growth:
        result.terminal_value = last_fcf * (1 + terminal_growth) / (wacc - terminal_growth)
    else:
        result.warnings.append("WACC <= 永续增长率，终值计算异常")
        result.terminal_value = 0

    # 折现
    for i, proj in enumerate(result.fcf_projections):
        discount_factor = 1 / (1 + wacc) ** (i + 1)
        result.pv_fcf += proj.fcf * discount_factor

    terminal_discount = 1 / (1 + wacc) ** projection_years
    result.pv_terminal = result.terminal_value * terminal_discount

    # 企业价值
    result.enterprise_value = result.pv_fcf + result.pv_terminal

    # 净负债
    debt_list = balance.get('年负债合计', [])
    cash_list = balance.get('现金及等价物', [])
    if not cash_list:
        # 备用：使用流动资产合计
        cash_list = balance.get('年流动资产合计', [])
    if debt_list and cash_list:
        result.net_debt = debt_list[-1] - cash_list[-1]

    # 权益价值
    result.equity_value = result.enterprise_value - result.net_debt

    # 每股价值
    if shares > 0:
        result.value_per_share = result.equity_value / shares

    # 敏感性分析
    result.sensitivity_matrix = _compute_sensitivity(
        result.fcf_projections, terminal_growth, wacc, result.net_debt, shares
    )

    logger.info(
        f"DCF完成: EV={result.enterprise_value:.0f}亿, "
        f"每股={result.value_per_share:.1f}元"
    )

    return result


def _compute_sensitivity(
    fcf_projections: list[FCFProjection],
    base_tg: float,
    base_wacc: float,
    net_debt: float,
    shares: float,
) -> dict:
    """计算敏感性矩阵"""
    matrix = {}

    for wacc_delta in [-0.02, -0.01, 0, 0.01, 0.02]:
        wacc = base_wacc + wacc_delta
        if wacc <= 0.01:
            continue

        for tg_delta in [-0.02, -0.01, 0, 0.01, 0.02]:
            tg = base_tg + tg_delta
            if tg >= wacc:
                continue

            # 简化计算
            pv_fcf = 0
            for i, proj in enumerate(fcf_projections):
                discount_factor = 1 / (1 + wacc) ** (i + 1)
                pv_fcf += proj.fcf * discount_factor

            last_fcf = fcf_projections[-1].fcf
            terminal_value = last_fcf * (1 + tg) / (wacc - tg)
            pv_terminal = terminal_value / (1 + wacc) ** len(fcf_projections)

            ev = pv_fcf + pv_terminal
            equity = ev - net_debt
            per_share = equity / shares if shares > 0 else 0

            key = f"WACC={wacc:.1%},TG={tg:.1%}"
            matrix[key] = round(per_share, 1)

    return matrix


# ====================================================================
# 可比公司分析
# ====================================================================

def build_comparable_analysis(
    core_comps: dict | None = None,
    supplementary_comps: dict | None = None,
) -> tuple[list[ComparableCompany], dict]:
    """
    构建可比公司分析。

    Returns:
        (可比公司列表, 中位数字典)——中位数含 static_snapshot 标记：
        使用默认静态池 → True（报告应标注"可比数据为静态快照"）；
        调用方传入实时可比 → False
    """
    companies = []
    # 双专家 P0：静态池使用标记（无实时行情时诚实标注，不冒充实时估值）
    use_static = (core_comps is None) and (supplementary_comps is None)

    # 核心可比
    comp_data = core_comps or CORE_COMPARABLES
    for name, data in comp_data.items():
        companies.append(ComparableCompany(
            name=name,
            ticker=data.get('ticker', ''),
            pe=data.get('pe'),
            pb=data.get('pb'),
            ps=data.get('ps'),
        ))

    # 补充可比
    supp_data = supplementary_comps or SUPPLEMENTARY_COMPARABLES
    for name, data in supp_data.items():
        companies.append(ComparableCompany(
            name=name,
            ticker=data.get('ticker', ''),
            pe=data.get('pe'),
            pb=data.get('pb'),
            ps=data.get('ps'),
        ))

    # 计算中位数
    pe_values = [c.pe for c in companies if c.pe is not None]
    pb_values = [c.pb for c in companies if c.pb is not None]
    ps_values = [c.ps for c in companies if c.ps is not None]

    medians = {}
    if pe_values:
        medians['pe'] = sorted(pe_values)[len(pe_values) // 2]
    if pb_values:
        medians['pb'] = sorted(pb_values)[len(pb_values) // 2]
    if ps_values:
        medians['ps'] = sorted(ps_values)[len(ps_values) // 2]
    medians['static_snapshot'] = use_static

    return companies, medians


# ====================================================================
# 目标价推导
# ====================================================================

def derive_target_prices(
    dcf_value: float | None,
    comparable_pe: float | None,
    current_price: float,
    eps: float | None = None,
    revenue_per_share: float | None = None,
    shares: float = 1.0,
    comparable_ps: float | None = None,
) -> dict:
    """
    推导牛/基准/熊三情景目标价。

    Returns:
        {"bull": X, "base": Y, "bear": Z}
    """
    targets = {}

    # 基准情景：DCF估值
    if dcf_value:
        targets['base'] = dcf_value

    # 牛市情景：DCF + 20% 或 可比公司PE上限（eps>0 才可用——亏损公司负 EPS 无意义）
    if dcf_value:
        targets['bull'] = dcf_value * 1.20
    elif comparable_pe and eps and eps > 0:
        targets['bull'] = comparable_pe * 1.2 * eps

    # 熊市情景：DCF - 20% 或 可比公司PE下限（B2a-3：eps<=0 时不用 PE 推算负目标价）
    if dcf_value:
        targets['bear'] = dcf_value * 0.80
    elif comparable_pe and eps and eps > 0:
        targets['bear'] = comparable_pe * 0.8 * eps

    return targets


# ====================================================================
# 主估值流程
# ====================================================================

def compute_full_valuation(
    ticker: str,
    company_name: str,
    financials: dict,
    shares: float,
    current_price: float,
    wacc: float = None,  # 使用CAPM计算
    terminal_growth: float = 0.02,
) -> ValuationResult:
    """
    执行完整估值流程（带降级链）。

    降级链: full_dcf → comparable_only → pe_multiple

    注（双专家 P2，2026-08-22）：SOTP 分部估值（quality/sotp_valuation.py）引擎存在且
    有测试，但**未接入本主流程**——需要分部财务数据（Wind 无分部粒度）。
    多业务公司如需分部估值，应另行调用 sotp_valuation（当前报告不声称 SOTP 结果）。
    """
    result = ValuationResult(ticker=ticker, company_name=company_name)

    # === Step 1: DCF估值 ===
    try:
        result.dcf = compute_dcf(
            financials=financials,
            shares=shares,
            wacc=wacc,
            terminal_growth=terminal_growth,
        )
        result.warnings.extend(result.dcf.warnings)
        if result.dcf.value_per_share > 0:
            result.value_per_share = result.dcf.value_per_share
        elif result.dcf.warnings:
            # B2a-3：亏损公司 DCF fail-fast → 降级链
            result.degraded = True
            result.degradation_reason = "亏损公司，DCF 不适用（fail-fast）"
    except Exception as e:
        logger.warning(f"DCF估值失败: {e}")
        result.warnings.append(f"DCF失败: {e}")

    # === Step 2: 可比公司分析 ===
    try:
        result.comparable_companies, medians = build_comparable_analysis()
        result.comparable_median_pe = medians.get('pe')
        result.comparable_median_pb = medians.get('pb')
        result.comparable_median_ps = medians.get('ps')
        result.comparables_static_snapshot = medians.get('static_snapshot', True)

        income = financials.get('income', {})
        np_list = income.get('年净利润', [])
        rev_list = income.get('年营业总收入', [])

        # B2a-3：亏损公司（eps<=0）不用 PE 法（负 EPS 无意义），降级 PS 法（市销率）
        eps = (np_list[-1] / shares) if (np_list and shares > 0) else None

        # 如果DCF失败/不适用，用可比公司估值（PE 仅盈利公司；亏损公司用 PS）
        if result.value_per_share is None:
            if eps is not None and eps > 0 and result.comparable_median_pe:
                result.value_per_share = result.comparable_median_pe * eps
                result.degraded = True
                result.degradation_reason = "DCF失败/不适用，使用可比公司PE"
            elif result.comparable_median_ps and rev_list and shares > 0:
                revenue_per_share = rev_list[-1] / shares
                if revenue_per_share > 0:
                    result.value_per_share = result.comparable_median_ps * revenue_per_share
                    result.degraded = True
                    result.degradation_reason = "亏损公司，DCF/PE 不适用，使用可比公司PS（市销率）"
    except Exception as e:
        logger.warning(f"可比公司分析失败: {e}")
        result.warnings.append(f"可比公司失败: {e}")

    # === Step 3: 目标价推导 ===
    try:
        eps = None
        income = financials.get('income', {})
        np_list = income.get('年净利润', [])
        if np_list and shares > 0:
            eps = np_list[-1] / shares

        targets = derive_target_prices(
            dcf_value=result.value_per_share,
            comparable_pe=result.comparable_median_pe,
            current_price=current_price,
            eps=eps,
            shares=shares,
        )
        result.target_price_bull = targets.get('bull')
        result.target_price_base = targets.get('base')
        result.target_price_bear = targets.get('bear')
    except Exception as e:
        logger.warning(f"目标价推导失败: {e}")
        result.warnings.append(f"目标价失败: {e}")

    # === 计算上行空间 ===
    if result.value_per_share and current_price > 0:
        result.upside = (result.value_per_share - current_price) / current_price

    logger.info(
        f"估值完成: 每股={result.value_per_share}, "
        f"目标价(牛/基/熊)={result.target_price_bull}/{result.target_price_base}/{result.target_price_bear}, "
        f"上行空间={result.upside:.1%}" if result.upside else "估值完成"
    )

    return result


def format_valuation_for_report(vr: ValuationResult) -> str:
    """将估值结果格式化为报告内容"""
    lines = [f"## {vr.company_name} ({vr.ticker}) 估值分析"]
    lines.append("")

    # DCF估值
    if vr.dcf and vr.dcf.value_per_share > 0:
        lines.append("### DCF估值")
        lines.append(f"- WACC: {vr.dcf.wacc:.1%}")
        lines.append(f"- 永续增长率: {vr.dcf.terminal_growth:.1%}")
        lines.append(f"- 企业价值: {vr.dcf.enterprise_value:.0f}亿元")
        lines.append(f"- 每股内在价值: {vr.dcf.value_per_share:.1f}元")
        lines.append("")

    # 可比公司
    if vr.comparable_companies:
        lines.append("### 可比公司估值")
        lines.append("| 公司 | PE | PB | PS |")
        lines.append("|------|-----|-----|-----|")
        for comp in vr.comparable_companies:
            pe = f"{comp.pe:.1f}x" if comp.pe else "N/A"
            pb = f"{comp.pb:.1f}x" if comp.pb else "N/A"
            ps = f"{comp.ps:.1f}x" if comp.ps else "N/A"
            lines.append(f"| {comp.name} | {pe} | {pb} | {ps} |")
        if vr.comparable_median_pe:
            lines.append(f"| **中位数** | **{vr.comparable_median_pe:.1f}x** | **{vr.comparable_median_pb:.1f}x** | **{vr.comparable_median_ps:.1f}x** |")
        # 双专家 P0：静态快照显式标注（不冒充实时行情）
        if getattr(vr, "comparables_static_snapshot", True):
            lines.append("")
            lines.append("> ⚠️ 可比公司倍数为**静态快照**（非实时行情），仅作方向参考；"
                         "实时估值应由 Wind MCP 提供可比倍数后更新")
        lines.append("")

    # 目标价
    if vr.target_price_bull:
        lines.append("### 目标价推导")
        lines.append(f"- 牛市情景: {vr.target_price_bull:.1f}元")
        lines.append(f"- 基准情景: {vr.target_price_base:.1f}元")
        lines.append(f"- 熊市情景: {vr.target_price_bear:.1f}元")
        lines.append("")

    # 上行空间
    if vr.upside is not None:
        direction = "上行" if vr.upside > 0 else "下行"
        lines.append(f"**{direction}空间**: {abs(vr.upside):.1%}")

    return "\n".join(lines)


# ====================================================================
# T13: 反向估值（DCF反推 + PE反推）
# ====================================================================

def implied_growth_from_dcf(
    current_price: float,
    shares: float,
    fcf_base: float,
    wacc: float = 0.08,
    terminal_growth: float = 0.03,
    projection_years: int = 5,
    net_debt: float = 0.0,
) -> dict:
    """DCF反推隐含FCF增长率

    假设当前股价合理，反推隐含的FCF增长率。
    使用二分法搜索。

    Args:
        current_price: 当前股价（元）
        shares: 总股本（亿股）
        fcf_base: 基准FCF（亿元）
        wacc: WACC（默认8%）
        terminal_growth: 永续增长率（默认3%）
        projection_years: 预测年数（默认5年）
        net_debt: 净负债（亿元）

    Returns:
        {
            "implied_growth": 隐含增长率,
            "method": "DCF反推",
            "assumptions": {...}
        }
    """
    if current_price <= 0 or shares <= 0 or fcf_base <= 0:
        return {"implied_growth": 0, "method": "DCF反推", "error": "输入参数无效"}

    # 目标企业价值
    target_ev = current_price * shares + net_debt

    # 二分法搜索隐含增长率
    low, high = -0.5, 1.0  # 增长率范围：-50% 到 100%
    tolerance = 0.001
    max_iterations = 100

    for _ in range(max_iterations):
        mid = (low + high) / 2

        # 计算FCF现值
        fcf_pv = 0
        for i in range(projection_years):
            fcf = fcf_base * (1 + mid) ** (i + 1)
            fcf_pv += fcf / (1 + wacc) ** (i + 1)

        # 计算终值
        last_fcf = fcf_base * (1 + mid) ** projection_years
        next_fcf = last_fcf * (1 + terminal_growth)
        if wacc <= terminal_growth:
            terminal_value = 0
        else:
            terminal_value = next_fcf / (wacc - terminal_growth)
        terminal_value_pv = terminal_value / (1 + wacc) ** projection_years

        # 企业价值
        ev = fcf_pv + terminal_value_pv

        if abs(ev - target_ev) < tolerance:
            break

        if ev < target_ev:
            low = mid
        else:
            high = mid

    implied_growth = (low + high) / 2

    return {
        "implied_growth": implied_growth,
        "implied_growth_pct": f"{implied_growth:.1%}",
        "method": "DCF反推",
        "target_ev": target_ev,
        "assumptions": {
            "wacc": wacc,
            "terminal_growth": terminal_growth,
            "projection_years": projection_years,
            "fcf_base": fcf_base,
        }
    }


def implied_growth_from_pe(
    pe: float,
    roe: float,
    retention_rate: float = 0.6,
) -> dict:
    """PE反推隐含增长率（Gordon Growth Model）

    g = k - (1-b)/PE
    但需要已知k（折现率），这里用ROE×b作为基本面可持续增速参考

    Args:
        pe: PE倍数
        roe: ROE（%）
        retention_rate: 留存收益比例（默认60%）

    Returns:
        {
            "sustainable_growth": 基本面可持续增速,
            "method": "PE+ROE",
            "note": "说明"
        }
    """
    # 基本面可持续增速 = ROE × 留存率
    sustainable_growth = (roe / 100) * retention_rate

    return {
        "sustainable_growth": sustainable_growth,
        "sustainable_growth_pct": f"{sustainable_growth:.1%}",
        "method": "PE+ROE反推",
        "note": f"基本面可持续增速 = ROE {roe}% × 留存率 {retention_rate:.0%} = {sustainable_growth:.1%}。"
               f"市场隐含增速需已知折现率k，建议用DCF反推。",
        "assumptions": {
            "pe": pe,
            "roe": roe,
            "retention_rate": retention_rate,
        }
    }


# ====================================================================
# T2: 可比公司估值增强
# ====================================================================

def compute_comparable_valuation(
    target_ticker: str,
    comparable_companies: list[dict],
    target_eps: float = 0.0,
    target_bvps: float = 0.0,
) -> dict:
    """可比公司估值计算

    Args:
        target_ticker: 目标公司代码
        comparable_companies: 可比公司列表 [{"name": str, "pe": float, "pb": float, "ps": float}]
        target_eps: 目标公司每股收益
        target_bvps: 目标公司每股净资产

    Returns:
        {
            "pe_median": PE中位数,
            "pe_range": (25分位, 75分位),
            "implied_value_pe": PE隐含估值,
            "implied_value_pb": PB隐含估值,
            "summary": "估值摘要"
        }
    """
    pe_values = [c["pe"] for c in comparable_companies if c.get("pe") and c["pe"] > 0]
    pb_values = [c["pb"] for c in comparable_companies if c.get("pb") and c["pb"] > 0]
    ps_values = [c["ps"] for c in comparable_companies if c.get("ps") and c["ps"] > 0]  # noqa: F841

    result = {"method": "可比公司法", "companies_count": len(comparable_companies)}

    if pe_values:
        pe_sorted = sorted(pe_values)
        pe_median = pe_sorted[len(pe_sorted) // 2]
        pe_q1 = pe_sorted[len(pe_sorted) // 4]
        pe_q3 = pe_sorted[3 * len(pe_sorted) // 4]

        result["pe_median"] = pe_median
        result["pe_range"] = (pe_q1, pe_q3)
        if target_eps > 0:
            result["implied_value_pe"] = pe_median * target_eps

    if pb_values:
        pb_sorted = sorted(pb_values)
        pb_median = pb_sorted[len(pb_sorted) // 2]
        result["pb_median"] = pb_median
        if target_bvps > 0:
            result["implied_value_pb"] = pb_median * target_bvps

    # 估值摘要
    summary_parts = []
    if "implied_value_pe" in result:
        summary_parts.append(f"PE法: {result['implied_value_pe']:.1f}元")
    if "implied_value_pb" in result:
        summary_parts.append(f"PB法: {result['implied_value_pb']:.1f}元")
    result["summary"] = "可比公司估值: " + ", ".join(summary_parts) if summary_parts else "无可比数据"

    return result
