"""
统一估值计算（DCF+情景分析+差异归因）

功能：
1. 统一DCF估值
2. 统一情景分析
3. 一致性验证
4. 差异归因
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class IntermediateVariable:
    """中间变量"""
    name: str
    dcf_value: float
    scenario_value: float
    difference: float
    explanation: str


@dataclass
class DifferenceAttribution:
    """差异归因"""
    total_difference: float
    attributions: list[IntermediateVariable]
    conclusion: str


@dataclass
class ValuationResult:
    """估值结果"""
    dcf_value: float
    scenario_values: dict[str, float]
    scenario_weighted_average: float
    consistency_check: dict
    difference_attribution: DifferenceAttribution | None


class UnifiedValuation:
    """
    统一估值计算

    所有估值方法使用同一套假设，确保结果一致性
    """

    def __init__(self, assumptions, shares: float, net_debt: float):
        """
        初始化

        Args:
            assumptions: ValuationAssumptions对象
            shares: 总股本（亿股）
            net_debt: 净负债（亿）
        """
        self.assumptions = assumptions
        self.shares = shares
        self.net_debt = net_debt

        # 中间变量记录
        self.dcf_intermediates: dict[str, float] = {}
        self.scenario_intermediates: dict[str, dict[str, float]] = {}

    def calc_fcf(self, revenue: float, ebit_margin: float, growth: float) -> float:
        """计算FCF（统一公式）"""
        ebit = revenue * ebit_margin
        nopat = ebit * (1 - self.assumptions.tax_rate)
        da = revenue * self.assumptions.da_ratio
        capex = revenue * self.assumptions.capex_ratio
        wc_change = revenue * growth * self.assumptions.wc_ratio
        fcf = nopat + da - capex - wc_change

        return fcf

    def calc_dcf(self) -> float:
        """DCF估值"""
        total_pv_fcf = 0
        revenue = self.assumptions.base_revenue

        for year in range(5):
            growth = self.assumptions.revenue_growth_rates[year]
            margin = self.assumptions.ebit_margins[year]

            revenue = revenue * (1 + growth)
            fcf = self.calc_fcf(revenue, margin, growth)

            discount_factor = 1 / (1 + self.assumptions.wacc) ** (year + 1)
            pv_fcf = fcf * discount_factor
            total_pv_fcf += pv_fcf

        # 终值
        last_fcf = fcf
        terminal_value = last_fcf * (1 + self.assumptions.terminal_growth) / \
                        (self.assumptions.wacc - self.assumptions.terminal_growth)
        pv_terminal = terminal_value / (1 + self.assumptions.wacc) ** 5

        # 企业价值
        ev = total_pv_fcf + pv_terminal

        # 权益价值
        equity = ev - self.net_debt

        # 每股价值
        per_share = equity / self.shares if self.shares > 0 else 0

        # 记录中间变量
        self.dcf_intermediates = {
            "total_pv_fcf": total_pv_fcf,
            "terminal_value": terminal_value,
            "pv_terminal": pv_terminal,
            "ev": ev,
            "equity": equity,
            "per_share": per_share,
        }

        return per_share

    def calc_scenario(self, scenario_name: str, revenue_growth: float,
                      ebit_margin: float, wacc: float) -> float:
        """情景分析（使用与DCF相同的计算逻辑）"""
        total_pv_fcf = 0
        revenue = self.assumptions.base_revenue

        for year in range(5):
            # 使用递减增速
            if year == 0:
                growth = revenue_growth
            else:
                growth = revenue_growth * (0.8 ** year)

            revenue = revenue * (1 + growth)
            fcf = self.calc_fcf(revenue, ebit_margin, growth)

            discount_factor = 1 / (1 + wacc) ** (year + 1)
            pv_fcf = fcf * discount_factor
            total_pv_fcf += pv_fcf

        # 终值
        last_fcf = fcf
        terminal_value = last_fcf * (1 + self.assumptions.terminal_growth) / \
                        (wacc - self.assumptions.terminal_growth)
        pv_terminal = terminal_value / (1 + wacc) ** 5

        # 企业价值
        ev = total_pv_fcf + pv_terminal

        # 权益价值
        equity = ev - self.net_debt

        # 每股价值
        per_share = equity / self.shares if self.shares > 0 else 0

        # 记录中间变量
        self.scenario_intermediates[scenario_name] = {
            "total_pv_fcf": total_pv_fcf,
            "terminal_value": terminal_value,
            "pv_terminal": pv_terminal,
            "ev": ev,
            "equity": equity,
            "per_share": per_share,
        }

        return per_share

    def calc_scenario_weighted_average(self, scenarios: dict[str, dict]) -> float:
        """计算情景分析概率加权平均"""
        weighted_sum = 0
        for name, params in scenarios.items():
            value = self.calc_scenario(name, **params)
            weight = self.assumptions.scenario_weights.get(name, 0)
            weighted_sum += value * weight
        return weighted_sum

    def validate_consistency(self, scenarios: dict[str, dict],
                            tolerance: float = 0.2) -> dict:
        """验证DCF与情景分析一致性"""
        dcf_value = self.calc_dcf()
        scenario_value = self.calc_scenario_weighted_average(scenarios)

        ratio = dcf_value / scenario_value if scenario_value > 0 else 0

        # 差异归因
        attribution = self._attribute_difference(dcf_value, scenario_value, scenarios)

        if abs(ratio - 1) > tolerance:
            logger.warning(f"DCF与情景分析差异超过阈值: {abs(ratio-1)*100:.1f}%")
            logger.warning(f"差异归因: {attribution.conclusion}")

            return {
                "dcf_value": dcf_value,
                "scenario_value": scenario_value,
                "ratio": ratio,
                "passed": False,
                "attribution": attribution,
                "action_required": "人工复核",
            }

        return {
            "dcf_value": dcf_value,
            "scenario_value": scenario_value,
            "ratio": ratio,
            "passed": True,
            "attribution": attribution,
        }

    def _attribute_difference(self, dcf_value: float, scenario_value: float,
                             scenarios: dict[str, dict]) -> DifferenceAttribution:
        """差异归因"""
        total_difference = dcf_value - scenario_value

        # 分析各中间变量的贡献
        attributions = []

        # 比较终值
        dcf_tv = self.dcf_intermediates.get("pv_terminal", 0)
        scenario_tv = sum(
            self.scenario_intermediates.get(name, {}).get("pv_terminal", 0) * weight
            for name, weight in self.assumptions.scenario_weights.items()
        )
        attributions.append(IntermediateVariable(
            name="终值",
            dcf_value=dcf_tv,
            scenario_value=scenario_tv,
            difference=dcf_tv - scenario_tv,
            explanation="DCF与情景分析的终值差异",
        ))

        # 比较预测期FCF
        dcf_pv = self.dcf_intermediates.get("total_pv_fcf", 0)
        scenario_pv = sum(
            self.scenario_intermediates.get(name, {}).get("total_pv_fcf", 0) * weight
            for name, weight in self.assumptions.scenario_weights.items()
        )
        attributions.append(IntermediateVariable(
            name="预测期FCF",
            dcf_value=dcf_pv,
            scenario_value=scenario_pv,
            difference=dcf_pv - scenario_pv,
            explanation="DCF与情景分析的预测期FCF差异",
        ))

        # 生成结论
        max_attribution = max(attributions, key=lambda x: abs(x.difference))
        conclusion = f"主要差异来源: {max_attribution.name}（差异{max_attribution.difference:.1f}元）"

        return DifferenceAttribution(
            total_difference=total_difference,
            attributions=attributions,
            conclusion=conclusion,
        )

    def calc_all_scenarios(self) -> dict[str, float]:
        """计算所有情景"""
        scenarios = {
            "基准": {
                "revenue_growth": 0.0,
                "ebit_margin": self.assumptions.ebit_margins[0],
                "wacc": self.assumptions.wacc,
            },
            "乐观": {
                "revenue_growth": 0.20,
                "ebit_margin": self.assumptions.ebit_margins[0] * 1.2,
                "wacc": self.assumptions.wacc - 0.02,
            },
            "悲观": {
                "revenue_growth": -0.20,
                "ebit_margin": self.assumptions.ebit_margins[0] * 0.8,
                "wacc": self.assumptions.wacc + 0.02,
            },
            "高增长": {
                "revenue_growth": 0.30,
                "ebit_margin": self.assumptions.ebit_margins[0],
                "wacc": self.assumptions.wacc,
            },
            "利润率压缩": {
                "revenue_growth": 0.0,
                "ebit_margin": self.assumptions.ebit_margins[0] * 0.7,
                "wacc": self.assumptions.wacc,
            },
        }

        results = {}
        for name, params in scenarios.items():
            results[name] = self.calc_scenario(name, **params)

        return results

    def get_full_result(self) -> ValuationResult:
        """获取完整估值结果"""
        # 计算DCF
        dcf_value = self.calc_dcf()

        # 计算所有情景
        scenario_values = self.calc_all_scenarios()

        # 计算加权平均
        weighted_average = sum(
            value * self.assumptions.scenario_weights.get(name, 0)
            for name, value in scenario_values.items()
        )

        # 验证一致性
        consistency_check = self.validate_consistency({
            "基准": {"revenue_growth": 0.0, "ebit_margin": self.assumptions.ebit_margins[0], "wacc": self.assumptions.wacc},
            "乐观": {"revenue_growth": 0.20, "ebit_margin": self.assumptions.ebit_margins[0] * 1.2, "wacc": self.assumptions.wacc - 0.02},
            "悲观": {"revenue_growth": -0.20, "ebit_margin": self.assumptions.ebit_margins[0] * 0.8, "wacc": self.assumptions.wacc + 0.02},
            "高增长": {"revenue_growth": 0.30, "ebit_margin": self.assumptions.ebit_margins[0], "wacc": self.assumptions.wacc},
            "利润率压缩": {"revenue_growth": 0.0, "ebit_margin": self.assumptions.ebit_margins[0] * 0.7, "wacc": self.assumptions.wacc},
        })

        return ValuationResult(
            dcf_value=dcf_value,
            scenario_values=scenario_values,
            scenario_weighted_average=weighted_average,
            consistency_check=consistency_check,
            difference_attribution=consistency_check.get("attribution"),
        )
