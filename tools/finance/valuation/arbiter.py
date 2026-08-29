"""
估值仲裁器（v10，治理方案 v3.0 Phase 2 配置化）。

ValuationArbiter 是估值模块的**唯一出口**。
gate5.py 必须只消费此结论，不得自行执行 DCF→PE→PS 降级链。

仲裁规则（从 valuation_thresholds.yaml 加载，不再硬编码）：
- 分公司类型差异化阈值（亏损/盈利/周期/高杠杆/金融）
- 分档处理：<阈值 可加权，阈值-警告阈值 披露偏差，>警告阈值 以主方法为准
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
    rating: str                 # 投资评级（买入/增持/中性/减持/卖出）
    rating_rationale: str       # 评级理由
    method: str                 # 主方法描述
    method_details: dict        # 各方法估值结果
    reconciliation: str         # 仲裁说明（CFA V-C）
    is_loss_company: bool
    primary_method: str
    excluded_methods: list[str]
    currency: str
    data_as_of: str


class ValuationArbiter:
    """估值仲裁器（唯一出口，配置从 valuation_thresholds.yaml 加载）。"""

    def __init__(self, config_path: str | None = None) -> None:
        """初始化仲裁器，加载阈值配置。"""
        import os
        _default = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "config", "valuation_thresholds.yaml",
        )
        self._config_path = config_path or _default
        self._config = self._load_config()

    def _load_config(self) -> dict:
        """加载阈值配置。"""
        try:
            import yaml
            with open(self._config_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def _get_threshold(self, company_type: str = "default") -> float:
        """获取公司类型对应的自洽阈值。"""
        by_type = self._config.get("convergence", {}).get("by_type", {})
        if company_type in by_type:
            return by_type[company_type].get("threshold", 0.30)
        return self._config.get("convergence", {}).get("default_threshold", 0.30)

    def _get_exceed_warning_threshold(self, company_type: str = "default") -> float:
        """获取超阈值警告线。"""
        by_type = self._config.get("convergence", {}).get("by_type", {})
        if company_type in by_type:
            return by_type[company_type].get("exceed_warning_threshold", 0.40)
        return 0.40

    def _classify_company(self, financials: Financials) -> str:
        """根据财务数据自动分类公司类型。"""
        if financials.is_loss_company:
            if financials.has_positive_ocf:
                return "loss_with_ocf"
            return "loss_no_ocf"
        if financials.leverage > 0.7:
            return "high_leverage"
        return "profitable_stable"

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

        # Step 5：仲裁（从配置加载阈值，不再硬编码）
        company_type = self._classify_company(financials)
        threshold = self._get_threshold(company_type)
        warn_threshold = self._get_exceed_warning_threshold(company_type)

        if not deviations:
            target = primary_value
            method_desc = f"{primary_name}（单一方法）"
            reconciliation = f"仅 {primary_name}={primary_value:.2f} 可用，建议补充交叉验证。"
        else:
            max_dev_name = max(deviations, key=lambda k: deviations[k])
            max_dev = deviations[max_dev_name]

            if max_dev < threshold:
                all_values = [primary_value, *list(cross_values.values())]
                target = sum(all_values) / len(all_values)
                method_desc = f"{primary_name}+{'+'.join(cross_values)} 等权（偏差 {max_dev:.0%}）"
                reconciliation = (
                    f"主方法 {primary_name}={primary_value:.2f}，"
                    f"交叉验证偏差 {max_dev:.0%}（<{threshold:.0%}），取等权均值。"
                )
            elif max_dev < warn_threshold:
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

        # v10 Phase 2：评级-目标价映射（从配置加载阈值）
        rating_thresholds = self._config.get("convergence", {}).get("rating_thresholds", {})
        rating, rating_rationale = _derive_rating(
            upside,
            buy_threshold=rating_thresholds.get("buy", 0.30),
            overweight_threshold=rating_thresholds.get("overweight", 0.15),
        )

        return ValuationVerdict(
            target_price=round(target, 2),
            target_bear=round(bear, 2),
            target_bear_assumptions=bear_a,
            target_base=round(target, 2),
            target_bull=round(bull, 2),
            target_bull_assumptions=bull_a,
            upside=round(upside, 1),
            rating=rating,
            rating_rationale=rating_rationale,
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
            upside=0, rating="无", rating_rationale="估值方法不可用",
            method="不适用", method_details={},
            reconciliation="所有估值方法均不可用，无法给出估值结论。",
            is_loss_company=financials.is_loss_company,
            primary_method="无",
            excluded_methods=[str(m) for m in excluded],
            currency=financials.currency,
            data_as_of=financials.report_date,
        )


def _derive_rating(
    upside_pct: float,
    buy_threshold: float = 0.30,
    overweight_threshold: float = 0.15,
) -> tuple[str, str]:
    """根据上行空间推导投资评级（CFA V-B，阈值从配置加载）。

    Args:
        upside_pct: 上行空间百分比
        buy_threshold: 买入阈值（默认 30%）
        overweight_threshold: 增持阈值（默认 15%）

    Returns:
        (评级, 理由)
    """
    buy_pct = buy_threshold * 100
    ow_pct = overweight_threshold * 100
    if upside_pct >= buy_pct:
        return "买入", f"上行空间 {upside_pct:.1f}%（≥{buy_pct:.0f}%），估值显著低估"
    elif upside_pct >= ow_pct:
        return "增持", f"上行空间 {upside_pct:.1f}%（{ow_pct:.0f}-{buy_pct:.0f}%），估值温和低估"
    elif upside_pct >= -ow_pct:
        return "中性", f"上行/下行空间 {upside_pct:.1f}%（±{ow_pct:.0f}%），估值合理"
    elif upside_pct >= -buy_pct:
        return "减持", f"下行空间 {abs(upside_pct):.1f}%（{ow_pct:.0f}-{buy_pct:.0f}%），估值温和高估"
    else:
        return "卖出", f"下行空间 {abs(upside_pct):.1f}%（≥{buy_pct:.0f}%），估值显著高估"
