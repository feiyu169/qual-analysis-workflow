"""
估值仲裁器（v10 新建，HeavySkill K8 审查 P0-5/P0-6）。

ValuationArbiter 是估值模块的**唯一出口**。
gate5.py 必须只消费此结论，不得自行执行 DCF→PE→PS 降级链。

仲裁规则（K8 修订）：
- 取消固定 60/40 权重和固定 30% 阈值
- 分档处理：<20% 可加权，20-40% 披露偏差，>40% 以主方法为准
- 亏损公司不得先触发 DCF 再被覆盖
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..contracts.financials import Financials
from .method_selector import ValuationMethod, select_valuation_methods

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValuationVerdict:
    """估值仲裁结论（唯一出口，CFA Standard V-C）。"""
    target_price: float
    target_bear: float
    target_bear_assumptions: str
    target_base: float
    target_bull: float
    target_bull_assumptions: str
    upside: float               # 百分比
    method: str                 # 主方法描述
    method_details: dict        # 各方法估值结果
    reconciliation: str         # 仲裁说明（CFA V-C）
    is_loss_company: bool
    primary_method: str
    excluded_methods: list[str]
    currency: str
    data_as_of: str


class ValuationArbiter:
    """估值仲裁器（唯一出口）。"""

    def arbitrate(
        self,
        financials: Financials,
        dcf_value: float | None = None,
        ev_revenue_value: float | None = None,
        ps_value: float | None = None,
        pb_value: float | None = None,
        pe_value: float | None = None,
    ) -> ValuationVerdict:
        """仲裁估值结论。"""
        # Step 1：选择估值方法
        method_sel = select_valuation_methods(financials)

        # Step 2：收集可用估值结果
        excluded_names = {m.value if isinstance(m, ValuationMethod) else m for m in method_sel.excluded}
        available: dict[str, float] = {}
        if dcf_value and dcf_value > 0 and "DCF" not in excluded_names:
            available["DCF"] = dcf_value
        if ev_revenue_value and ev_revenue_value > 0:
            available["EV/Revenue"] = ev_revenue_value
        if ps_value and ps_value > 0:
            available["PS"] = ps_value
        if pb_value and pb_value > 0 and "PB" not in excluded_names:
            available["PB"] = pb_value
        if pe_value and pe_value > 0 and "PE" not in excluded_names:
            available["PE"] = pe_value

        # Step 3：确定主方法值
        primary_name = method_sel.primary.value
        primary_value = available.get(primary_name)

        if primary_value is None:
            for cv in method_sel.cross_validation:
                cv_name = cv.value if isinstance(cv, ValuationMethod) else cv
                if cv_name in available:
                    primary_value = available[cv_name]
                    primary_name = cv_name
                    break

        if primary_value is None:
            return self._no_value_verdict(financials, method_sel)

        # Step 4：交叉验证 + 偏差分析
        cross_values = {k: v for k, v in available.items() if k != primary_name}
        deviations: dict[str, float] = {}
        for name, value in cross_values.items():
            deviations[name] = abs(primary_value - value) / max(primary_value, value, 1e-6)

        # Step 5：仲裁（分档处理）
        if not deviations:
            target = primary_value
            method_desc = f"{primary_name}（单一方法）"
            reconciliation = f"仅 {primary_name}={primary_value:.2f} 可用，建议补充交叉验证。"
        else:
            max_dev_name = max(deviations, key=lambda k: deviations[k])
            max_dev = deviations[max_dev_name]

            if max_dev < 0.20:
                all_values = [primary_value, *list(cross_values.values())]
                target = sum(all_values) / len(all_values)
                method_desc = f"{primary_name}+{'+'.join(cross_values)} 等权（偏差 {max_dev:.0%}）"
                reconciliation = (
                    f"主方法 {primary_name}={primary_value:.2f}，"
                    f"交叉验证偏差 {max_dev:.0%}（<20%），取等权均值。"
                )
            elif max_dev < 0.40:
                target = primary_value
                method_desc = f"{primary_name}（主）+ {max_dev_name} 偏差 {max_dev:.0%}"
                reconciliation = (
                    f"主方法 {primary_name}={primary_value:.2f}，"
                    f"与 {max_dev_name}={cross_values[max_dev_name]:.2f} 偏差 {max_dev:.0%}。"
                    f"以主方法为准，偏差来源：增长假设/折现率/乘数差异。"
                )
            else:
                target = primary_value
                method_desc = f"{primary_name}（主，与 {max_dev_name} 偏差 {max_dev:.0%}）"
                reconciliation = (
                    f"主方法 {primary_name}={primary_value:.2f}，"
                    f"与 {max_dev_name}={cross_values[max_dev_name]:.2f} 偏差 {max_dev:.0%}（>40%）。"
                    f"以主方法为准，{max_dev_name} 仅作区间参考。建议检查假设。"
                )

        # Step 6：目标价区间
        if financials.is_loss_company:
            bear = target * 0.75
            bull = target * 1.30
            bear_a = "PS/EV-Rev 倍数降至行业中位数 75%"
            bull_a = "PS/EV-Rev 倍数升至 130%，叠加营收超预期"
        else:
            bear = target * 0.80
            bull = target * 1.20
            bear_a = "增长放缓 + 利润率压缩"
            bull_a = "增长超预期 + 利润率扩张"

        upside = (target / financials.current_price - 1) * 100 if financials.current_price > 0 else 0

        return ValuationVerdict(
            target_price=round(target, 2),
            target_bear=round(bear, 2),
            target_bear_assumptions=bear_a,
            target_base=round(target, 2),
            target_bull=round(bull, 2),
            target_bull_assumptions=bull_a,
            upside=round(upside, 1),
            method=method_desc,
            method_details=available,
            reconciliation=reconciliation,
            is_loss_company=financials.is_loss_company,
            primary_method=primary_name,
            excluded_methods=list(excluded_names),
            currency=financials.currency,
            data_as_of=financials.report_date,
        )

    def _no_value_verdict(
        self, financials: Financials, method_sel: object,
    ) -> ValuationVerdict:
        """全部不可用时的结论。"""
        excluded = getattr(method_sel, "excluded", [])
        return ValuationVerdict(
            target_price=0, target_bear=0, target_bear_assumptions="",
            target_base=0, target_bull=0, target_bull_assumptions="",
            upside=0, method="不适用", method_details={},
            reconciliation="所有估值方法均不可用，无法给出估值结论。",
            is_loss_company=financials.is_loss_company,
            primary_method="无",
            excluded_methods=[str(m) for m in excluded],
            currency=financials.currency,
            data_as_of=financials.report_date,
        )
