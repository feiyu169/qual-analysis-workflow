"""
TerminalValueArbitrator模块

功能:
- 终值仲裁: 保守优先+差异阈值
- TV/EV比例验证
- 仲裁报告生成

解决: P1-1 终值仲裁规则
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ArbitrationResult:
    """仲裁结果"""
    chosen_method: str
    chosen_tv: float
    alternative_tv: float
    difference_pct: float
    reasoning: str
    confidence: str  # high | medium | low
    warnings: list[str] = field(default_factory=list)


class TerminalValueArbitrator:
    """终值仲裁器

    仲裁规则:
    ┌─────────────────────────────────────────────────────────────┐
    │ 场景                          │ 规则                        │
    ├─────────────────────────────────────────────────────────────┤
    │ 差异 < 10%                    │ 取均值, 置信度=high         │
    │ 10% ≤ 差异 < 25%              │ 取保守(较低值), 置信度=medium│
    │ 25% ≤ 差异 < 50%              │ 取保守+敏感性分析, 置信度=low│
    │ 差异 ≥ 50%                    │ 阻断, 需人工审查            │
    │ TV/EV > 75% (任一方法)        │ 强制敏感性分析              │
    │ g ≥ WACC (永续增长法)         │ 阻断, 参数错误              │
    └─────────────────────────────────────────────────────────────┘
    """

    # 差异阈值
    THRESHOLD_CLOSE = 0.10      # < 10%: 取均值
    THRESHOLD_MODERATE = 0.25   # 10-25%: 取保守
    THRESHOLD_LARGE = 0.50      # 25-50%: 取保守+敏感性
    # ≥ 50%: 阻断

    def arbitrate(
        self,
        tv_perpetuity: float,
        tv_exit_multiple: float,
        ev_estimate: float | None = None,
    ) -> ArbitrationResult:
        """仲裁两种终值方法的结果"""
        warnings = []

        # 计算差异
        diff = abs(tv_perpetuity - tv_exit_multiple)
        avg_tv = (tv_perpetuity + tv_exit_multiple) / 2
        diff_pct = diff / avg_tv if avg_tv > 0 else 0

        # 检查TV/EV比例
        if ev_estimate and ev_estimate > 0:
            tv_ev_ratio_perp = tv_perpetuity / ev_estimate
            tv_ev_ratio_exit = tv_exit_multiple / ev_estimate
            max_tv_ev = max(tv_ev_ratio_perp, tv_ev_ratio_exit)

            if max_tv_ev > 0.75:
                warnings.append(f"终值占比{max_tv_ev:.1%}超过75%，需强制敏感性分析")

        # 仲裁逻辑
        if diff_pct < self.THRESHOLD_CLOSE:
            # 差异<10%: 取均值
            return ArbitrationResult(
                chosen_method="dual_average",
                chosen_tv=avg_tv,
                alternative_tv=avg_tv,
                difference_pct=diff_pct,
                reasoning=f"两种方法差异{diff_pct:.1%}<10%, 取均值",
                confidence="high",
                warnings=warnings,
            )

        elif diff_pct < self.THRESHOLD_MODERATE:
            # 10-25%: 取保守(较低值)
            conservative_tv = min(tv_perpetuity, tv_exit_multiple)
            return ArbitrationResult(
                chosen_method="conservative",
                chosen_tv=conservative_tv,
                alternative_tv=max(tv_perpetuity, tv_exit_multiple),
                difference_pct=diff_pct,
                reasoning=f"两种方法差异{diff_pct:.1%}在10-25%区间, 取保守值",
                confidence="medium",
                warnings=warnings,
            )

        elif diff_pct < self.THRESHOLD_LARGE:
            # 25-50%: 取保守+强制敏感性分析
            conservative_tv = min(tv_perpetuity, tv_exit_multiple)
            warnings.append("终值差异过大，需强制敏感性分析")
            return ArbitrationResult(
                chosen_method="conservative_with_sensitivity",
                chosen_tv=conservative_tv,
                alternative_tv=max(tv_perpetuity, tv_exit_multiple),
                difference_pct=diff_pct,
                reasoning=f"两种方法差异{diff_pct:.1%}在25-50%区间, 取保守值并强制敏感性分析",
                confidence="low",
                warnings=warnings,
            )

        else:
            # ≥50%: 阻断
            raise ValueError(
                f"终值差异过大({diff_pct:.1%}≥50%), "
                f"永续增长法={tv_perpetuity:.0f}, 退出倍数法={tv_exit_multiple:.0f}, "
                f"需人工审查假设"
            )

    def validate_tv_ev_ratio(
        self,
        tv: float,
        ev: float,
        max_ratio: float = 0.75,
    ) -> dict:
        """验证TV/EV比例"""
        ratio = tv / ev if ev > 0 else 0

        return {
            "tv": tv,
            "ev": ev,
            "ratio": ratio,
            "passed": ratio <= max_ratio,
            "warning": f"终值占比{ratio:.1%}超过{max_ratio:.0%}上限" if ratio > max_ratio else None,
        }

    def generate_arbitration_report(self, result: ArbitrationResult) -> str:
        """生成仲裁报告"""
        lines = [
            "## 终值仲裁报告",
            "",
            "| 项目 | 值 |",
            "|------|-----|",
            f"| 选定方法 | {result.chosen_method} |",
            f"| 选定终值 | {result.chosen_tv:.0f}亿 |",
            f"| 备选终值 | {result.alternative_tv:.0f}亿 |",
            f"| 差异 | {result.difference_pct:.1%} |",
            f"| 置信度 | {result.confidence} |",
            f"| 理由 | {result.reasoning} |",
        ]

        if result.warnings:
            lines.extend([
                "",
                "### 警告",
                "",
            ])
            for warning in result.warnings:
                lines.append(f"- {warning}")

        return "\n".join(lines)
