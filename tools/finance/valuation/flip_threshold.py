"""
翻转阈值计算器（二分法+方向验证+收敛兜底）

功能：
1. 二分法计算翻转阈值
2. 方向验证
3. 输入边界检查
4. 收敛失败兜底
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FlipThreshold:
    """翻转阈值"""
    variable: str
    current_value: float
    flip_value: float
    direction: str  # up, down
    impact: str


@dataclass
class ConvergenceResult:
    """收敛结果"""
    converged: bool
    iterations: int
    final_value: float
    error_message: str | None = None


class FlipThresholdCalculator:
    """翻转阈值计算器"""

    # 输入边界
    INPUT_BOUNDS = {
        "revenue": {"min": 0.1, "max": 10000},
        "ebit_margin": {"min": -0.5, "max": 0.5},
        "wacc": {"min": 0.03, "max": 0.25},
        "terminal_growth": {"min": 0.01, "max": 0.05},
    }

    def __init__(self, base_revenue, base_ebit_margin, base_wacc,
                 base_terminal_growth, shares, net_debt):
        # 输入边界检查
        self._validate_inputs(base_revenue, base_ebit_margin, base_wacc, base_terminal_growth)

        self.base_revenue = base_revenue
        self.base_ebit_margin = base_ebit_margin
        self.base_wacc = base_wacc
        self.base_terminal_growth = base_terminal_growth
        self.shares = shares
        self.net_debt = net_debt

    def _validate_inputs(self, revenue, ebit_margin, wacc, terminal_growth):
        """输入边界检查"""
        bounds = self.INPUT_BOUNDS

        if not (bounds["revenue"]["min"] <= revenue <= bounds["revenue"]["max"]):
            raise ValueError(f"营收{revenue}超出边界{bounds['revenue']}")

        if not (bounds["ebit_margin"]["min"] <= ebit_margin <= bounds["ebit_margin"]["max"]):
            raise ValueError(f"EBIT利润率{ebit_margin}超出边界{bounds['ebit_margin']}")

        if not (bounds["wacc"]["min"] <= wacc <= bounds["wacc"]["max"]):
            raise ValueError(f"WACC{wacc}超出边界{bounds['wacc']}")

        if not (bounds["terminal_growth"]["min"] <= terminal_growth <= bounds["terminal_growth"]["max"]):
            raise ValueError(f"永续增长率{terminal_growth}超出边界{bounds['terminal_growth']}")

    def _binary_search(self, target_value: float, variable: str,
                      low: float, high: float, max_iterations: int = 50,
                      tolerance: float = 0.001) -> ConvergenceResult:
        """二分法搜索"""
        for iteration in range(max_iterations):
            mid = (low + high) / 2

            # 计算当前值的权益价值
            if variable == "revenue":
                equity = self.calc_equity_value(mid, self.base_ebit_margin,
                                               self.base_wacc, self.base_terminal_growth)
            elif variable == "ebit_margin":
                equity = self.calc_equity_value(self.base_revenue, mid,
                                               self.base_wacc, self.base_terminal_growth)
            elif variable == "wacc":
                equity = self.calc_equity_value(self.base_revenue, self.base_ebit_margin,
                                               mid, self.base_terminal_growth)
            else:
                raise ValueError(f"未知变量: {variable}")

            # 检查是否收敛
            if abs(equity - target_value) < tolerance:
                return ConvergenceResult(
                    converged=True,
                    iterations=iteration + 1,
                    final_value=mid,
                )

            # 调整边界
            if equity > target_value:
                high = mid
            else:
                low = mid

        # 收敛失败
        return ConvergenceResult(
            converged=False,
            iterations=max_iterations,
            final_value=(low + high) / 2,
            error_message=f"二分法在{max_iterations}次迭代后未收敛",
        )

    def calc_equity_value(self, revenue, ebit_margin, wacc, terminal_growth):
        """计算权益价值"""
        ebit = revenue * ebit_margin
        nopat = ebit * 0.75
        da = revenue * 0.03
        capex = revenue * 0.04
        fcf = nopat + da - capex - revenue * 0.02 * 0.02

        if fcf <= 0 or wacc <= terminal_growth:
            return 0

        tv = fcf * (1 + terminal_growth) / (wacc - terminal_growth)
        pv_factor = sum(1 / (1 + wacc) ** i for i in range(1, 6))
        ev = fcf * pv_factor + tv / (1 + wacc) ** 5

        return ev - self.net_debt

    def calc_revenue_flip(self, target_equity_value) -> FlipThreshold:
        """计算营收翻转点"""
        result = self._binary_search(target_equity_value, "revenue",
                                    self.base_revenue * 0.3, self.base_revenue * 3.0)

        if not result.converged:
            logger.warning(f"营收翻转点计算未收敛: {result.error_message}")

        flip_value = result.final_value

        # 方向验证
        if flip_value > self.base_revenue:
            direction = "up"
            impact = f"当营收升至{flip_value:.0f}亿元时，估值等于当前股价"
        else:
            direction = "down"
            impact = f"当营收降至{flip_value:.0f}亿元时，估值等于当前股价"

        return FlipThreshold(
            variable="营收",
            current_value=round(self.base_revenue, 1),
            flip_value=round(flip_value, 1),
            direction=direction,
            impact=impact,
        )

    def calc_margin_flip(self, target_equity_value) -> FlipThreshold:
        """计算EBIT利润率翻转点"""
        result = self._binary_search(target_equity_value, "ebit_margin",
                                    0.01, 0.30)

        if not result.converged:
            logger.warning(f"EBIT利润率翻转点计算未收敛: {result.error_message}")

        flip_value = result.final_value

        # 方向验证
        if flip_value > self.base_ebit_margin:
            direction = "up"
            impact = f"当EBIT利润率升至{flip_value*100:.1f}%时，估值等于当前股价"
        else:
            direction = "down"
            impact = f"当EBIT利润率降至{flip_value*100:.1f}%时，估值等于当前股价"

        return FlipThreshold(
            variable="EBIT利润率",
            current_value=round(self.base_ebit_margin * 100, 1),
            flip_value=round(flip_value * 100, 1),
            direction=direction,
            impact=impact,
        )

    def calc_wacc_flip(self, target_equity_value) -> FlipThreshold:
        """计算WACC翻转点"""
        result = self._binary_search(target_equity_value, "wacc",
                                    0.03, 0.25)

        if not result.converged:
            logger.warning(f"WACC翻转点计算未收敛: {result.error_message}")

        flip_value = result.final_value

        # 方向验证（WACC上升应压低估值）
        if flip_value > self.base_wacc:
            direction = "up"
            impact = f"当WACC升至{flip_value*100:.1f}%时，估值等于当前股价"
        else:
            direction = "down"
            impact = f"当WACC降至{flip_value*100:.1f}%时，估值等于当前股价"

        return FlipThreshold(
            variable="WACC",
            current_value=round(self.base_wacc * 100, 1),
            flip_value=round(flip_value * 100, 1),
            direction=direction,
            impact=impact,
        )

    def calc_all_thresholds(self, current_price) -> list[FlipThreshold]:
        """计算所有翻转阈值"""
        target_equity_value = current_price * self.shares

        return [
            self.calc_revenue_flip(target_equity_value),
            self.calc_margin_flip(target_equity_value),
            self.calc_wacc_flip(target_equity_value),
        ]
