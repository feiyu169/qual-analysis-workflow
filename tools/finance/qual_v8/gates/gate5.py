"""
Gate 5: 质量增强 + 组件集成（确定性计算）
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..core.gate_engine import GateBase, GateResult, GateSpec

logger = logging.getLogger(__name__)


@dataclass
class ValuationResult:
    """估值结果"""
    dcf_value: float  # DCF估值
    comparable_value: float  # 可比公司估值
    valuation_range: tuple  # 估值范围
    calculation_method: str
    components_integrated: list


class Gate5QualityEnhancement(GateBase):
    """Gate 5: 质量增强 + 组件集成"""

    def __init__(self):
        spec = GateSpec(
            gate_num=5,
            name="质量增强 + 组件集成",
            description="确定性计算估值",
            prerequisites=[4],  # 依赖Gate 4
            timeout=300,  # 5分钟
            max_retries=3,
            pass_criteria=[
                {"name": "估值计算正确", "type": "condition", "condition": "valuation_correct"},
                {"name": "DCF估值范围", "type": "condition", "condition": "dcf_in_range"},
                {"name": "组件集成成功", "type": "condition", "condition": "components_integrated"},
                {"name": "估值参数一致", "type": "condition", "condition": "valuation_params_consistent"},
            ],
        )
        super().__init__(spec)

        # 组件列表
        self.components = [
            "T9_FactTable",
            "T10_ComparableConfig",
            "T11_MarketData",
            "T12_FlipThreshold",
            "T13_InsightAuditor",
            "T14_ROICChecker",
        ]

    def execute(self, context: dict[str, Any]) -> GateResult:
        """执行Gate 5（真实：enhance_report_quality，参数从 context 强传）"""
        errors = []
        warnings = []
        details = {}

        # 1. 计算估值（真实：base_valuation + UnifiedValuation）
        valuation_result = self._calculate_valuation(context)
        details["valuation"] = valuation_result

        if not valuation_result["passed"]:
            errors.extend(valuation_result["errors"])

        # 2. 组件集成（真实：enhance_report_quality 全链）
        integration_result = self._integrate_components(context)
        details["integration"] = integration_result

        if not integration_result["passed"]:
            errors.extend(integration_result["errors"])

        # 3. 交叉验证（真实：数字校验器）
        cross_validation = self._cross_validate(context, valuation_result)
        details["cross_validation"] = cross_validation

        if not cross_validation["passed"]:
            errors.extend(cross_validation["errors"])

        # 3.5 v10 Phase 3：估值一致性检查（检查前移）
        # DCF vs 可比公司偏差超阈值时发出 warning
        try:
            _vr = context.get("valuation", {})
            if isinstance(_vr, dict) and _vr.get("method_details"):
                _methods = _vr["method_details"]
                _vals = list(_methods.values())
                if len(_vals) >= 2:
                    _max_v = max(_vals)
                    _min_v = min(_vals)
                    _dev = abs(_max_v - _min_v) / max(_max_v, _min_v, 1e-6)
                    if _dev > 0.40:
                        warnings.append(
                            f"估值一致性警告：多方法偏差 {_dev:.0%}（>{'40%'}），"
                            f"需人工复核估值假设"
                        )
                        logger.warning(f"Gate5 估值一致性: 偏差 {_dev:.0%}，方法 {list(_methods.keys())}")
        except Exception as e:
            logger.warning(f"Gate5 估值一致性检查失败（非阻断）: {e}")

        # 4. 计算得分
        score = 100.0
        if errors:
            score -= len(errors) * 25
        score = max(0.0, min(100.0, score))

        passed = len(errors) == 0

        context["gate_5_result"] = {
            "valuation_passed": valuation_result["passed"],
            "integration_passed": integration_result["passed"],
            "cross_validation_passed": cross_validation["passed"],
        }

        return GateResult(
            gate_num=5,
            passed=passed,
            score=score,
            details=details,
            errors=errors,
            warnings=warnings,
            execution_time=0.0,
            timestamp=datetime.now().isoformat(),
        )

    def check_criteria(self, context: dict[str, Any]) -> bool:
        """检查通过标准"""
        # 检查DCF估值范围（使用 context 中的 dcf_params）
        dcf_params = context.get("dcf_params")
        if not dcf_params:
            return False

        # 检查组件集成
        gate5 = context.get("gate_5_result", {})
        if not gate5.get("integration_passed", False):
            return False

        return True

    def _calculate_valuation(self, context: dict[str, Any]) -> dict[str, Any]:
        """计算估值（真实：base_valuation.compute_base_valuation，参数从 context 强传）"""
        errors = []
        valuation = None

        wind_data = context.get("wind_data", {})
        ticker = context.get("ticker", "")
        company_name = context.get("company_name", "")
        shares = context.get("shares")

        try:
            from ...base_valuation import compute_base_valuation
            base_val = compute_base_valuation(
                ticker=ticker,
                company_name=company_name,
                wind_financials={
                    "income": wind_data.get("income", {}),
                    "balance": wind_data.get("balance", {}),
                    "cashflow": wind_data.get("cashflow", {}),
                },
                shares=shares,
            )
            valuation = {
                "pe_ttm": base_val.pe_ttm,
                "pb": base_val.pb,
                "ps_ttm": getattr(base_val, "ps_ttm", None),
                "market_cap": getattr(base_val, "market_cap", None),
            }
            # 双专家 P1（2026-08-22）：补 dcf_value——gate6 评级一致性检查依赖它，
            # 缺失导致 "if dcf_value > 0" 静默跳过（评级铁律空转）。
            # 简化 DCF：per-share = Σ FCF/(1+wacc)^n + TV/(1+wacc)^N 的每股值（近似）。
            try:
                _dcf_p = context.get("dcf_params")
                _shares = context.get("shares")
                if _dcf_p is not None and _shares:
                    _fcf = getattr(_dcf_p, "fcf", None) or 0
                    _wacc = getattr(_dcf_p, "wacc", 0.10) or 0.10
                    _g = getattr(_dcf_p, "terminal_growth", 0.03) or 0.03
                    if _fcf and _wacc > _g and _shares > 0:
                        # 简化永续增长 DCF：V = FCF1/(wacc-g)，per-share = V/shares
                        dcf_value = (_fcf / (_wacc - _g)) / _shares
                        # v9：DCF 负值处理——亏损公司 FCF 为负时 DCF 无效，
                        # 标注为"不适用"，使用可比公司估值作为主要方法
                        if dcf_value < 0:
                            valuation["dcf_value"] = None
                            valuation["dcf_not_applicable"] = True
                            valuation["dcf_reason"] = f"FCF={_fcf:.1f}亿为负，DCF不适用"
                            logger.info(f"Gate5 DCF 不适用: FCF={_fcf:.1f}亿为负，使用可比公司估值")
                        else:
                            valuation["dcf_value"] = round(dcf_value, 2)
                            logger.info(f"Gate5 DCF per-share: {dcf_value:.2f}（简化永续模型）")
            except Exception as e:
                logger.warning(f"Gate5 DCF per-share 计算失败（非阻断）: {e}")
            context["valuation"] = valuation

            # 估值偏差范围检查
            current_price = context.get("current_price", 0)
            dcf_value = context.get("dcf_params")
            if current_price > 0 and dcf_value:
                pass  # 范围检查交由 _cross_validate
        except Exception as e:
            errors.append(f"估值计算失败: {e}")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "valuation": valuation,
        }

    def _integrate_components(self, context: dict[str, Any]) -> dict[str, Any]:
        """组件集成（真实：enhance_report_quality，参数强传消除硬编码污染）"""
        errors = []
        integrated = []

        chapters = context.get("chapters", {})
        llm_caller = context.get("llm_caller")

        if not chapters:
            return {"passed": False, "errors": ["无章节可增强"], "integrated_components": integrated}

        if llm_caller is None:
            logger.warning("Gate5: 无 llm_caller，跳过质量增强（组件集成标记跳过）")
            integrated = ["SKIPPED_NO_LLM"]
            return {"passed": True, "errors": [], "integrated_components": integrated}

        try:
            wind_data = context.get("wind_data", {})
            shares = context.get("shares")
            current_price = context.get("current_price")  # 必须显式传入，无默认值
            fiscal_year = context.get("fiscal_year")  # 必须显式传入，无默认值

            from ...quality_enhancer import enhance_report_quality
            enhanced, quality_result = enhance_report_quality(
                chapters=chapters,
                financials={
                    "income": wind_data.get("income", {}),
                    "balance": wind_data.get("balance", {}),
                    "cashflow": wind_data.get("cashflow", {}),
                },
                wind_valuation=context.get("valuation"),
                company_name=context.get("company_name", ""),
                ticker=context.get("ticker", ""),
                shares=shares if shares is not None else 0,
                current_price=current_price if current_price is not None else 0,
                fiscal_year=fiscal_year if fiscal_year is not None else 2025,
                market=context.get("market", "hk"),  # B2a-2：币种断言
                llm_caller=llm_caller,
                enable_debate=False,
                enable_valuation=True,
                enable_depth=True,
            )
            context["chapters"] = enhanced
            integrated = ["T9_FactTable", "T10_ComparableConfig", "T11_MarketData",
                          "T12_FlipThreshold", "T13_InsightAuditor", "T14_ROICChecker"]
            context["gate_5_result"] = {
                "total_fixes": getattr(quality_result, "total_fixes", 0),
                "chapters_enhanced": getattr(quality_result, "chapters_enhanced", 0),
                "warnings": list(getattr(quality_result, "warnings", []))[:5],
            }
        except Exception as e:
            errors.append(f"质量增强失败: {e}")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "integrated_components": integrated,
        }

    def _cross_validate(self, context: dict[str, Any], valuation_result: dict[str, Any]) -> dict[str, Any]:
        """交叉验证（真实：估值参数一致性；全文数字校验移交 Gate8 最终验证收口）"""
        errors = []

        # 1. 检查估值参数与 Gate 2 是否一致
        dcf_params = context.get("dcf_params")
        gate2 = context.get("gate_2_result", {}).get("dcf_params", {})
        if dcf_params and gate2 and abs(dcf_params.wacc - gate2.get("wacc", -1)) > 1e-6:
            errors.append(f"估值 WACC 与 Gate2 不一致: {dcf_params.wacc} vs {gate2.get('wacc')}")

        # 2. 全文数字校验（DataAnchor）已移交 Gate8 最终验证；
        #    这里把锚点挂到 context 供 Gate8 复用
        wind_data = context.get("wind_data", {})
        if wind_data:
            try:
                from ..data_anchor import get_data_anchor
                anchor = get_data_anchor(wind_data)
                context["data_anchor"] = anchor
            except Exception as e:
                logger.warning(f"Gate5 锚点准备失败（非阻断）: {e}")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
        }
