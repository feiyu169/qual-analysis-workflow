"""
Gate 1: 类型推断 + 数据提取
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..core.gate_engine import GateBase, GateResult, GateSpec

logger = logging.getLogger(__name__)

# Gate1 required_fields（英文）→ FinancialFacts 属性名
_FACT_FIELD_MAP = {
    "revenue": "revenue",
    "net_income": "net_profit",
    "operating_income": "operating_margin",  # 营业利润 → 财务表无 operating_income 字段，用 operating_margin 占位
    "operating_cash_flow": "operating_cashflow",
    "total_assets": "total_assets",
}


@dataclass
class TypeInferenceConfig:
    """类型推断配置"""
    allowed_markets: list[str]
    required_fields: list[str]
    max_deviation: float


class Gate1TypeInference(GateBase):
    """Gate 1: 类型推断 + 数据提取"""

    def __init__(self):
        spec = GateSpec(
            gate_num=1,
            name="类型推断 + 数据提取",
            description="市场类型推断和结构化事实提取",
            prerequisites=[0],  # 依赖Gate 0
            timeout=300,  # 5分钟
            max_retries=3,
            pass_criteria=[
                {"name": "市场类型正确", "type": "condition", "condition": "market_type_valid"},
                {"name": "必填字段提取", "type": "condition", "condition": "required_fields_extracted"},
                {"name": "数值偏差", "type": "quantitative", "metric": "value_deviation", "threshold": 0.02},
                {"name": "Schema合规", "type": "condition", "condition": "schema_compliant"},
            ],
        )
        super().__init__(spec)

        self.config = TypeInferenceConfig(
            allowed_markets=["A股", "港股", "美股"],
            # operating_income（营业利润）非事实提取强制输出，从必填移除
            required_fields=["revenue", "net_income", "total_assets", "operating_cash_flow"],
            max_deviation=0.02,
        )

    def execute(self, context: dict[str, Any]) -> GateResult:
        """执行Gate 1（真实：市场推断 + 事实提取 + Wind 交叉验证）"""
        errors = []
        warnings = []
        details = {}

        # 1. 推断市场类型（真实：infer_market）
        market_type = self._infer_market_type(context)
        details["market_type"] = market_type

        if market_type not in self.config.allowed_markets:
            errors.append(f"市场类型无效: {market_type}")

        # 2. 提取结构化事实（真实：fact_extractor.extract_facts，返回 ExtractedFacts 对象）
        facts = self._extract_facts(context)
        details["facts"] = _facts_to_dict(facts) if not isinstance(facts, dict) else facts

        # quick 模式：事实提取 SKIPPED 时跳过必填字段/偏差检查（不阻断检查链）
        facts_skipped = (context.get("gate_1_result") or {}).get("facts_skipped", False)

        # 3. 验证必填字段
        if not facts_skipped:
            missing_fields = self._check_required_fields(facts)
            if missing_fields:
                errors.append(f"缺少必填字段: {missing_fields}")

        # 4. 验证数值偏差（真实：与 Wind canonical 值比对）
        deviation = 0.0
        if not facts_skipped:
            deviation = self._check_value_deviation(facts, context.get("wind_data", {}))
            details["deviation"] = deviation

            if deviation > self.config.max_deviation:
                errors.append(f"数值偏差过大: {deviation:.2%}")

        # 5. 计算得分
        score = 100.0
        if errors:
            score -= len(errors) * 25
        score = max(0.0, min(100.0, score))

        passed = len(errors) == 0

        # 6. 写入 context 供后续 Gate 使用（合并，保留 _extract_facts 设置的 facts_skipped）
        #    P0-B2: context["facts"] 存**完整 ExtractedFacts 对象**（供 Gate3 仲裁/format 使用），
        #    另存 dict 视图供 check_criteria 与详情
        context["facts"] = facts
        context["facts_dict"] = _facts_to_dict(facts) if not isinstance(facts, dict) else facts
        context["market_type"] = market_type
        g1 = dict(context.get("gate_1_result") or {})
        g1.update({
            "market_type": market_type,
            "facts_keys": list(context["facts_dict"].keys()) if isinstance(context["facts_dict"], dict) else str(type(facts)),
            "deviation": deviation,
            "passed": passed,
            "facts_skipped": (context.get("gate_1_result") or {}).get("facts_skipped", False),
        })
        context["gate_1_result"] = g1

        return GateResult(
            gate_num=1,
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
        market_type = context.get("market_type")

        # quick 模式：事实提取 SKIPPED 时放行（检查链继续）
        if (context.get("gate_1_result") or {}).get("facts_skipped", False):
            return True

        # 检查市场类型
        if market_type not in self.config.allowed_markets:
            return False

        # 检查必填字段（用 facts_dict（dict 视图）或对象）
        facts = context.get("facts_dict") or context.get("facts", {})
        if hasattr(facts, "financial"):
            for field in self.config.required_fields:
                attr = _FACT_FIELD_MAP.get(field, field)
                if not hasattr(facts.financial, attr) or getattr(facts.financial, attr, None) is None:
                    return False
            return True
        for field in self.config.required_fields:
            if field not in facts:
                return False

        return True

    def _infer_market_type(self, context: dict[str, Any]) -> str:
        """推断市场类型（真实：finance.workflow.infer_market）"""
        ticker = context.get("ticker", "")
        try:
            from ...workflow import infer_market
            market = infer_market(ticker)
            return {"cn": "A股", "hk": "港股", "us": "美股"}.get(market, "未知")
        except Exception:
            if ticker.endswith((".SH", ".SZ")):
                return "A股"
            elif ticker.endswith(".HK"):
                return "港股"
            elif ticker.endswith((".OQ", ".N")):
                return "美股"
            return "未知"

    def _extract_facts(self, context: dict[str, Any]) -> dict[str, Any]:
        """提取结构化事实（真实：fact_extractor.extract_facts，P0-B1 财年锚定）

        返回**完整 ExtractedFacts 对象**（保留 fiscal_year/report_type，供 Gate3 仲裁与 format 使用）；
        无 llm_caller 时降级：若已有预填章节（quick 模式），标记跳过并返回空 dict
        （事实提取是可选增强，不阻断检查链）。
        """
        filing_data = context.get("filing_data") or {}
        sections = filing_data.get("sections") or {}
        wind_data = context.get("wind_data") or {}
        llm_caller = context.get("llm_caller")
        ticker = context.get("ticker", "")
        company_name = context.get("company_name", "")
        market = context.get("market", "hk")

        if llm_caller is None:
            pre_filled = context.get("chapters")
            if pre_filled:
                logger.info("Gate1: 无 llm_caller 且已有章节（quick 模式），事实提取标记 SKIPPED")
                context["gate_1_result"] = {"facts_skipped": True}
                return {}
            logger.warning("Gate1: 无 sections 或 llm_caller，事实提取降级为空")
            return {}

        if not sections:
            logger.warning("Gate1: 无 sections，事实提取降级为空")
            return {}

        # P0-B1: 财年锚定（filing metadata → Wind labels[-1]）
        fiscal_year = None
        try:
            fy_meta = (filing_data.get("metadata") or {}).get("fiscal_year")
            if fy_meta:
                fiscal_year = int(fy_meta)
        except (TypeError, ValueError):
            fiscal_year = None
        if fiscal_year is None and wind_data:
            try:
                labels = (wind_data.get("_year_labels") or {}).get("财年") or []
                if labels:
                    fiscal_year = int(labels[-1])
            except (TypeError, ValueError):
                fiscal_year = None

        try:
            from ...fact_extractor import extract_facts as real_extract
            result = real_extract(
                sections=sections,
                company_name=company_name,
                ticker=ticker,
                market=market,
                llm_caller=llm_caller,
                wind_data=wind_data,
                fiscal_year=fiscal_year,
            )

            # B3-1：多财年提取——对 prior_years（旧年 sections）每份单独提取，程序化合并
            prior_years = (filing_data.get("metadata") or {}).get("prior_years") or {}
            if prior_years and result is not None:
                by_year = {int(fiscal_year): result} if fiscal_year else {}
                for fy, fy_sections in sorted(prior_years.items()):
                    if not fy_sections:
                        continue
                    try:
                        fy_result = real_extract(
                            sections=fy_sections,
                            company_name=company_name,
                            ticker=ticker,
                            market=market,
                            llm_caller=llm_caller,
                            wind_data=wind_data,
                            fiscal_year=int(fy),
                        )
                        if fy_result is not None:
                            by_year[int(fy)] = fy_result
                            logger.info(f"Gate1 多财年提取: FY{fy} 完成")
                    except Exception as e:
                        logger.warning(f"Gate1 多财年提取 FY{fy} 失败: {e}")
                if by_year:
                    result.by_year = by_year
                    logger.info(f"Gate1 多财年事实表: {sorted(by_year.keys())} 年（B3-1）")

            return result
        except Exception as e:
            import traceback as _tb
            logger.error(f"Gate1 事实提取失败: {e}\n{_tb.format_exc()}")
            return {}

    def _check_required_fields(self, facts: dict[str, Any]) -> list[str]:
        """检查必填字段（兼容 ExtractedFacts 对象或 dict）"""
        if hasattr(facts, "financial"):
            # ExtractedFacts 对象
            fin = facts.financial
            missing = []
            for field in self.config.required_fields:
                if not hasattr(fin, _FACT_FIELD_MAP.get(field, field)) or getattr(fin, _FACT_FIELD_MAP.get(field, field), None) is None:
                    missing.append(field)
            return missing
        missing = []
        for field in self.config.required_fields:
            if field not in facts:
                missing.append(field)
        return missing

    def _check_value_deviation(self, facts: dict[str, Any], wind_data: dict[str, Any]) -> float:
        """检查数值偏差（真实：与 Wind canonical 最新值比对；兼容 ExtractedFacts 对象/dict）"""
        if not wind_data:
            return 0.0

        from ..adapters import get_latest_wind_value

        # 归一为 dict
        fd = facts if isinstance(facts, dict) else _facts_to_dict(facts)

        deviations = []
        # facts 的字段 → Wind canonical 键
        field_map = {
            "revenue": "营业收入",
            "net_income": "归母净利润",
            "operating_income": "营业利润",
            "operating_cash_flow": "经营活动现金流量净额",
            "total_assets": "总资产",
        }
        for fact_field, wind_canonical in field_map.items():
            fact_value = fd.get(fact_field)
            if fact_value is None:
                continue
            wind_value = get_latest_wind_value(wind_data, wind_canonical)
            if wind_value is None or wind_value == 0:
                continue
            deviations.append(abs(fact_value - wind_value) / abs(wind_value))

        return sum(deviations) / len(deviations) if deviations else 0.0


def _facts_to_dict(facts) -> dict[str, Any]:
    """ExtractedFacts → dict（键与 Gate1 required_fields 对齐：
    revenue / net_income / operating_cash_flow / total_assets / operating_income）"""
    out = {}
    if facts is None:
        return out
    fin = getattr(facts, "financial", None)
    if fin is not None:
        for attr, key in [
            ("revenue", "revenue"),
            ("net_profit", "net_income"),
            ("gross_margin", "gross_margin"),
            ("operating_cashflow", "operating_cash_flow"),
            ("total_assets", "total_assets"),
            ("total_liabilities", "total_liabilities"),
            ("equity", "equity"),
        ]:
            v = getattr(fin, attr, None)
            if v is not None:
                out[key] = v
    return out
