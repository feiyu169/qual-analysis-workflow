"""
Gate 2: 数据收集 + 参数提取（确定性计算）
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..core.gate_engine import GateBase, GateResult, GateSpec

logger = logging.getLogger(__name__)


@dataclass
class DCFParams:
    """DCF参数"""
    fcf: float  # 自由现金流
    wacc: float  # 加权平均资本成本
    terminal_growth: float  # 永续增长率
    revenue_growth: float  # 营收增长率
    tax_rate: float  # 税率
    calculation_formula: str
    data_source: str


class Gate2DataCollection(GateBase):
    """Gate 2: 数据收集 + 参数提取"""
    
    def __init__(self):
        spec = GateSpec(
            gate_num=2,
            name="数据收集 + 参数提取",
            description="确定性计算DCF参数",
            prerequisites=[1],  # 依赖Gate 1
            timeout=180,  # 3分钟
            max_retries=3,
            pass_criteria=[
                {"name": "FCF非零", "type": "condition", "condition": "fcf_nonzero"},
                {"name": "WACC范围", "type": "condition", "condition": "wacc_in_range"},
                {"name": "永续增长率范围", "type": "condition", "condition": "terminal_growth_in_range"},
                {"name": "营收增长率范围", "type": "condition", "condition": "revenue_growth_in_range"},
                {"name": "税率范围", "type": "condition", "condition": "tax_rate_in_range"},
            ],
        )
        super().__init__(spec)
        
        # 参数范围配置（FCF 允许为负：亏损/投资期公司 FCF<0 是真实状态，只要求非零）
        self.param_ranges = {
            "fcf": {"min": float("-inf"), "max": float("inf"), "nonzero": True},
            "wacc": {"min": 0.05, "max": 0.15},
            "terminal_growth": {"min": 0.01, "max": 0.05},
            "revenue_growth": {"min": -0.30, "max": 1.00},
            "tax_rate": {"min": 0.10, "max": 0.35},
        }
    
    def execute(self, context: dict[str, Any]) -> GateResult:
        """执行Gate 2（真实：Wind→canonical DCF 参数 + 初始化数据锚点）"""
        errors = []
        warnings = []
        details = {}

        # 1. 提取DCF参数（真实：finance.workflow.extract_dcf_params）
        dcf_params = self._extract_dcf_params(context)
        details["dcf_params"] = dcf_params

        # 2. 初始化 DataAnchor（唯一数据源：Wind canonical 多财年锚点）
        anchor_result = self._init_data_anchor(context)
        details["data_anchor"] = anchor_result
        context["data_anchor"] = anchor_result.get("anchor")

        # 3. 验证参数范围
        validation_errors = self._validate_params(dcf_params)
        errors.extend(validation_errors)

        # 4. 计算得分
        score = 100.0
        if errors:
            score -= len(errors) * 20
        score = max(0.0, min(100.0, score))

        passed = len(errors) == 0

        # 5. 写入 context
        context["dcf_params"] = dcf_params
        context["gate_2_result"] = {
            "dcf_params": {
                "fcf": dcf_params.fcf, "wacc": dcf_params.wacc,
                "terminal_growth": dcf_params.terminal_growth,
                "revenue_growth": dcf_params.revenue_growth,
                "tax_rate": dcf_params.tax_rate,
            },
            "anchor_count": anchor_result.get("count", 0),
        }

        return GateResult(
            gate_num=2,
            passed=passed,
            score=score,
            details=details,
            errors=errors,
            warnings=warnings,
            execution_time=0.0,
            timestamp=datetime.now().isoformat(),  # noqa: DTZ005
        )

    def check_criteria(self, context: dict[str, Any]) -> bool:
        """检查通过标准"""
        dcf_params = context.get("dcf_params")
        if not dcf_params:
            return False

        # 检查各参数范围（FCF 允许为负，只要求非零）
        checks = [
            dcf_params.fcf != 0,
            self._check_range(dcf_params.wacc, self.param_ranges["wacc"]),
            self._check_range(dcf_params.terminal_growth, self.param_ranges["terminal_growth"]),
            self._check_range(dcf_params.revenue_growth, self.param_ranges["revenue_growth"]),
            self._check_range(dcf_params.tax_rate, self.param_ranges["tax_rate"]),
        ]

        return all(checks)

    def _extract_dcf_params(self, context: dict[str, Any]) -> DCFParams:
        """提取DCF参数（真实：finance.workflow.extract_dcf_params，canonical 键）"""
        wind_data = context.get("wind_data", {})
        shares = context.get("shares")

        try:
            from ...workflow import extract_dcf_params as real_extract
            params = real_extract(wind_data, shares=shares)
            return DCFParams(
                fcf=float(params.get("fcf_base", 0) or 0),
                wacc=float(params.get("wacc", 0.10) or 0.10),
                terminal_growth=float(params.get("terminal_growth", 0.03) or 0.03),
                revenue_growth=float(params.get("growth_rate", 0.05) or 0.05),
                tax_rate=0.25,
                calculation_formula="FCF = OCF - Capex; WACC = CAPM (finance.workflow.extract_dcf_params)",
                data_source="Wind canonical",
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"Gate2 真实 DCF 提取失败: {e}，回退确定性计算")
            # 回退：确定性计算（canonical 键）
            income = wind_data.get("income", {})
            balance = wind_data.get("balance", {})
            cashflow = wind_data.get("cashflow", {})

            ocf_list = cashflow.get("经营活动现金流量净额") or [0]
            capex_list = cashflow.get("购建固定资产、无形资产和其他长期资产支付的现金") or [0]
            ocf = float(ocf_list[-1] or 0) if ocf_list else 0
            capex = float(capex_list[-1] or 0) if capex_list else 0
            fcf = ocf - capex

            risk_free_rate = 0.03
            beta = 1.2
            market_risk_premium = 0.06
            cost_of_equity = risk_free_rate + beta * market_risk_premium

            total_assets = 0
            debt_list = balance.get("年负债合计") or [0]
            total_debt = float(debt_list[-1] or 0) if debt_list else 0
            asset_list = balance.get("总资产") or [0]
            total_assets = float(asset_list[-1] or 0) if asset_list else 0
            debt_ratio = total_debt / total_assets if total_assets > 0 else 0

            cost_of_debt = 0.05
            tax_rate = 0.25
            wacc = (1 - debt_ratio) * cost_of_equity + debt_ratio * cost_of_debt * (1 - tax_rate)

            revenue_growth = 0.05
            rev_list = income.get("营业收入") or []
            if len(rev_list) >= 2:
                try:
                    rev = [float(v) for v in rev_list if v and float(v) > 0]
                    if len(rev) >= 2 and rev[0] > 0:
                        cagr = (rev[-1] / rev[0]) ** (1.0 / (len(rev) - 1)) - 1.0
                        revenue_growth = max(0.01, min(cagr, 0.15))
                except (ValueError, TypeError, ZeroDivisionError):
                    pass
            terminal_growth = min(revenue_growth * 0.5, 0.05)

            return DCFParams(
                fcf=fcf, wacc=wacc, terminal_growth=terminal_growth,
                revenue_growth=revenue_growth, tax_rate=tax_rate,
                calculation_formula="FCF = OCF - Capex (fallback)",
                data_source="Wind canonical (fallback)",
            )

    def _init_data_anchor(self, context: dict[str, Any]) -> dict[str, Any]:
        """初始化 DataAnchor（真实：Wind canonical 多财年锚点）"""
        wind_data = context.get("wind_data")
        if not wind_data:
            return {"count": 0, "anchor": None}
        try:
            from ..data_anchor import get_data_anchor
            anchor = get_data_anchor(wind_data)
            context["data_anchor"] = anchor
            return {
                "count": len(anchor.get_all_anchors()),
                "latest_fy": anchor.get_latest_fiscal_year(),
                "anchor": anchor,
            }
        except Exception as e:  # noqa: BLE001
            logger.error(f"Gate2 DataAnchor 初始化失败: {e}")
            return {"count": 0, "anchor": None}

    def _validate_params(self, dcf_params: DCFParams) -> list:
        """验证参数范围"""
        errors = []
        warnings = []

        checks = [
            ("FCF", dcf_params.fcf, self.param_ranges["fcf"]),
            ("WACC", dcf_params.wacc, self.param_ranges["wacc"]),
            ("永续增长率", dcf_params.terminal_growth, self.param_ranges["terminal_growth"]),
            ("营收增长率", dcf_params.revenue_growth, self.param_ranges["revenue_growth"]),
            ("税率", dcf_params.tax_rate, self.param_ranges["tax_rate"]),
        ]

        for name, value, range_config in checks:
            # FCF 特殊：允许为负（亏损/投资期），只要求非零
            if name == "FCF" and value == 0:
                errors.append("FCF=0，估值无意义")
                continue
            if not self._check_range(value, range_config):
                if name == "FCF" and value < 0:
                    warnings.append(f"{name}={value:.2f}为负（公司处于亏损/投资期，属真实状态，不阻断）")
                    continue
                errors.append(f"{name}={value:.2%}超出合理范围[{range_config['min']:.2%}, {range_config['max']:.2%}]")

        return errors

    def _check_range(self, value: float, range_config: dict) -> bool:
        """检查值是否在范围内"""
        return range_config["min"] <= value <= range_config["max"]
