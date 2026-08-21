"""
Gate 4: 审计修复 + 深度审查（合并）
"""

import logging
from datetime import datetime
from typing import Any

# v3.1 P0-B-1：确定性/终止性异常显式 fail-closed（白名单，不被 except Exception 吞掉）
from ...llm_errors import (
    DeterministicLLMFailure,
    LLMCallBudgetExceeded,
    WallClockDeadlineExceeded,
)
from ..core.gate_engine import GateBase, GateResult, GateSpec

logger = logging.getLogger(__name__)


# 逻辑矛盾检测模式库
LOGIC_CONTRADICTION_PATTERNS = [
    {
        "id": "LC01",
        "name": "营收增长但利润下降无解释",
        "type": "deterministic",
        "severity": "warning",
    },
    {
        "id": "LC02",
        "name": "评级上调但目标价下调",
        "type": "deterministic",
        "severity": "critical",
    },
    {
        "id": "LC04",
        "name": "现金流为负但推荐买入",
        "type": "deterministic",
        "severity": "critical",
    },
    {
        "id": "LC09",
        "name": "现金流与净利润严重背离",
        "type": "deterministic",
        "severity": "critical",
    },
    {
        "id": "LC11",
        "name": "营收数据跨章节不一致",
        "type": "deterministic",
        "severity": "critical",
    },
]

# 风险提示检查清单
RISK_DISCLOSURE_CHECKLIST = [
    {"category": "市场风险", "min_length": 50},
    {"category": "经营风险", "min_length": 50},
    {"category": "财务风险", "min_length": 50},
    {"category": "行业风险", "min_length": 50},
    {"category": "估值风险", "min_length": 50},
    {"category": "数据风险", "min_length": 30},
    {"category": "流动性风险", "min_length": 30},
    {"category": "汇率风险", "min_length": 30},
]


class Gate4AuditRepair(GateBase):
    """Gate 4: 审计修复 + 深度审查"""

    def __init__(self):
        spec = GateSpec(
            gate_num=4,
            name="审计修复 + 深度审查",
            description="形式审查+实质审查+修复循环",
            prerequisites=[3],  # 依赖Gate 3
            timeout=1200,  # 20分钟
            max_retries=3,
            pass_criteria=[
                {"name": "格式错误数", "type": "quantitative", "metric": "format_errors", "threshold": 0},
                {"name": "数据引用来源", "type": "condition", "condition": "data_references_have_source"},
                {"name": "日期锚点一致", "type": "condition", "condition": "date_anchors_consistent"},
                {"name": "币种统一", "type": "condition", "condition": "currency_unified"},
                {"name": "估值参数一致", "type": "condition", "condition": "valuation_params_consistent"},
                {"name": "逻辑矛盾数", "type": "quantitative", "metric": "logic_contradictions", "threshold": 2},
                {"name": "风险提示覆盖", "type": "quantitative", "metric": "risk_categories_covered", "threshold": 8},
            ],
        )
        super().__init__(spec)

        self.contradiction_patterns = LOGIC_CONTRADICTION_PATTERNS
        self.risk_checklist = RISK_DISCLOSURE_CHECKLIST

    def execute(self, context: dict[str, Any]) -> GateResult:
        """执行Gate 4（真实：形式审查 + review_and_repair_loop 实质审查修复循环）"""
        errors = []
        warnings = []
        details = {}

        chapters = context.get("chapters", {})

        # 1. 形式审查（真实：占位符/币种/来源/模板指纹）
        #    形式问题记录并写入 context，交由 Gate8 最终 Critical 校验收口；
        #    Gate4 的硬阻断留给实质审查（审查修复循环）与逻辑矛盾
        formal_result = self._formal_review(chapters)
        details["formal_review"] = formal_result
        context["gate_4_formal_issues"] = formal_result["errors"] + formal_result.get("warnings", [])
        warnings.extend(formal_result["errors"])
        warnings.extend(formal_result.get("warnings", []))
        logger.warning(f"Gate4 形式审查发现{len(formal_result['errors']) + len(formal_result.get('warnings', []))}个问题（交由 Gate8 收口）")

        # 2. 实质审查（真实：review_and_repair_loop，含 deep + substantive + 修复）
        substantive_result = self._substantive_review(chapters, context)
        details["substantive_review"] = substantive_result

        if substantive_result.get("repaired_chapters"):
            context["chapters"] = substantive_result["repaired_chapters"]
            chapters = context["chapters"]

        if not substantive_result["passed"]:
            errors.extend(substantive_result["errors"])

        # 3. 逻辑矛盾检测（真实：quality.logic_consistency_check）
        #    C1-1：结果挂 context 供 check_criteria 复用（不再重复跑）
        contradiction_result = self._detect_contradictions(chapters)
        context["gate4_logic_result"] = contradiction_result
        details["contradictions"] = contradiction_result

        if not contradiction_result["passed"]:
            errors.extend(contradiction_result["errors"])

        # 4. 风险提示检查
        risk_result = self._check_risk_disclosure(chapters)
        details["risk_disclosure"] = risk_result

        if not risk_result["passed"]:
            errors.extend(risk_result["errors"])

        # 5. 计算得分
        score = 100.0
        if errors:
            score -= len(errors) * 15
        score = max(0.0, min(100.0, score))

        passed = len(errors) == 0

        context["gate_4_result"] = {
            "formal_passed": formal_result["passed"],
            "substantive_passed": substantive_result["passed"],
            "contradictions": contradiction_result.get("critical_count", 0),
            "risk_covered": risk_result.get("covered_count", 0),
        }

        return GateResult(
            gate_num=4,
            passed=passed,
            score=score,
            details=details,
            errors=errors,
            warnings=warnings,
            execution_time=0.0,
            timestamp=datetime.now().isoformat(),
        )

    def check_criteria(self, context: dict[str, Any]) -> bool:
        """检查通过标准（形式问题交 Gate8 收口；此处只查硬性：逻辑矛盾/风险覆盖）"""
        chapters = context.get("chapters", {})

        # 逻辑矛盾（硬性）—— C1-1：复用 execute 的结果（若已跑），避免重复计算
        contradiction_result = context.get("gate4_logic_result")
        if contradiction_result is None:
            contradiction_result = self._detect_contradictions(chapters)
            context["gate4_logic_result"] = contradiction_result
        contradiction_passed = contradiction_result["passed"]

        # 风险提示（硬性）
        risk_passed = self._check_risk_disclosure(chapters)["passed"]

        return contradiction_passed and risk_passed

    def _formal_review(self, chapters: dict[int, str]) -> dict[str, Any]:
        """形式审查（真实：占位符/币种混用/来源缺失/模板指纹）"""
        errors = []
        warnings = []
        format_errors = 0
        import re  # R7-②：'元/股' 专项检测需要 re（此方法后续来源检查也用到）

        # C5-2：占位符统一常量（L1/G3/G4a/G8 同源）
        from ...quality.placeholder_rules import PLACEHOLDER_PATTERNS
        placeholder_patterns = PLACEHOLDER_PATTERNS

        for ch_num, content in chapters.items():
            # 占位符
            for pattern in placeholder_patterns:
                if pattern in content:
                    format_errors += 1
                    errors.append(f"第{ch_num}章包含占位符: {pattern}")

            # 模板泄漏指纹（R5 ch8/ch9 实锤问题）
            template_markers = ["沪深300", "组合构建", "夏普比率", "原材料成本上行"]
            for marker in template_markers:
                if marker in content:
                    format_errors += 1
                    errors.append(f"第{ch_num}章疑似模板泄漏（含'{marker}'）")

            # '元/股' 专项（R7-②：豁免发行价/港元等港股真实表述）
            for mm in re.finditer(r"元/股", content):
                ctx_b = content[max(0, mm.start() - 40):mm.start()]
                if re.search(r"(发行价|上市价|招股价|港元|每股|现价|股价|价格)", ctx_b):
                    continue
                format_errors += 1
                errors.append(f"第{ch_num}章疑似模板泄漏（含'元/股'，上下文...{ctx_b[-15:]}）")

            # 币种混用（港股常态：股价港元+财务人民币，R7-④ 降为 warning 非 critical）
            if "港元" in content and "人民币" in content:
                warnings.append(f"第{ch_num}章币种混用（港元+人民币）——港股报告股价港元+财务人民币为常态，仅提示统一标注")

            # 数据引用无来源（质量警告：来源标注通常在句末括号"。（来源：…）"，句号在来源前，
            # 因此按句 split 会把来源切到下一句——合并"本句+下一句"再判断，且只记 warning）
            import re
            sentences = re.split(r"[。\n]", content)
            for idx, sent in enumerate(sentences):
                if not re.search(r"\d+\.?\d*\s*亿", sent):
                    continue
                window = sent + (sentences[idx + 1] if idx + 1 < len(sentences) else "")
                if not any(kw in window for kw in ("来源", "Wind", "年报", "报告", "公告", "测算", "估计", "数据")):
                    warnings.append(f"第{ch_num}章数据引用可能缺来源: '{sent[:40]}...'")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "format_errors": format_errors,
        }

    def _substantive_review(self, chapters: dict[int, str], context: dict[str, Any]) -> dict[str, Any]:
        """实质审查（真实：quality.review_and_repair_loop，含锚点注入）"""
        errors = []

        llm_caller = context.get("llm_caller")
        if llm_caller is None:
            # v3.1 P0-A-2：fail-closed（原为 passed=True 静默通过）
            return {"passed": False, "errors": ["无 LLM 调用器（fail-closed）"], "repaired_chapters": None}

        try:
            # 构造 DataContext（供 review_and_repair_loop 使用）
            from ..adapters import build_data_context, industry_for
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

            wind_data_for_check = {}
            if ctx.wind:
                wind_data_for_check = {
                    "income": ctx.wind.income if isinstance(ctx.wind.income, dict) else {},
                    "balance": ctx.wind.balance if isinstance(ctx.wind.balance, dict) else {},
                    "cashflow": ctx.wind.cashflow if isinstance(ctx.wind.cashflow, dict) else {},
                    # 必须带上 _year_labels：否则 DataAnchor 无财年锚点（FYNone），
                    # 多财年章节（如 ch6/ch7 引用 FY2024 历史值）会被误判为与最新锚点不符而回滚修复
                    "_year_labels": getattr(ctx.wind, "_year_labels", None) or {},
                }

            industry = industry_for(context.get("company_name", ""))

            from ...quality.review_repair_loop import review_and_repair_loop
            result = review_and_repair_loop(
                chapters=chapters,
                ctx=ctx,
                llm_caller=llm_caller,
                wind_data=wind_data_for_check,
                max_rounds=3,
                industry=industry,
                # v3.1 P0-B-10：shadow 模式只审不修（workflow 已按 qual_mode 注入）
                skip_repair=bool(context.get("shadow_skip_repair", False)),
                # v3.1 P0-B-8：全局墙钟/调用预算透传（与 workflow context 同源）
                # C4-1：审查子预算 ≤35 次（⊂ v3.1 总预算 200）——超预算 fail-closed（不静默放行）
                llm_call_budget=min(context.get("llm_call_budget", 200), 35),
                deadline=context.get("_wall_deadline"),
                # C1-3：Gate3 跨章结果首轮复用（避免重复静态检查）
                precomputed_cross_chapter=context.get("gate3_consistency_issues"),
                # P1：T2 低置信修复开关（ADVC 层1，默认关；弱签名+FY 唯一目标仍可替换）
                enable_t2=bool(context.get("advc_enable_t2", False)),
            )

            if not result.passed:
                for issue in (result.remaining_issues or [])[:5]:
                    errors.append(f"审查未修复: {issue}")

            return {
                "passed": result.passed,
                "errors": errors,
                "issues_found": getattr(result, "issues_found", 0),
                "issues_fixed": getattr(result, "issues_fixed", 0),
                "repaired_chapters": getattr(result, "chapters", None),
            }
        except (LLMCallBudgetExceeded, WallClockDeadlineExceeded) as e:
            # v3.1 P0-4：白名单前置——预算/墙钟子类必须先于父类 DeterministicLLMFailure
            logger.error(f"Gate4 实质审查终止性失败（预算/墙钟）: {e}")
            return {"passed": False, "errors": [f"实质审查终止性失败: {e}"], "repaired_chapters": None}
        except DeterministicLLMFailure as e:
            logger.error(f"Gate4 实质审查确定性失败: {e}")
            return {"passed": False, "errors": [f"实质审查确定性失败: {e}"], "repaired_chapters": None}
        except Exception as e:
            logger.error(f"Gate4 实质审查失败: {e}")
            # v3.1 P0-A-2：fail-closed（原为 passed=True 静默通过）
            return {"passed": False, "errors": [f"实质审查异常（fail-closed）: {e}"], "repaired_chapters": None}

    def _detect_contradictions(self, chapters: dict[int, str]) -> dict[str, Any]:
        """检测逻辑矛盾（真实：quality.logic_consistency_check）"""
        errors = []
        contradictions = []
        critical_count = 0

        try:
            from ...quality.logic_consistency_check import check_logic_consistency
            result = check_logic_consistency(chapters)
            if not result.passed:
                for issue in result.issues:
                    contradictions.append({
                        "id": getattr(issue, "issue_id", ""),
                        "description": getattr(issue, "description", str(issue)),
                        "severity": getattr(issue, "severity", "warning"),
                    })
                    if getattr(issue, "severity", "") == "critical":
                        critical_count += 1
        except Exception as e:
            logger.warning(f"Gate4 逻辑矛盾检测失败（非阻断）: {e}")

        if critical_count > 0:
            errors.append(f"发现{critical_count}个致命逻辑矛盾")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "contradictions": contradictions,
            "critical_count": critical_count,
        }

    def _check_risk_disclosure(self, chapters: dict[int, str]) -> dict[str, Any]:
        """检查风险提示（真实：关键词覆盖）"""
        errors = []
        covered_categories = []

        full_text = "\n".join(str(v) for v in chapters.values())

        risk_keywords = {
            "市场风险": ["市场竞争", "竞争加剧", "市场份额"],
            "经营风险": ["经营", "业务", "运营"],
            "财务风险": ["财务", "杠杆", "负债", "现金流"],
            "行业风险": ["行业", "监管", "政策"],
            "估值风险": ["估值", "PE", "PB", "折价"],
            "数据风险": ["数据", "信息"],
            "流动性风险": ["流动性", "偿债"],
            "汇率风险": ["汇率", "港元", "人民币"],
        }

        for category, keywords in risk_keywords.items():
            if any(kw in full_text for kw in keywords):
                covered_categories.append(category)

        required_count = len(self.risk_checklist)
        covered_count = len(covered_categories)

        if covered_count < required_count:
            errors.append(f"风险提示覆盖不足: {covered_count}/{required_count}")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "covered_categories": covered_categories,
            "covered_count": covered_count,
        }
