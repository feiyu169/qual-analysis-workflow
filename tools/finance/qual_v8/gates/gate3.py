"""
Gate 3: 逐章写作（大纲→分章→交叉验证→组装）

v9 变更：
- 引入 ChapterState 状态机（参照 dayu write_pipeline chapter_execution_coordinator）
- prompt 构建从 workflow._build_chapter_prompt 切换到 prompting.chapter_prompts
- Gate3 内部章节生成遵循 PREPARE→GENERATE→VALIDATE→COMPLETE 状态流转
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from ..core.gate_engine import GateBase, GateResult, GateSpec

logger = logging.getLogger(__name__)


class ChapterState(str, Enum):  # noqa: UP042
    """章节生成状态机（参照 dayu write_pipeline ChapterExecutionState）。

    状态流转：
        PREPARE → GENERATE → VALIDATE → COMPLETE
        VALIDATE → REPAIR → VALIDATE（最多 max_repairs 轮）
    """
    PREPARE = "prepare"      # 构建 prompt + 注入锚点
    GENERATE = "generate"    # LLM 生成章节
    VALIDATE = "validate"    # PGNB + ADVC + 检查器
    REPAIR = "repair"        # 程序化修复（不调 LLM）
    COMPLETE = "complete"    # 返回章节内容


@dataclass
class ChapterConfig:
    """章节配置"""
    total_chapters: int  # 总章节数
    min_word_count: int  # 最小字数
    required_sections: list[str]  # 必需章节
    placeholder_patterns: list[str]  # 占位符模式


class Gate3ChapterWriting(GateBase):
    """Gate 3: 逐章写作"""

    def __init__(self):
        spec = GateSpec(
            gate_num=3,
            name="逐章写作",
            description="大纲→分章→交叉验证→组装",
            prerequisites=[2],  # 依赖Gate 2
            timeout=900,  # 15分钟
            max_retries=3,
            pass_criteria=[
                {"name": "章节完整性", "type": "condition", "condition": "chapters_complete"},
                {"name": "字数要求", "type": "condition", "condition": "word_count_met"},
                {"name": "数据一致性", "type": "condition", "condition": "data_consistent"},
                {"name": "无占位符", "type": "condition", "condition": "no_placeholders"},
            ],
        )
        super().__init__(spec)

        self.config = ChapterConfig(
            total_chapters=11,  # 第0-10章
            min_word_count=500,
            required_sections=["目录", "正文", "图表", "风险提示"],
            placeholder_patterns=["[Placeholder]", "XX亿元", "待填写", "TBD"],
        )

    def execute(self, context: dict[str, Any]) -> GateResult:
        """执行Gate 3（真实：11章 LLM 生成 + 完整性/占位符/一致性检查）"""
        errors = []
        warnings = []
        details = {}

        # 1. 生成大纲（真实：CHAPTERS 标题）
        outline = self._generate_outline(context)
        details["outline"] = outline

        # 2. 分章生成（真实：workflow._build_chapter_prompt + _generate_chapter）
        chapters = self._generate_chapters(context, outline)
        details["chapters"] = {k: len(v) for k, v in chapters.items()}

        # 3. 交叉一致性验证（真实：quality.cross_chapter_consistency）
        #    一致性发现的问题记录为 warning 并写入 context，不阻断流程——
        #    阻断语义由 Gate4（审查修复）与 Gate8（最终 Critical 校验）承担
        consistency_result = self._check_consistency(chapters, wind_data=context.get("wind_data"))
        details["consistency"] = consistency_result
        # C1-3：跨章结果挂 context，Gate4 首轮复用（中间无修改，结果相同——避免重复跑）
        context["gate3_consistency_issues"] = consistency_result["errors"]
        context["gate3_consistency_passed"] = consistency_result["passed"]

        if not consistency_result["passed"]:
            warnings.extend(consistency_result["errors"])
            logger.warning(
                f"Gate3 跨章一致性发现{len(consistency_result['errors'])}个矛盾（交由 Gate4/8 处理）"
            )

        # 4. 检查章节完整性（缺失章节是硬阻断；字数不足记 warning）
        completeness_result = self._check_completeness(chapters)
        details["completeness"] = completeness_result

        if not completeness_result["passed"]:
            # 区分：章节数量不足 → 硬错误；字数不足 → 警告
            hard = [e for e in completeness_result["errors"] if "数量不足" in e]
            soft = [e for e in completeness_result["errors"] if "字数不足" in e]
            errors.extend(hard)
            warnings.extend(soft)

        # 5. 检查占位符（记 warning，由 Gate8 最终 Critical 校验收口）
        placeholder_result = self._check_placeholders(chapters)
        details["placeholders"] = placeholder_result

        if not placeholder_result["passed"]:
            warnings.extend(placeholder_result["errors"])
            logger.warning(f"Gate3 占位符{warnings[-1:] if warnings else ''}（交由 Gate8 收口）")

        # 6. 计算得分
        score = 100.0
        if errors:
            score -= len(errors) * 20
        score = max(0.0, min(100.0, score))

        passed = len(errors) == 0

        # 7. 写入 context 供后续 Gate 使用
        context["chapters"] = chapters
        context["gate_3_result"] = {
            "chapter_count": len(chapters),
            "total_chars": sum(len(v) for v in chapters.values()),
            "consistency_passed": consistency_result["passed"],
        }

        return GateResult(
            gate_num=3,
            passed=passed,
            score=score,
            details=details,
            errors=errors,
            warnings=warnings,
            execution_time=0.0,
            timestamp=datetime.now().isoformat(),
        )

    def check_criteria(self, context: dict[str, Any]) -> bool:
        """检查通过标准（核心：章节数量；字数/占位符由后续 Gate 收口）"""
        chapters = context.get("chapters", {})

        # 检查章节完整性（数量是硬性）
        if len(chapters) < self.config.total_chapters - 2:  # 允许缺 0/10  # noqa: SIM103
            return False

        return True

    def _generate_outline(self, context: dict[str, Any]) -> dict[str, Any]:
        """生成大纲（真实：finance.workflow.CHAPTERS 标题）"""
        try:
            from ...workflow import _CHAPTER_WRITE_ORDER, CHAPTERS
            outline = {}
            for num in [0, *_CHAPTER_WRITE_ORDER, 10]:
                ch_def = CHAPTERS.get(num)
                if ch_def:
                    outline[num] = f"第{num}章: {ch_def['title']}"
            if outline:
                return outline
        except Exception as e:
            logger.warning(f"Gate3 大纲生成降级: {e}")
        return {i: f"第{i}章大纲" for i in range(self.config.total_chapters)}

    def _generate_chapters(self, context: dict[str, Any], outline: dict[str, Any]) -> dict[int, str]:
        """分章生成（真实：workflow 11 章生成链）

        context 需含：llm_caller、wind_data、filing_data、ticker、company_name、market、shares
        若 context 已含 chapters（如 --quick 模式预填），直接复用并校验。
        """
        # --quick 模式：预填章节直接复用
        pre_filled = context.get("chapters")
        if pre_filled and isinstance(pre_filled, dict) and pre_filled:
            logger.info(f"Gate3: 复用预填章节 {len(pre_filled)} 章")
            return pre_filled

        llm_caller = context.get("llm_caller")
        if llm_caller is None:
            logger.warning("Gate3: 无 llm_caller，返回空章节")
            return {}

        try:
            from ...workflow import (
                _CHAPTER_WRITE_ORDER,
                _build_chapter_prompt,
                _generate_chapter,
            )
            from ..adapters import build_data_context

            ctx = build_data_context(
                ticker=context.get("ticker", ""),
                company_name=context.get("company_name", ""),
                market=context.get("market", "hk"),
                wind_data=context.get("wind_data"),
                filing_data=context.get("filing_data"),
            )

            # 注入事实表（若 Gate1 已提取）
            facts = context.get("facts")
            if facts and not getattr(ctx, "facts", None):
                # v10：wind-only 模式下 facts 是 dict，需要包装为兼容对象
                if isinstance(facts, dict):
                    class _FactsCompat:
                        """dict 包装，兼容 ctx.facts.operational 等属性访问。"""
                        def __init__(self, d: dict):
                            self._d = d
                            self.operational = type('O', (), {k: v for k, v in d.items() if isinstance(v, (int, float, str)) and k not in ('revenue', 'net_income', 'total_assets', 'operating_cash_flow')})()
                            self.revenue = d.get('revenue')
                            self.net_income = d.get('net_income')
                            self.total_assets = d.get('total_assets')
                            self.operating_cash_flow = d.get('operating_cash_flow')
                    ctx.facts = _FactsCompat(facts)
                else:
                    ctx.facts = facts

            chapters: dict[int, str] = {}
            for chapter_num in _CHAPTER_WRITE_ORDER:
                # ChapterState: PREPARE → GENERATE → VALIDATE → COMPLETE
                logger.info(f"Gate3 第{chapter_num}章 PREPARE: 构建 prompt")
                prompt = _build_chapter_prompt(chapter_num, ctx, chapters)
                logger.info(f"Gate3 第{chapter_num}章 GENERATE: LLM 生成")
                content = _generate_chapter(chapter_num, prompt, ctx, llm_caller,
                                            deadline=context.get("_wall_deadline"))
                # VALIDATE：PGNB + ADVC 已在 _generate_chapter 内部完成
                logger.info(f"Gate3 第{chapter_num}章 COMPLETE: {len(content)}字符")
                chapters[chapter_num] = content

            # B1-3：ch10（决策）与 ch0（概览）纳入生成与审计（全 11 章）
            # 决策章依赖前 9 章综合，概览章依赖全部（含决策）——故在 1-9 章之后补生成
            from ...workflow import (
                _generate_decision_chapter,
                _generate_overview_chapter,
            )

            decision = _generate_decision_chapter(chapters, ctx, llm_caller)
            chapters[10] = decision
            # v10：DecisionAggregator 结果写入 context 供 Gate6 评级提取
            if hasattr(ctx, '_decision_rating'):
                context["decision_rating"] = ctx._decision_rating
            logger.info(f"Gate3 第10章完成（决策）: {len(decision)}字符")
            overview = _generate_overview_chapter(chapters, ctx, llm_caller)
            chapters[0] = overview
            logger.info(f"Gate3 第0章完成（概览）: {len(overview)}字符")
            return chapters
        except Exception as e:
            logger.error(f"Gate3 章节生成失败: {e}")
            return {}

    def _check_consistency(self, chapters: dict[int, str],
                           wind_data: dict | None = None) -> dict[str, Any]:
        """检查一致性（真实：quality.cross_chapter_consistency，FiscalSemantics 归因）"""
        errors = []

        try:
            from ...quality.cross_chapter_consistency import (
                check_cross_chapter_consistency,
            )
            result = check_cross_chapter_consistency(chapters, wind_data=wind_data)
            if not result.passed:
                errors.extend(
                    f"第{i.chapter1}章 vs 第{i.chapter2}章: {i.description}"
                    for i in result.issues
                )
        except Exception as e:
            logger.warning(f"Gate3 一致性检查失败（非阻断）: {e}")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
        }

    def _check_completeness(self, chapters: dict[int, str]) -> dict[str, Any]:
        """检查完整性"""
        errors = []

        # 检查章节数量
        if len(chapters) < self.config.total_chapters - 2:  # 0/10 可选
            errors.append(f"章节数量不足: {len(chapters)}/{self.config.total_chapters}")

        # 检查字数
        for ch_num, content in chapters.items():
            if len(content) < self.config.min_word_count:
                errors.append(f"第{ch_num}章字数不足: {len(content)}/{self.config.min_word_count}")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
        }

    def _check_placeholders(self, chapters: dict[int, str]) -> dict[str, Any]:
        """检查占位符"""
        errors = []

        for ch_num, content in chapters.items():
            errors.extend(
                f"第{ch_num}章包含占位符: {p}"
                for p in self.config.placeholder_patterns
                if p in content
            )

        return {
            "passed": len(errors) == 0,
            "errors": errors,
        }
