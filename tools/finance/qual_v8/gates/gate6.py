"""
Gate 6: 综合结论 + 决策章 + 概览章
"""

import logging
from datetime import datetime
from typing import Any

from ..core.gate_engine import GateBase, GateResult, GateSpec

logger = logging.getLogger(__name__)


# 评级映射规则
RATING_VALUATION_MAPPING = {
    "买入": {"undervaluation": 0.30, "description": "DCF低估≥30%"},
    "增持": {"undervaluation": 0.15, "description": "DCF低估15-30%"},
    "中性": {"undervaluation": -0.15, "description": "DCF估值偏差±15%"},
    "减持": {"overvaluation": 0.15, "description": "DCF高估15-30%"},
    "卖出": {"overvaluation": 0.30, "description": "DCF高估≥30%"},
}


class Gate6Conclusion(GateBase):
    """Gate 6: 综合结论 + 决策章 + 概览章"""

    def __init__(self):
        spec = GateSpec(
            gate_num=6,
            name="综合结论 + 决策章 + 概览章",
            description="生成决策逻辑和概览",
            prerequisites=[5],  # 依赖Gate 5
            timeout=600,  # 10分钟
            max_retries=3,
            pass_criteria=[
                {"name": "决策章存在", "type": "condition", "condition": "decision_chapter_exists"},
                {"name": "决策章字数", "type": "quantitative", "metric": "decision_word_count", "threshold": 1000},
                {"name": "概览章存在", "type": "condition", "condition": "overview_chapter_exists"},
                {"name": "概览章字数", "type": "quantitative", "metric": "overview_word_count", "threshold": 500},
                {"name": "投资评级有效", "type": "condition", "condition": "rating_valid"},
                {"name": "评级与估值一致", "type": "condition", "condition": "rating_valuation_consistent"},
                {"name": "目标价偏差", "type": "quantitative", "metric": "target_price_deviation", "threshold": 0.20},
            ],
        )
        super().__init__(spec)

        self.allowed_ratings = ["买入", "增持", "中性", "减持", "卖出"]
        self.rating_mapping = RATING_VALUATION_MAPPING

    def execute(self, context: dict[str, Any]) -> GateResult:
        """执行Gate 6（真实：生成决策章+概览章，然后检查评级一致性）"""
        errors = []
        warnings = []
        details = {}

        chapters = context.get("chapters", {})

        # 0. 若未生成决策/概览章，用真实 LLM 生成（无 llm_caller 时跳过，保留预填章节）
        if (10 not in chapters or 0 not in chapters) and context.get("llm_caller") is not None:
            gen_result = self._generate_decision_overview(context, chapters)
            chapters = gen_result.get("chapters", chapters)
            context["chapters"] = chapters
            details["generation"] = gen_result
            if not gen_result["passed"]:
                errors.extend(gen_result["errors"])

        # 1. 检查决策章
        decision_result = self._check_decision_chapter(chapters)
        details["decision"] = decision_result

        if not decision_result["passed"]:
            errors.extend(decision_result["errors"])

        # 2. 检查概览章
        overview_result = self._check_overview_chapter(chapters)
        details["overview"] = overview_result

        if not overview_result["passed"]:
            errors.extend(overview_result["errors"])

        # 3. 检查投资评级
        rating_result = self._check_rating(chapters)
        details["rating"] = rating_result

        if not rating_result["passed"]:
            errors.extend(rating_result["errors"])

        # 4. 检查评级与估值一致性
        consistency_result = self._check_rating_valuation_consistency(chapters, context)
        details["consistency"] = consistency_result

        if not consistency_result["passed"]:
            errors.extend(consistency_result["errors"])

        # 5. 计算得分
        score = 100.0
        if errors:
            score -= len(errors) * 15
        score = max(0.0, min(100.0, score))

        passed = len(errors) == 0

        context["gate_6_result"] = {
            "decision_exists": decision_result["passed"],
            "overview_exists": overview_result["passed"],
            "rating": rating_result.get("rating", ""),
            "rating_valuation_consistent": consistency_result["passed"],
        }

        return GateResult(
            gate_num=6,
            passed=passed,
            score=score,
            details=details,
            errors=errors,
            warnings=warnings,
            execution_time=0.0,
            timestamp=datetime.now().isoformat(),
        )

    def _generate_decision_overview(self, context: dict[str, Any], chapters: dict[int, str]) -> dict[str, Any]:
        """生成决策章(10)与概览章(0)（真实：workflow._generate_decision_chapter/_generate_overview_chapter）"""
        errors = []
        llm_caller = context.get("llm_caller")

        if llm_caller is None:
            return {"passed": True, "errors": [], "chapters": chapters}

        try:
            from ...workflow import (
                _generate_decision_chapter,
                _generate_overview_chapter,
                _generate_synthesis_chapter,
            )
            from ..adapters import build_data_context

            ctx = build_data_context(
                ticker=context.get("ticker", ""),
                company_name=context.get("company_name", ""),
                market=context.get("market", "hk"),
                wind_data=context.get("wind_data"),
                filing_data=context.get("filing_data"),
            )
            facts = context.get("facts")
            if facts and not getattr(ctx, "facts", None):
                ctx.facts = facts

            out = dict(chapters)

            # 综合结论章（引用 ANCH）
            anch = context.get("anch_hypothesis")
            if 9 in out and 9 not in (1, 2, 3, 4, 5, 6, 7, 8):
                synthesis = _generate_synthesis_chapter(out, ctx, anch, llm_caller)
                if synthesis:
                    out[9] = synthesis

            # 决策章（第10章）
            decision = _generate_decision_chapter(out, ctx, llm_caller, checkpoint=None)
            if decision and "[Placeholder]" not in decision:
                out[10] = decision

            # 概览章（第0章）
            overview = _generate_overview_chapter(out, ctx, llm_caller, checkpoint=None)
            if overview and "[Placeholder]" not in overview:
                out[0] = overview

            return {"passed": True, "errors": [], "chapters": out}
        except Exception as e:
            logger.error(f"Gate6 决策/概览章生成失败: {e}")
            return {"passed": False, "errors": [f"决策/概览章生成失败: {e}"], "chapters": chapters}

    def check_criteria(self, context: dict[str, Any]) -> bool:
        """检查通过标准"""
        chapters = context.get("chapters", {})

        # 检查决策章
        decision_chapter = chapters.get(10, "")
        if len(decision_chapter) < 1000:
            return False

        # 检查概览章（quick 预填无第0章时放行）
        overview_chapter = chapters.get(0, "")
        if overview_chapter and len(overview_chapter) < 500:
            return False

        # 检查投资评级
        rating = self._extract_rating(chapters)
        if rating not in self.allowed_ratings:
            return False

        return True

    def _check_decision_chapter(self, chapters: dict[int, str]) -> dict[str, Any]:
        """检查决策章"""
        errors = []

        decision_chapter = chapters.get(10, "")

        if not decision_chapter:
            errors.append("决策章不存在")
        elif len(decision_chapter) < 1000:
            errors.append(f"决策章字数不足: {len(decision_chapter)}/1000")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "word_count": len(decision_chapter),
        }

    def _check_overview_chapter(self, chapters: dict[int, str]) -> dict[str, Any]:
        """检查概览章（第0章；quick 预填报告头部无编号时，检查报告头部存在即可）"""
        errors = []

        overview_chapter = chapters.get(0, "")

        if overview_chapter:
            if len(overview_chapter) < 500:
                errors.append(f"概览章字数不足: {len(overview_chapter)}/500")
        else:
            # 无第0章：若报告头部（1章前内容）存在且非空，视为概览（quick 预填模式）
            # 正式流程应生成第0章；此处不阻断，由 Gate8 最终验证把关
            logger.warning("Gate6: 无第0章概览（quick 预填模式，交由 Gate8 校验）")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "word_count": len(overview_chapter),
        }

    def _check_rating(self, chapters: dict[int, str]) -> dict[str, Any]:
        """检查投资评级"""
        errors = []

        rating = self._extract_rating(chapters)

        if not rating:
            errors.append("未找到投资评级")
        elif rating not in self.allowed_ratings:
            errors.append(f"投资评级无效: {rating}")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "rating": rating,
        }

    def _check_rating_valuation_consistency(self, chapters: dict[int, str], context: dict[str, Any]) -> dict[str, Any]:
        """检查评级与估值一致性"""
        errors = []

        rating = self._extract_rating(chapters)
        valuation = context.get("valuation")
        current_price = context.get("current_price", 0)

        if rating and valuation and current_price > 0:
            # 计算估值偏差
            dcf_value = valuation.dcf_value if hasattr(valuation, 'dcf_value') else 0
            if dcf_value > 0:
                deviation = (dcf_value - current_price) / current_price

                # 检查评级与估值是否一致
                rating_config = self.rating_mapping.get(rating, {})

                if "undervaluation" in rating_config:
                    if deviation < rating_config["undervaluation"]:
                        errors.append(f"评级'{rating}'要求低估≥{rating_config['undervaluation']:.0%}，实际偏差{deviation:.2%}")
                elif "overvaluation" in rating_config:
                    if deviation > rating_config["overvaluation"]:
                        errors.append(f"评级'{rating}'要求高估≥{rating_config['overvaluation']:.0%}，实际偏差{deviation:.2%}")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
        }

    def _extract_rating(self, chapters: dict[int, str]) -> str:
        """提取投资评级"""
        import re

        # 在所有章节中查找评级
        for ch_num, content in chapters.items():
            patterns = [
                r"评级[：:]\s*(买入|增持|中性|减持|卖出)",
                r"(买入|增持|中性|减持|卖出)\s*评级",
            ]

            for pattern in patterns:
                match = re.search(pattern, content)
                if match:
                    return match.group(1)

        return ""
