"""
SensitivityAnalyzer模块

功能:
- 敏感性分析: WACC/g/FCF三维
- 龙卷风图: Top 5变量
- Breakeven分析: 翻转点

解决: P1-4 敏感性分析缺失
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SensitivityConfig:
    """敏感性分析配置"""
    wacc_range: list[float] = field(default_factory=lambda: [-0.02, -0.01, 0, 0.01, 0.02])
    growth_range: list[float] = field(default_factory=lambda: [-0.01, -0.005, 0, 0.005, 0.01])
    fcf_range: list[float] = field(default_factory=lambda: [-0.20, -0.10, 0, 0.10, 0.20])


@dataclass
class SensitivityResult:
    """敏感性分析结果"""
    base_value: float
    wacc_sensitivity: dict[float, float] = field(default_factory=dict)
    growth_sensitivity: dict[float, float] = field(default_factory=dict)
    fcf_sensitivity: dict[float, float] = field(default_factory=dict)
    tornado_data: list[dict] = field(default_factory=list)
    breakeven: dict[str, float] = field(default_factory=dict)


class SensitivityAnalyzer:
    """敏感性分析器"""

    def __init__(self, config: SensitivityConfig | None = None):
        self.config = config or SensitivityConfig()

    def analyze_wacc_sensitivity(
        self,
        base_wacc: float,
        base_g: float,
        base_fcf: float,
        net_debt: float,
        shares: float,
    ) -> dict[float, float]:
        """WACC敏感性分析"""
        results = {}

        for delta in self.config.wacc_range:
            wacc = base_wacc + delta
            if wacc <= base_g:
                results[delta] = None  # 无效
                continue

            ev = base_fcf / (wacc - base_g)
            equity_value = ev - net_debt
            per_share_value = equity_value / shares
            results[delta] = per_share_value

        return results

    def analyze_growth_sensitivity(
        self,
        base_wacc: float,
        base_g: float,
        base_fcf: float,
        net_debt: float,
        shares: float,
    ) -> dict[float, float]:
        """永续增长率敏感性分析"""
        results = {}

        for delta in self.config.growth_range:
            g = base_g + delta
            if g >= base_wacc:
                results[delta] = None  # 无效
                continue

            ev = base_fcf / (base_wacc - g)
            equity_value = ev - net_debt
            per_share_value = equity_value / shares
            results[delta] = per_share_value

        return results

    def analyze_fcf_sensitivity(
        self,
        base_wacc: float,
        base_g: float,
        base_fcf: float,
        net_debt: float,
        shares: float,
    ) -> dict[float, float]:
        """FCF敏感性分析"""
        results = {}

        for delta in self.config.fcf_range:
            fcf = base_fcf * (1 + delta)
            ev = fcf / (base_wacc - base_g)
            equity_value = ev - net_debt
            per_share_value = equity_value / shares
            results[delta] = per_share_value

        return results

    def analyze(
        self,
        base_wacc: float,
        base_g: float,
        base_fcf: float,
        net_debt: float,
        shares: float,
    ) -> SensitivityResult:
        """完整敏感性分析"""
        # 基础值
        base_ev = base_fcf / (base_wacc - base_g)
        base_equity = base_ev - net_debt
        base_per_share = base_equity / shares

        # WACC敏感性
        wacc_sensitivity = self.analyze_wacc_sensitivity(
            base_wacc, base_g, base_fcf, net_debt, shares
        )

        # 增长率敏感性
        growth_sensitivity = self.analyze_growth_sensitivity(
            base_wacc, base_g, base_fcf, net_debt, shares
        )

        # FCF敏感性
        fcf_sensitivity = self.analyze_fcf_sensitivity(
            base_wacc, base_g, base_fcf, net_debt, shares
        )

        # 龙卷风图数据
        tornado_data = self._calculate_tornado(
            base_per_share, wacc_sensitivity, growth_sensitivity, fcf_sensitivity
        )

        # Breakeven分析
        breakeven = self._calculate_breakeven(
            base_wacc, base_g, base_fcf, net_debt, shares, base_per_share
        )

        return SensitivityResult(
            base_value=base_per_share,
            wacc_sensitivity=wacc_sensitivity,
            growth_sensitivity=growth_sensitivity,
            fcf_sensitivity=fcf_sensitivity,
            tornado_data=tornado_data,
            breakeven=breakeven,
        )

    def _calculate_tornado(
        self,
        base_value: float,
        wacc_sensitivity: dict[float, float],
        growth_sensitivity: dict[float, float],
        fcf_sensitivity: dict[float, float],
    ) -> list[dict]:
        """计算龙卷风图数据"""
        tornado_data = []

        # WACC影响
        wacc_values = [v for v in wacc_sensitivity.values() if v is not None]
        if wacc_values:
            wacc_range = max(wacc_values) - min(wacc_values)
            tornado_data.append({
                "variable": "WACC",
                "range": wacc_range,
                "min": min(wacc_values),
                "max": max(wacc_values),
            })

        # 增长率影响
        growth_values = [v for v in growth_sensitivity.values() if v is not None]
        if growth_values:
            growth_range = max(growth_values) - min(growth_values)
            tornado_data.append({
                "variable": "永续增长率",
                "range": growth_range,
                "min": min(growth_values),
                "max": max(growth_values),
            })

        # FCF影响
        fcf_values = [v for v in fcf_sensitivity.values() if v is not None]
        if fcf_values:
            fcf_range = max(fcf_values) - min(fcf_values)
            tornado_data.append({
                "variable": "FCF",
                "range": fcf_range,
                "min": min(fcf_values),
                "max": max(fcf_values),
            })

        # 按影响范围排序
        tornado_data.sort(key=lambda x: x["range"], reverse=True)

        return tornado_data[:5]  # Top 5

    def _calculate_breakeven(
        self,
        base_wacc: float,
        base_g: float,
        base_fcf: float,
        net_debt: float,
        shares: float,
        base_per_share: float,
    ) -> dict[str, float]:
        """计算Breakeven点"""
        breakeven = {}

        # WACC翻转点（使per_share_value = 0）
        # equity_value = 0 → ev = net_debt → fcf/(wacc-g) = net_debt → wacc = fcf/net_debt + g
        if net_debt > 0:
            wacc_breakeven = base_fcf / net_debt + base_g
            breakeven["wacc_for_zero_value"] = wacc_breakeven

        # g翻转点（使per_share_value = 0）
        # equity_value = 0 → ev = net_debt → fcf/(wacc-g) = net_debt → g = wacc - fcf/net_debt
        if net_debt > 0:
            g_breakeven = base_wacc - base_fcf / net_debt
            breakeven["growth_for_zero_value"] = g_breakeven

        return breakeven

    def generate_sensitivity_matrix(
        self,
        result: SensitivityResult,
    ) -> str:
        """生成敏感性矩阵"""
        lines = [
            "## 敏感性分析",
            "",
            f"**基础每股价值**: {result.base_value:.2f}元",
            "",
            "### WACC敏感性",
            "",
            "| WACC变动 | 每股价值 |",
            "|----------|----------|",
        ]

        for delta, value in result.wacc_sensitivity.items():
            if value is not None:
                lines.append(f"| {delta:+.1%} | {value:.2f} |")
            else:
                lines.append(f"| {delta:+.1%} | 无效 |")

        lines.extend([
            "",
            "### 永续增长率敏感性",
            "",
            "| g变动 | 每股价值 |",
            "|-------|----------|",
        ])

        for delta, value in result.growth_sensitivity.items():
            if value is not None:
                lines.append(f"| {delta:+.1%} | {value:.2f} |")
            else:
                lines.append(f"| {delta:+.1%} | 无效 |")

        lines.extend([
            "",
            "### FCF敏感性",
            "",
            "| FCF变动 | 每股价值 |",
            "|---------|----------|",
        ])

        for delta, value in result.fcf_sensitivity.items():
            if value is not None:
                lines.append(f"| {delta:+.0%} | {value:.2f} |")
            else:
                lines.append(f"| {delta:+.0%} | 无效 |")

        # 龙卷风图
        if result.tornado_data:
            lines.extend([
                "",
                "### 龙卷风图 (Top 5影响变量)",
                "",
                "| 变量 | 影响范围 | 最小值 | 最大值 |",
                "|------|----------|--------|--------|",
            ])
            for item in result.tornado_data:
                lines.append(
                    f"| {item['variable']} | {item['range']:.2f} | {item['min']:.2f} | {item['max']:.2f} |"
                )

        # Breakeven
        if result.breakeven:
            lines.extend([
                "",
                "### Breakeven分析",
                "",
            ])
            for key, value in result.breakeven.items():
                lines.append(f"- {key}: {value:.2%}")

        return "\n".join(lines)
