"""
TerminalValueCalculator模块

功能:
- 双轨终值计算（永续增长法+退出倍数法）
- 终值仲裁规则
- TV/EV比例检查

解决: 终值计算不一致问题

"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TerminalValueResult:
    """终值计算结果"""
    tv_perpetuity: float  # 永续增长法终值
    tv_exit_multiple: float  # 退出倍数法终值
    chosen_tv: float  # 选定终值
    chosen_method: str  # 选定方法
    difference_pct: float  # 差异百分比
    confidence: str  # 置信度
    reasoning: str  # 选择理由
    tv_ev_ratio: float  # TV/EV比例


class TerminalValueCalculator:
    """终值计算器

    双轨方法:
    1. 永续增长法: TV = FCF × (1+g) / (WACC-g)
    2. 退出倍数法: TV = EBITDA × ExitMultiple

    仲裁规则:
    - 差异 < 10%: 取均值, 置信度=high
    - 10% ≤ 差异 < 25%: 取保守(较低值), 置信度=medium
    - 25% ≤ 差异 < 50%: 取保守+敏感性分析, 置信度=low
    - 差异 ≥ 50%: 阻断, 需人工审查
    """

    # 差异阈值
    THRESHOLD_CLOSE = 0.10      # < 10%: 取均值
    THRESHOLD_MODERATE = 0.25   # 10-25%: 取保守
    THRESHOLD_LARGE = 0.50      # 25-50%: 取保守+敏感性
    # ≥ 50%: 阻断

    # TV/EV阈值
    TV_EV_THRESHOLD = 0.75  # TV/EV > 75%: 强制敏感性分析

    def calculate_perpetuity(
        self,
        fcf: float,
        wacc: float,
        g: float
    ) -> float:
        """永续增长法计算终值

        TV = FCF × (1+g) / (WACC-g)

        Args:
            fcf: 最后一年FCF
            wacc: 加权平均资本成本
            g: 永续增长率

        Returns:
            终值
        """

        # 数学约束: g < WACC
        if g >= wacc:
            raise ValueError(f"g={g:.2%}必须小于WACC={wacc:.2%}（数学约束）")

        # 计算终值
        tv = fcf * (1 + g) / (wacc - g)

        return tv

    def calculate_exit_multiple(
        self,
        ebitda: float,
        exit_multiple: float
    ) -> float:
        """退出倍数法计算终值

        TV = EBITDA × ExitMultiple

        Args:
            ebitda: 最后一年EBITDA
            exit_multiple: 退出倍数 (EV/EBITDA)

        Returns:
            终值
        """

        # 验证退出倍数范围
        if exit_multiple < 5 or exit_multiple > 25:
            raise ValueError(f"退出倍数={exit_multiple:.1f}x超出合理范围[5x, 25x]")

        # 计算终值
        tv = ebitda * exit_multiple

        return tv

    def calculate(
        self,
        fcf: float,
        ebitda: float,
        wacc: float,
        g: float,
        exit_multiple: float,
        ev_estimate: float
    ) -> TerminalValueResult:
        """双轨终值计算+仲裁"""

        # 计算两种终值
        tv_perpetuity = self.calculate_perpetuity(fcf, wacc, g)
        tv_exit_multiple = self.calculate_exit_multiple(ebitda, exit_multiple)

        # 仲裁
        result = self._arbitrate(
            tv_perpetuity=tv_perpetuity,
            tv_exit_multiple=tv_exit_multiple,
            ev_estimate=ev_estimate
        )

        return result

    def _arbitrate(
        self,
        tv_perpetuity: float,
        tv_exit_multiple: float,
        ev_estimate: float
    ) -> TerminalValueResult:
        """仲裁两种终值方法的结果"""

        # 计算差异
        diff = abs(tv_perpetuity - tv_exit_multiple)
        avg_tv = (tv_perpetuity + tv_exit_multiple) / 2
        diff_pct = diff / avg_tv if avg_tv > 0 else 0

        # 计算TV/EV比例
        tv_ev_ratio_perp = tv_perpetuity / ev_estimate if ev_estimate > 0 else 0
        tv_ev_ratio_exit = tv_exit_multiple / ev_estimate if ev_estimate > 0 else 0
        max_tv_ev = max(tv_ev_ratio_perp, tv_ev_ratio_exit)

        # 仲裁逻辑
        if diff_pct < self.THRESHOLD_CLOSE:
            # 差异<10%: 取均值
            return TerminalValueResult(
                tv_perpetuity=tv_perpetuity,
                tv_exit_multiple=tv_exit_multiple,
                chosen_tv=avg_tv,
                chosen_method="dual_average",
                difference_pct=diff_pct,
                confidence="high",
                reasoning=f"两种方法差异{diff_pct:.1%}<10%, 取均值",
                tv_ev_ratio=max_tv_ev
            )

        elif diff_pct < self.THRESHOLD_MODERATE:
            # 10-25%: 取保守(较低值)
            conservative_tv = min(tv_perpetuity, tv_exit_multiple)
            return TerminalValueResult(
                tv_perpetuity=tv_perpetuity,
                tv_exit_multiple=tv_exit_multiple,
                chosen_tv=conservative_tv,
                chosen_method="conservative",
                difference_pct=diff_pct,
                confidence="medium",
                reasoning=f"两种方法差异{diff_pct:.1%}在10-25%区间, 取保守值",
                tv_ev_ratio=max_tv_ev
            )

        elif diff_pct < self.THRESHOLD_LARGE:
            # 25-50%: 取保守+强制敏感性分析
            conservative_tv = min(tv_perpetuity, tv_exit_multiple)
            return TerminalValueResult(
                tv_perpetuity=tv_perpetuity,
                tv_exit_multiple=tv_exit_multiple,
                chosen_tv=conservative_tv,
                chosen_method="conservative_with_sensitivity",
                difference_pct=diff_pct,
                confidence="low",
                reasoning=f"两种方法差异{diff_pct:.1%}在25-50%区间, 取保守值并强制敏感性分析",
                tv_ev_ratio=max_tv_ev
            )

        else:
            # ≥50%: 阻断
            raise ValueError(
                f"终值差异过大({diff_pct:.1%}≥50%), "
                f"永续增长法={tv_perpetuity:.0f}, 退出倍数法={tv_exit_multiple:.0f}, "
                f"需人工审查假设"
            )

    def generate_report(self, result: TerminalValueResult) -> str:
        """生成仲裁报告"""

        report = f"""## 终值仲裁报告

| 项目 | 值 |
|------|-----|
| 永续增长法终值 | {result.tv_perpetuity:.0f} |
| 退出倍数法终值 | {result.tv_exit_multiple:.0f} |
| 选定方法 | {result.chosen_method} |
| 选定终值 | {result.chosen_tv:.0f} |
| 差异 | {result.difference_pct:.1%} |
| 置信度 | {result.confidence} |
| TV/EV比例 | {result.tv_ev_ratio:.1%} |
| 理由 | {result.reasoning} |
"""

        # 添加警告
        if result.tv_ev_ratio > self.TV_EV_THRESHOLD:
            report += f"\n⚠️ **警告**: TV/EV比例{result.tv_ev_ratio:.1%}>75%, 终值占比过高，需关注永续增长率假设\n"

        return report
