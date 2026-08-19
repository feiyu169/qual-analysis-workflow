"""
压力测试模块

支持：
- 收入下降压力测试
- 利润率收缩压力测试
- 现金流压力测试
- 利息保障倍数计算
- 流动性月数计算
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class StressScenario:
    """压力测试情景"""
    name: str                           # 情景名称
    description: str                    # 情景描述
    revenue_shock: float = 0.0          # 收入冲击（百分比）
    margin_shock: float = 0.0           # 利润率冲击
    fx_shock: float = 0.0               # 汇率冲击
    probability: float = 0.0            # 发生概率


@dataclass
class StressTestResult:
    """压力测试结果"""
    scenario: StressScenario
    base_revenue: float = 0.0
    stressed_revenue: float = 0.0
    base_net_income: float = 0.0
    stressed_net_income: float = 0.0
    base_fcf: float = 0.0
    stressed_fcf: float = 0.0
    interest_coverage: float = 0.0      # 利息保障倍数
    liquidity_months: float = 0.0       # 流动性月数
    warnings: list[str] = field(default_factory=list)


@dataclass
class StressTestSuite:
    """压力测试套件"""
    scenarios: list[StressScenario] = field(default_factory=list)
    results: list[StressTestResult] = field(default_factory=list)
    worst_case: Optional[StressTestResult] = None
    summary: str = ""


def run_stress_test(
    base_revenue: float,
    base_net_income: float,
    base_fcf: float,
    base_ebit: float = 0.0,            # 新增：基准 EBIT
    interest_expense: float = 0.0,
    net_debt: float = 0.0,
    cash: float = 0.0,
    monthly_opex: float = 0.0,
    scenarios: list[StressScenario] = None,
) -> StressTestSuite:
    """
    运行压力测试

    Args:
        base_revenue: 基准收入（亿人民币）
        base_net_income: 基准净利润
        base_fcf: 基准自由现金流
        base_ebit: 基准 EBIT（可选）
        interest_expense: 利息支出（亿人民币）
        net_debt: 净负债
        cash: 现金储备
        monthly_opex: 月度运营支出
        scenarios: 压力测试情景列表

    Returns:
        StressTestSuite 测试结果
    """
    if scenarios is None:
        scenarios = _default_scenarios()

    suite = StressTestSuite(scenarios=scenarios)

    # 计算基准利润率
    base_margin = base_net_income / base_revenue if base_revenue > 0 else 0

    # 如果未提供 EBIT，使用净利润的 1.25 倍作为估算
    if base_ebit <= 0:
        base_ebit = base_net_income * 1.25
        logger.warning("未提供 EBIT，使用净利润 x 1.25 作为估算")

    for scenario in scenarios:
        result = StressTestResult(
            scenario=scenario,
            base_revenue=base_revenue,
            base_net_income=base_net_income,
            base_fcf=base_fcf,
        )

        # 收入冲击
        result.stressed_revenue = base_revenue * (1 + scenario.revenue_shock)

        # 利润率调整
        stressed_margin = base_margin * (1 + scenario.margin_shock)

        # 净利润 = 压力收入 x 调整后利润率
        result.stressed_net_income = result.stressed_revenue * stressed_margin

        # FCF 冲击
        result.stressed_fcf = base_fcf * (1 + scenario.revenue_shock)

        # 利息保障倍数 = EBIT / 利息支出
        if interest_expense > 0:
            stressed_ebit = base_ebit * (1 + scenario.revenue_shock) * (1 + scenario.margin_shock)
            result.interest_coverage = stressed_ebit / interest_expense
        else:
            result.interest_coverage = float('inf')

        # 流动性月数（保守计算）
        monthly_fcf = result.stressed_fcf / 12
        if monthly_opex > 0:
            if monthly_fcf >= 0:
                # FCF 为正：现金 + 6个月缓冲
                result.liquidity_months = (cash + monthly_fcf * 6) / monthly_opex
            else:
                # FCF 为负：现金 / (月支出 + 月度现金消耗)
                result.liquidity_months = cash / (monthly_opex + abs(monthly_fcf))
        else:
            result.liquidity_months = float('inf')

        # 警告
        if result.stressed_net_income < 0:
            result.warnings.append("压力情景下净利润为负")
        if result.interest_coverage < 2.0:
            result.warnings.append("利息保障倍数不足 2x")
        if result.liquidity_months < 6:
            result.warnings.append("流动性不足 6 个月")

        suite.results.append(result)

    # 最坏情景
    suite.worst_case = min(suite.results, key=lambda r: r.stressed_net_income)

    # 摘要
    suite.summary = _format_stress_summary(suite)

    return suite


def _default_scenarios() -> list[StressScenario]:
    """默认压力测试情景"""
    return [
        StressScenario(
            name="温和衰退",
            description="收入下降10%，利润率收缩5%",
            revenue_shock=-0.10,
            margin_shock=-0.05,
            probability=0.20,
        ),
        StressScenario(
            name="严重衰退",
            description="收入下降25%，利润率收缩15%",
            revenue_shock=-0.25,
            margin_shock=-0.15,
            probability=0.05,
        ),
        StressScenario(
            name="极端冲击",
            description="收入下降40%，利润率收缩30%",
            revenue_shock=-0.40,
            margin_shock=-0.30,
            probability=0.01,
        ),
    ]


def _format_stress_summary(suite: StressTestSuite) -> str:
    """格式化压力测试摘要"""
    lines = ["## 压力测试结果\n"]
    lines.append("| 情景 | 收入冲击 | 净利润 | FCF | 利息保障 | 流动性月数 |")
    lines.append("|------|----------|--------|-----|----------|------------|")

    for result in suite.results:
        coverage = f"{result.interest_coverage:.1f}x" if result.interest_coverage != float('inf') else "N/A"
        liquidity = f"{result.liquidity_months:.1f}月" if result.liquidity_months != float('inf') else "N/A"

        lines.append(
            f"| {result.scenario.name} | "
            f"{result.scenario.revenue_shock:.0%} | "
            f"{result.stressed_net_income:.1f}亿 | "
            f"{result.stressed_fcf:.1f}亿 | "
            f"{coverage} | "
            f"{liquidity} |"
        )

    if suite.worst_case:
        lines.append(f"\n**最坏情景**: {suite.worst_case.scenario.name}")
        if suite.worst_case.warnings:
            lines.append(f"**警告**: {', '.join(suite.worst_case.warnings)}")

    return "\n".join(lines)
