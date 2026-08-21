"""
Gate 3: 逐章写作（大纲→分章→交叉验证→组装）
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..core.gate_engine import GateBase, GateResult, GateSpec

logger = logging.getLogger(__name__)


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
        consistency_result = self._check_consistency(chapters)
        details["consistency"] = consistency_result

        if not consistency_result["passed"]:
            warnings.extend(consistency_result["errors"])
            logger.warning(f"Gate3 跨章一致性发现{len(consistency_result['errors'])}个矛盾（交由 Gate4/8 处理）")

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
            timestamp=datetime.now().isoformat(),  # noqa: DTZ005
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
            for num in [0] + _CHAPTER_WRITE_ORDER + [10]:
                ch_def = CHAPTERS.get(num)
                if ch_def:
                    outline[num] = f"第{num}章: {ch_def['title']}"
            if outline:
                return outline
        except Exception as e:  # noqa: BLE001
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
                ctx.facts = facts

            chapters: dict[int, str] = {}
            for chapter_num in _CHAPTER_WRITE_ORDER:
                prompt = _build_chapter_prompt(chapter_num, ctx, chapters)
                content = _generate_chapter(chapter_num, prompt, ctx, llm_caller,
                                            deadline=context.get("_wall_deadline"))  # v3.1 P0-B-1
                chapters[chapter_num] = content
                logger.info(f"Gate3 第{chapter_num}章完成: {len(content)}字符")

            # B1-3：ch10（决策）与 ch0（概览）纳入生成与审计（全 11 章）
            # 决策章依赖前 9 章综合，概览章依赖全部（含决策）——故在 1-9 章之后补生成
            from ...workflow import (
                _generate_decision_chapter,
                _generate_overview_chapter,
            )

            decision = _generate_decision_chapter(chapters, ctx, llm_caller)
            chapters[10] = decision
            logger.info(f"Gate3 第10章完成（决策）: {len(decision)}字符")
            overview = _generate_overview_chapter(chapters, ctx, llm_caller)
            chapters[0] = overview
            logger.info(f"Gate3 第0章完成（概览）: {len(overview)}字符")
            return chapters
        except Exception as e:  # noqa: BLE001
            logger.error(f"Gate3 章节生成失败: {e}")
            return {}

    def _check_consistency(self, chapters: dict[int, str]) -> dict[str, Any]:
        """检查一致性（真实：quality.cross_chapter_consistency）"""
        errors = []

        try:
            from ...quality.cross_chapter_consistency import (
                check_cross_chapter_consistency,
            )
            result = check_cross_chapter_consistency(chapters)
            if not result.passed:
                for issue in result.issues:
                    errors.append(f"第{issue.chapter1}章 vs 第{issue.chapter2}章: {issue.description}")
        except Exception as e:  # noqa: BLE001
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
            for pattern in self.config.placeholder_patterns:
                if pattern in content:
                    errors.append(f"第{ch_num}章包含占位符: {pattern}")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
        }
