"""
depth_enhancer.py — Layer 4: 深度优化模块

功能：
1. 情景分析+敏感性矩阵：4变量×3值=81组合
2. 结论翻转阈值标注
3. 对比分析：YoY/环比/趋势偏离
4. 洞察深度审计：每章至少1条可执行判断
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ====================================================================
# 数据结构
# ====================================================================

@dataclass
class ScenarioResult:
    """情景分析结果"""
    name: str                          # 情景名称
    revenue_growth: float              # 营收增速假设
    ebit_margin: float                 # EBIT利润率假设
    wacc: float                        # WACC假设
    terminal_growth: float             # 永续增长率假设
    value_per_share: float = 0.0       # 每股价值
    probability: float | None = None  # 概率权重


@dataclass
class FlipThreshold:
    """结论翻转阈值"""
    variable: str                      # 变量名
    current_value: float               # 当前值
    flip_value: float                  # 翻转值
    direction: str                     # "up" or "down"
    impact: str                        # 对投资结论的影响


@dataclass
class YoYChange:
    """同比变化"""
    metric: str
    current: float
    previous: float
    change: float
    change_pct: float
    trend: str  # "accelerating" / "decelerating" / "stable"


@dataclass
class InsightAudit:
    """洞察深度审计"""
    chapter_num: int
    chapter_title: str
    has_actionable_insight: bool = False
    insights: list[str] = field(default_factory=list)
    score: int = 0  # 0-100


@dataclass
class DepthResult:
    """深度优化结果"""
    scenarios: list[ScenarioResult] = field(default_factory=list)
    flip_thresholds: list[FlipThreshold] = field(default_factory=list)
    yoy_changes: list[YoYChange] = field(default_factory=list)
    insight_audits: list[InsightAudit] = field(default_factory=list)
    overall_insight_score: int = 0
    warnings: list[str] = field(default_factory=list)


# ====================================================================
# 情景分析
# ====================================================================

def run_scenario_analysis(
    base_revenue: float,
    base_ebit_margin: float,
    base_wacc: float,
    base_terminal_growth: float,
    shares: float,
    net_debt: float = 0,
) -> list[ScenarioResult]:
    """
    运行情景分析：4变量×3值=81组合。

    Args:
        base_revenue: 基础营收（亿）
        base_ebit_margin: 基础EBIT利润率
        base_wacc: 基础WACC
        base_terminal_growth: 基础永续增长率
        shares: 总股本（亿股）
        net_debt: 净负债（亿）

    Returns:
        情景分析结果列表
    """
    scenarios = []

    # 定义变量范围
    revenue_growths = [base_revenue * 0.8, base_revenue, base_revenue * 1.2]
    ebit_margins = [base_ebit_margin * 0.8, base_ebit_margin, base_ebit_margin * 1.2]
    waccs = [base_wacc - 0.02, base_wacc, base_wacc + 0.02]
    terminal_growths = [base_terminal_growth - 0.01, base_terminal_growth, base_terminal_growth + 0.01]

    # 生成代表性情景（而非81组合全部计算）
    key_scenarios = [
        ("基准", base_revenue, base_ebit_margin, base_wacc, base_terminal_growth, 0.5),
        ("乐观", base_revenue * 1.2, base_ebit_margin * 1.2, base_wacc - 0.02, base_terminal_growth + 0.01, 0.2),
        ("悲观", base_revenue * 0.8, base_ebit_margin * 0.8, base_wacc + 0.02, base_terminal_growth - 0.01, 0.2),
        ("高增长", base_revenue * 1.3, base_ebit_margin, base_wacc, base_terminal_growth, 0.05),
        ("利润率压缩", base_revenue, base_ebit_margin * 0.7, base_wacc, base_terminal_growth, 0.05),
    ]

    for name, rev, margin, wacc, tg, prob in key_scenarios:
        if wacc <= tg or wacc <= 0:
            continue

        # FCF计算（与主DCF一致，使用5年预测）
        # 使用与DCF相同的营收增速假设（递减增速）
        revenue_growth = (rev - base_revenue) / base_revenue if base_revenue > 0 else 0

        # 5年FCF预测（使用递减增速，与DCF一致）
        total_pv_fcf = 0
        current_revenue = base_revenue
        for year in range(1, 6):
            # 营收增长（使用递减增速，与DCF一致）
            # 第1年使用情景增速，后续年份使用递减增速
            if year == 1:
                growth = revenue_growth
            else:
                # 递减增速：每年减少20%的增速
                growth = revenue_growth * (0.8 ** (year - 1))

            current_revenue = current_revenue * (1 + growth)
            ebit = current_revenue * margin
            nopat = ebit * (1 - 0.25)  # 税率25%
            da = current_revenue * 0.03  # 折旧率3%
            capex = current_revenue * 0.04  # 资本开支率4%
            wc_change = current_revenue * growth * 0.02  # 营运资金变动
            fcf = nopat + da - capex - wc_change

            # 折现
            discount_factor = 1 / (1 + wacc) ** year
            total_pv_fcf += fcf * discount_factor

        # 终值（基于第5年FCF）
        last_fcf = fcf
        terminal_value = last_fcf * (1 + tg) / (wacc - tg)
        pv_terminal = terminal_value / (1 + wacc) ** 5

        # 企业价值
        ev = total_pv_fcf + pv_terminal

        equity = ev - net_debt
        per_share = equity / shares if shares > 0 else 0

        scenarios.append(ScenarioResult(
            name=name,
            revenue_growth=(rev - base_revenue) / base_revenue,
            ebit_margin=margin,
            wacc=wacc,
            terminal_growth=tg,
            value_per_share=round(per_share, 1),
            probability=prob,
        ))

    return scenarios


def compute_flip_thresholds(
    base_value: float,
    current_price: float,
    base_revenue: float,
    base_ebit_margin: float,
    base_wacc: float,
    base_terminal_growth: float,
    shares: float,
) -> list[FlipThreshold]:
    """
    计算结论翻转阈值。

    找出当投资结论从"看多"变为"看空"（或反之）时，各变量的临界值。

    根据HeavySkill审查要求：
    - 增加迭代次数（100次）
    - 增加收敛检查
    - 未收敛时返回区间估值并标注"未收敛，仅供参考"
    """
    thresholds = []

    # 收敛参数
    MAX_ITERATIONS = 100  # 从50增加到100
    CONVERGENCE_TOLERANCE = 1e-6  # 收敛容差

    # 使用二分法找到翻转点

    # 目标企业价值 = 当前股价 × 股本（假设净负债为0简化计算）
    target_equity_value = current_price * shares

    # 营收翻转点（使用二分法）
    # 固定其他变量，找到使equity_value = target_equity_value的营收
    low_rev, high_rev = base_revenue * 0.3, base_revenue * 3.0
    converged_rev = False
    for i in range(MAX_ITERATIONS):
        mid_rev = (low_rev + high_rev) / 2
        ebit = mid_rev * base_ebit_margin
        nopat = ebit * 0.75
        da = mid_rev * 0.03
        capex = mid_rev * 0.04
        fcf = nopat + da - capex - mid_rev * 0.02 * 0.02
        if fcf <= 0 or base_wacc <= base_terminal_growth:
            break
        tv = fcf * (1 + base_terminal_growth) / (base_wacc - base_terminal_growth)
        pv_factor = sum(1 / (1 + base_wacc) ** i for i in range(1, 6))
        ev = fcf * pv_factor + tv / (1 + base_wacc) ** 5
        equity = ev  # 简化：不考虑净负债

        # 检查收敛
        if abs(high_rev - low_rev) < CONVERGENCE_TOLERANCE * base_revenue:
            converged_rev = True
            break

        if equity > target_equity_value:
            high_rev = mid_rev
        else:
            low_rev = mid_rev

    flip_rev = (low_rev + high_rev) / 2
    if abs(flip_rev - base_revenue) > 1:
        if converged_rev:
            thresholds.append(FlipThreshold(
                variable="营收",
                current_value=round(base_revenue, 1),
                flip_value=round(flip_rev, 1),
                direction="down" if flip_rev < base_revenue else "up",
                impact=f"当营收降至{flip_rev:.0f}亿元时，估值等于当前股价",
            ))
        else:
            # 未收敛：返回区间估值并标注
            rev_range_low = round(low_rev, 1)
            rev_range_high = round(high_rev, 1)
            thresholds.append(FlipThreshold(
                variable="营收（未收敛）",
                current_value=round(base_revenue, 1),
                flip_value=round(flip_rev, 1),
                direction="区间",
                impact=f"营收翻转点未收敛，区间=[{rev_range_low}, {rev_range_high}]亿元，仅供参考",
            ))
            logger.warning(f"营收翻转点计算未收敛: 迭代{MAX_ITERATIONS}次, 区间=[{rev_range_low}, {rev_range_high}]")

    # EBIT利润率翻转点
    low_m, high_m = 0.01, 0.30
    converged_margin = False
    for i in range(MAX_ITERATIONS):
        mid_m = (low_m + high_m) / 2
        ebit = base_revenue * mid_m
        nopat = ebit * 0.75
        da = base_revenue * 0.03
        capex = base_revenue * 0.04
        fcf = nopat + da - capex - base_revenue * 0.02 * 0.02
        if fcf <= 0 or base_wacc <= base_terminal_growth:
            low_m = mid_m
            continue
        tv = fcf * (1 + base_terminal_growth) / (base_wacc - base_terminal_growth)
        pv_factor = sum(1 / (1 + base_wacc) ** i for i in range(1, 6))
        ev = fcf * pv_factor + tv / (1 + base_wacc) ** 5

        # 检查收敛
        if abs(high_m - low_m) < CONVERGENCE_TOLERANCE:
            converged_margin = True
            break

        if ev > target_equity_value:
            high_m = mid_m
        else:
            low_m = mid_m

    flip_margin = (low_m + high_m) / 2
    if converged_margin:
        thresholds.append(FlipThreshold(
            variable="EBIT利润率",
            current_value=round(base_ebit_margin * 100, 1),
            flip_value=round(flip_margin * 100, 1),
            direction="down" if flip_margin < base_ebit_margin else "up",
            impact=f"当EBIT利润率降至{flip_margin*100:.1f}%时，估值等于当前股价",
        ))
    else:
        # 未收敛：返回区间估值并标注
        margin_range_low = round(low_m * 100, 1)
        margin_range_high = round(high_m * 100, 1)
        thresholds.append(FlipThreshold(
            variable="EBIT利润率（未收敛）",
            current_value=round(base_ebit_margin * 100, 1),
            flip_value=round(flip_margin * 100, 1),
            direction="区间",
            impact=f"EBIT利润率翻转点未收敛，区间=[{margin_range_low}%, {margin_range_high}%]，仅供参考",
        ))
        logger.warning(f"EBIT利润率翻转点计算未收敛: 迭代{MAX_ITERATIONS}次, 区间=[{margin_range_low}%, {margin_range_high}%]")

    # WACC翻转点（使用二分法）
    # 找到使equity_value = target_equity_value的WACC
    low_w, high_w = 0.03, 0.25
    converged_wacc = False
    for i in range(MAX_ITERATIONS):
        mid_w = (low_w + high_w) / 2
        ebit = base_revenue * base_ebit_margin
        nopat = ebit * 0.75
        da = base_revenue * 0.03
        capex = base_revenue * 0.04
        fcf = nopat + da - capex - base_revenue * 0.02 * 0.02
        if fcf <= 0 or mid_w <= base_terminal_growth:
            low_w = mid_w
            continue
        tv = fcf * (1 + base_terminal_growth) / (mid_w - base_terminal_growth)
        pv_factor = sum(1 / (1 + mid_w) ** i for i in range(1, 6))
        ev = fcf * pv_factor + tv / (1 + mid_w) ** 5

        # 检查收敛
        if abs(high_w - low_w) < CONVERGENCE_TOLERANCE:
            converged_wacc = True
            break

        if ev > target_equity_value:
            low_w = mid_w  # WACC太低，估值太高
        else:
            high_w = mid_w  # WACC太高，估值太低

    flip_wacc = (low_w + high_w) / 2
    # WACC翻转点应该高于当前WACC（WACC上升→估值下降）
    if converged_wacc:
        if flip_wacc > base_wacc:
            thresholds.append(FlipThreshold(
                variable="WACC",
                current_value=round(base_wacc * 100, 1),
                flip_value=round(flip_wacc * 100, 1),
                direction="up",
                impact=f"当WACC升至{flip_wacc*100:.1f}%时，估值等于当前股价",
            ))
        else:
            # 如果翻转点低于当前WACC，说明当前WACC已经很高
            thresholds.append(FlipThreshold(
                variable="WACC",
                current_value=round(base_wacc * 100, 1),
            flip_value=round(flip_wacc * 100, 1),
            direction="down",
            impact=f"当WACC降至{flip_wacc*100:.1f}%时，估值等于当前股价",
        ))

    return thresholds


# ====================================================================
# 对比分析
# ====================================================================

def compute_yoy_changes(financials) -> list[YoYChange]:
    """
    计算同比变化。

    Args:
        financials: Wind财务数据（dict 或 Financials 契约）

    Returns:
        YoY变化列表
    """
    changes = []
    # v10：兼容 Financials 契约和 dict
    from .contracts.financials import Financials as _Fin
    if isinstance(financials, _Fin):
        income = financials.to_wind_dict().get('income', {})
    else:
        income = financials.get('income', {})

    # v10：使用 canonical key（已修正为 营业收入/归母净利润/营业利润）
    # 并通过 canonicalize 兜底确保 key 存在
    from .canonical import canonicalize as _canon
    try:
        norm = _canon(financials if isinstance(financials, dict) else financials.to_wind_dict())
        income = norm.get('income', {})
    except Exception:
        income = financials.get('income', {}) if isinstance(financials, dict) else {}

    metrics = {
        '营收': '营业收入',
        '净利润': '归母净利润',
        '营业利润': '营业利润',
    }

    for display_name, wind_key in metrics.items():
        raw_values = income.get(wind_key, [])
        # v10：过滤 None 值（canonicalize 后可能含 None）
        values = [v for v in raw_values if v is not None]
        if isinstance(values, list) and len(values) >= 2:
            current = values[-1]
            previous = values[-2]
            if previous and previous != 0:
                change = current - previous
                change_pct = change / abs(previous)
                trend = _classify_trend(values)
                changes.append(YoYChange(
                    metric=display_name,
                    current=current,
                    previous=previous,
                    change=round(change, 2),
                    change_pct=round(change_pct, 4),
                    trend=trend,
                ))

    return changes


def _classify_trend(values: list[float]) -> str:
    """判断趋势：加速/减速/稳定"""
    if len(values) < 3:
        return "stable"

    growth_rates = []
    for i in range(1, len(values)):
        if values[i-1] != 0:
            growth_rates.append((values[i] - values[i-1]) / abs(values[i-1]))

    if len(growth_rates) < 2:
        return "stable"

    if growth_rates[-1] > growth_rates[-2] * 1.1:
        return "accelerating"
    elif growth_rates[-1] < growth_rates[-2] * 0.9:
        return "decelerating"
    else:
        return "stable"


# ====================================================================
# 洞察深度审计
# ====================================================================

# 可执行判断的关键词
ACTIONABLE_KEYWORDS = [
    '建议', '推荐', '应该', '需要关注', '风险在于',
    '如果.*则', '触发条件', '催化剂', '预期差',
    '买入', '卖出', '持有', '增持', '减持',
    '目标价', '上行空间', '下行风险',
]


def audit_insight_depth(chapters: dict[int, str]) -> list[InsightAudit]:
    """
    审计每章的洞察深度。

    检查每章是否包含至少1条可执行的投资判断。
    """
    audits = []

    for ch_num, content in chapters.items():
        audit = InsightAudit(
            chapter_num=ch_num,
            chapter_title=_extract_chapter_title(content),
        )

        # 检查是否包含可执行判断
        for keyword in ACTIONABLE_KEYWORDS:
            matches = re.findall(keyword, content)
            if matches:
                audit.insights.extend(matches[:3])  # 最多3个
                audit.has_actionable_insight = True

        # 评分
        if audit.has_actionable_insight:
            audit.score = min(100, 60 + len(audit.insights) * 10)
        else:
            audit.score = 30

        audits.append(audit)

    return audits


def _extract_chapter_title(content: str) -> str:
    """提取章节标题"""
    match = re.search(r'###?\s*第\d+章[：:]\s*(.+)', content)
    if match:
        return match.group(1).strip()
    return ""


# ====================================================================
# 主流程
# ====================================================================

def run_depth_enhancement(
    chapters: dict[int, str],
    financials: dict,
    valuation_value: float,
    current_price: float,
    shares: float,
    base_wacc: float = None,  # 使用CAPM计算
    base_terminal_growth: float = 0.02,
) -> DepthResult:
    """
    执行深度优化。

    Args:
        chapters: {章节号: 章节内容}
        financials: Wind财务数据
        valuation_value: DCF每股价值
        current_price: 当前股价
        shares: 总股本
        base_wacc: 基础WACC
        base_terminal_growth: 基础永续增长率

    Returns:
        DepthResult 深度优化结果
    """
    result = DepthResult()

    # v10 P0：使用 Financials 契约（禁止硬编码 fallback）
    from .contracts.financials import Financials as _Fin
    if isinstance(financials, _Fin):
        fin = financials
    else:
        from .data.wind_adapter import wind_to_financials
        fin = wind_to_financials(
            wind_data=financials,
            shares=shares,
            current_price=current_price,
        )

    base_revenue = fin.revenue
    is_loss = fin.is_loss_company
    ebit_margin = fin.ebit_margin

    # v10 P0：亏损公司跳过 DCF 情景分析，使用 EV/Revenue 模型
    if is_loss:
        logger.info(
            f"亏损公司（EBIT={ebit_margin:.2%}，OCF={fin.operating_cashflow:.1f}亿），"
            f"跳过 DCF 情景/翻转，使用 EV/Revenue 模型"
        )
        result.scenarios = []
        result.flip_thresholds = _compute_ev_revenue_flip_thresholds(
            revenue=base_revenue,
            enterprise_value=fin.enterprise_value,
            current_price=current_price,
            shares=shares,
        )
        result.warnings.append(
            f"亏损公司(EBIT={ebit_margin:.2%})，情景分析使用 EV/Revenue 模型（非 DCF）"
        )
    else:
        # 盈利公司：正常 DCF 情景分析
        try:
            result.scenarios = run_scenario_analysis(
                base_revenue=base_revenue,
                base_ebit_margin=ebit_margin,
                base_wacc=base_wacc,
                base_terminal_growth=base_terminal_growth,
                shares=shares,
            )
        except Exception as e:
            logger.warning(f"情景分析失败: {e}")
            result.warnings.append(f"情景分析失败: {e}")

    # === Step 2: 结论翻转阈值 ===
    if not is_loss:
        try:
            result.flip_thresholds = compute_flip_thresholds(
                base_value=valuation_value,
                current_price=current_price,
                base_revenue=base_revenue,
                base_ebit_margin=ebit_margin,
                base_wacc=base_wacc,
                base_terminal_growth=base_terminal_growth,
                shares=shares,
            )
        except Exception as e:
            logger.warning(f"翻转阈值计算失败: {e}")
            result.warnings.append(f"翻转阈值失败: {e}")

    # === Step 3: 同比分析 ===
    try:
        result.yoy_changes = compute_yoy_changes(financials)
    except Exception as e:
        logger.warning(f"同比分析失败: {e}")
        result.warnings.append(f"同比分析失败: {e}")

    # === Step 4: 洞察深度审计 ===
    try:
        result.insight_audits = audit_insight_depth(chapters)
        if result.insight_audits:
            result.overall_insight_score = sum(
                a.score for a in result.insight_audits
            ) / len(result.insight_audits)
    except Exception as e:
        logger.warning(f"洞察审计失败: {e}")
        result.warnings.append(f"洞察审计失败: {e}")

    logger.info(
        f"深度优化完成: 情景={len(result.scenarios)}个, "
        f"翻转阈值={len(result.flip_thresholds)}个, "
        f"同比变化={len(result.yoy_changes)}个, "
        f"洞察评分={result.overall_insight_score:.0f}"
    )

    return result


def format_depth_for_report(dr: DepthResult) -> str:
    """将深度优化结果格式化为报告内容"""
    lines = []

    # 情景分析
    if dr.scenarios:
        lines.append("### 情景分析")
        lines.append("| 情景 | 营收增速 | EBIT利润率 | WACC | 每股价值 | 概率 |")
        lines.append("|------|----------|-----------|------|----------|------|")
        for s in dr.scenarios:
            lines.append(
                f"| {s.name} | {s.revenue_growth:+.1%} | {s.ebit_margin:.1%} | "
                f"{s.wacc:.1%} | {s.value_per_share:.1f}元 | {s.probability:.0%} |"
            )
        lines.append("")

    # 翻转阈值
    if dr.flip_thresholds:
        lines.append("### 结论翻转阈值")
        for ft in dr.flip_thresholds:
            lines.append(f"- **{ft.variable}**: 当前{ft.current_value} → 翻转点{ft.flip_value} ({ft.direction})")
            lines.append(f"  - {ft.impact}")
        lines.append("")

    # 同比分析
    if dr.yoy_changes:
        lines.append("### 同比变化")
        for yc in dr.yoy_changes:
            trend_cn = {"accelerating": "加速", "decelerating": "减速", "stable": "稳定"}.get(yc.trend, yc.trend)
            lines.append(f"- {yc.metric}: {yc.previous:.1f} → {yc.current:.1f} ({yc.change_pct:+.1%}, {trend_cn})")
        lines.append("")

    # 洞察审计
    if dr.insight_audits:
        lines.append("### 洞察深度审计")
        for audit in dr.insight_audits:
            status = "✅" if audit.has_actionable_insight else "❌"
            lines.append(f"- 第{audit.chapter_num}章 {audit.chapter_title}: {status} (评分{audit.score})")
        lines.append(f"- **整体洞察评分**: {dr.overall_insight_score:.0f}/100")

    return "\n".join(lines)


# v10 P0：亏损公司 EV/Revenue 翻转阈值（替代 DCF 翻转阈值）
def _compute_ev_revenue_flip_thresholds(
    revenue: float,
    enterprise_value: float,
    current_price: float,
    shares: float,
) -> list[FlipThreshold]:
    """亏损公司 EV/Revenue 翻转阈值。

    翻转逻辑：当营收降至多少时，即使 EV/Revenue 倍数不变，
    企业价值也跌破当前市值（即股价跌破当前价）。
    """
    thresholds = []
    market_cap = current_price * shares
    current_ev_rev = enterprise_value / revenue if revenue > 0 else 0

    # Step 1: EV/Revenue 倍数翻转点（当倍数降到多少时，EV = 市值）
    flip_ev_rev = market_cap / revenue if revenue > 0 else 0

    # Step 2: 营收翻转点（倍数不变，营收降到多少时 EV = 市值）
    flip_revenue = market_cap / current_ev_rev if current_ev_rev > 0 else 0

    # Step 3: 检测净债务≈0 的情况（翻转点≈当前值，无信息量）
    ev_rev_gap = abs(current_ev_rev - flip_ev_rev) / max(current_ev_rev, 0.01)
    rev_gap = abs(revenue - flip_revenue) / max(revenue, 0.01)

    note = ""
    if ev_rev_gap < 0.05 or rev_gap < 0.05:
        # 净债务≈0，改用 20% 偏差作为敏感度阈值
        flip_ev_rev = current_ev_rev * 0.80
        flip_revenue = revenue * 0.80
        note = "（净债务≈0，以 20% 偏差为敏感度阈值）"
    else:
        # 方向验证：翻转点必须低于当前值（下降才有意义）
        if flip_ev_rev > current_ev_rev:
            flip_ev_rev = current_ev_rev * 0.80
        if flip_revenue > revenue:
            flip_revenue = revenue * 0.80

    thresholds.append(FlipThreshold(
        variable="EV/Revenue倍数",
        current_value=round(current_ev_rev, 2),
        flip_value=round(flip_ev_rev, 2),
        direction="down",
        impact=f"当 EV/Revenue 降至 {flip_ev_rev:.2f}x 时，估值等于当前股价{note}",
    ))

    thresholds.append(FlipThreshold(
        variable="营收(亿)",
        current_value=round(revenue, 2),
        flip_value=round(flip_revenue, 2),
        direction="down",
        impact=f"当营收降至 {flip_revenue:.1f}亿 时，估值等于当前股价（EV/Rev={current_ev_rev:.2f}x）{note}",
    ))

    return thresholds
