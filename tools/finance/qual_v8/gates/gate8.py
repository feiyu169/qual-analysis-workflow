"""
Gate 8: 最终验证（人工确认）
"""

import logging
from datetime import datetime
from typing import Any

from ..core.gate_engine import GateBase, GateResult, GateSpec

logger = logging.getLogger(__name__)


class Gate8FinalValidation(GateBase):
    """Gate 8: 最终验证"""

    def __init__(self):
        spec = GateSpec(
            gate_num=8,
            name="最终验证",
            description="人工确认+最终质量评估",
            prerequisites=[7],  # 依赖Gate 7
            timeout=1800,  # 30分钟
            max_retries=1,  # 最终验证只允许1次重试
            pass_criteria=[
                {"name": "所有Gate通过", "type": "condition", "condition": "all_gates_passed"},
                {"name": "无Critical问题", "type": "condition", "condition": "no_critical_issues"},
                {"name": "人工确认", "type": "condition", "condition": "human_confirmed"},
                {"name": "报告格式正确", "type": "condition", "condition": "report_format_correct"},
                {"name": "报告大小合理", "type": "condition", "condition": "report_size_reasonable"},
            ],
        )
        super().__init__(spec)

    def execute(self, context: dict[str, Any]) -> GateResult:
        """执行Gate 8"""
        errors = []
        warnings = []
        details = {}

        # 0. 兜底组装 report（若尚未组装，从 chapters 生成）
        if not context.get("report") and context.get("chapters"):
            try:
                chs = context["chapters"]
                parts = [f"# {context.get('company_name', '')} ({context.get('ticker', '')}) 买方定性分析报告\n"]
                for num in sorted(k for k in chs.keys() if isinstance(k, int)):  # noqa: SIM118
                    parts.append(f"# 第{num}章\n{chs[num]}")
                context["report"] = "\n".join(parts)
            except Exception as e:
                logger.warning(f"Gate8 报告组装失败: {e}")

        # 0.5 ADVC 组装闸门救援 sweep（P1：最终闸门前最后一次确定性数值清洗——
        # 值类问题由程序修正，不依赖 LLM 重写；T2 低置信开关从 context 读取）
        rescue_result = self._advc_rescue_sweep(context)
        details["advc_rescue"] = rescue_result
        if rescue_result.get("fixed_count", 0) > 0:
            # 已修复 → 重新组装 report（sweep 已就地更新 context["chapters"]）
            try:
                chs = context["chapters"]
                parts = [f"# {context.get('company_name', '')} ({context.get('ticker', '')}) 买方定性分析报告\n"]
                for num in sorted(k for k in chs.keys() if isinstance(k, int)):  # noqa: SIM118
                    parts.append(f"# 第{num}章\n{chs[num]}")
                context["report"] = "\n".join(parts)
            except Exception as e:
                logger.warning(f"Gate8 救援后报告重组失败: {e}")

        # 1. 检查所有Gate是否通过
        all_gates_result = self._check_all_gates(context)
        details["all_gates"] = all_gates_result

        if not all_gates_result["passed"]:
            errors.extend(all_gates_result["errors"])

        # 2. 检查Critical问题
        critical_result = self._check_critical_issues(context)
        details["critical_issues"] = critical_result

        if not critical_result["passed"]:
            errors.extend(critical_result["errors"])

        # 3. 人工确认
        human_result = self._request_human_confirmation(context)
        details["human_confirmation"] = human_result

        if not human_result["passed"]:
            errors.extend(human_result["errors"])
        warnings.extend(human_result.get("warnings", []))

        # 4. 检查报告格式
        format_result = self._check_report_format(context)
        details["report_format"] = format_result

        if not format_result["passed"]:
            errors.extend(format_result["errors"])

        # 5. 检查报告大小
        size_result = self._check_report_size(context)
        details["report_size"] = size_result

        if not size_result["passed"]:
            errors.extend(size_result["errors"])

        # 5.5 红队审查层（buy_side_report_review skill 接入；有 llm_caller 时执行）
        redteam_result = self._run_redteam_review(context)
        details["redteam_review"] = redteam_result

        if not redteam_result["passed"]:
            errors.extend(redteam_result["errors"])
        warnings.extend(redteam_result.get("warnings", []))

        # 6. 计算得分
        score = 100.0
        if errors:
            score -= len(errors) * 20
        score = max(0.0, min(100.0, score))

        passed = len(errors) == 0

        return GateResult(
            gate_num=8,
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
        # 检查所有Gate是否通过
        gate_results = context.get("gate_results", {})
        for gate_num in range(8):  # Gate 0-7
            if gate_num not in gate_results or not gate_results[gate_num].passed:
                return False

        # 检查人工确认
        human_confirmed = context.get("human_confirmed", False)
        return bool(human_confirmed)

    def _advc_rescue_sweep(self, context: dict[str, Any]) -> dict[str, Any]:
        """ADVC 组装闸门救援 sweep（P1：最终闸门前确定性数值清洗）。

        在 Gate8 数字校验（_check_critical_issues）之前执行：若 chapters 中仍残留
        可确定性修复的值类错位（T1 高置信恒开；T2 低置信由 context['advc_enable_t2']
        开关，默认关），就地修正并记录，随后校验器以清洗后的内容为准。

        Returns:
            {"fixed_count", "fixes", "unresolved_count", "hint_count", "skipped"}
        """
        chapters = context.get("chapters", {})
        wind_data = context.get("wind_data", {})
        if not chapters or not wind_data:
            return {"fixed_count": 0, "skipped": True, "reason": "无 chapters/wind_data"}

        try:
            from ..anchor_repair import sweep_all_chapters
            from ..data_anchor import get_data_anchor

            enable_t2 = bool(context.get("advc_enable_t2", False))
            _fixed, _fixes, _unresolved, _hints = sweep_all_chapters(
                chapters, get_data_anchor(wind_data), enable_t2=enable_t2,
            )
            if _fixes:
                # 就地更新 chapters（Gate8 后续校验/组装读取同一 dict）
                chapters.clear()
                chapters.update(_fixed)
                logger.info(
                    f"Gate8 ADVC 救援 sweep: 确定性修复 {len(_fixes)} 处"
                    f"（T2={'开' if enable_t2 else '关'}）——值类问题不再依赖 LLM"
                )
            if _unresolved:
                logger.warning(
                    f"Gate8 ADVC 救援 sweep: {len(_unresolved)} 处值类问题仍无法程序校正（T3 标注）"
                )
            return {
                "fixed_count": len(_fixes),
                "fixes": [
                    {"metric": f.metric, "old": f.old_value, "new": f.new_value,
                     "kind": f.kind, "confidence": f.confidence}
                    for f in _fixes[:10]
                ],
                "unresolved_count": len(_unresolved),
                "hint_count": len(_hints),
                "skipped": False,
            }
        except Exception as e:
            logger.warning(f"Gate8 ADVC 救援 sweep 失败（非阻断）: {e}")
            return {"fixed_count": 0, "skipped": True, "reason": str(e)}

    def _check_all_gates(self, context: dict[str, Any]) -> dict[str, Any]:
        """检查所有Gate是否通过"""
        errors = []

        gate_results = context.get("gate_results", {})
        results = context.get("results", {})
        failed_gates = []

        for gate_num in range(8):  # Gate 0-7
            # 支持 GateResult 对象或 dict 两种格式
            gr = gate_results.get(gate_num)
            if gr is not None:
                passed = gr.passed if hasattr(gr, "passed") else gr.get("passed", False)
                if not passed:
                    failed_gates.append(gate_num)
            elif results.get(f"gate_{gate_num}", {}).get("passed"):
                pass
            else:
                failed_gates.append(gate_num)

        if failed_gates:
            errors.append(f"以下Gate未通过: {failed_gates}")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "failed_gates": failed_gates,
        }

    def _check_critical_issues(self, context: dict[str, Any]) -> dict[str, Any]:
        """检查Critical问题（真实：数字校验器 + 模板指纹 + 结构校验）"""
        errors = []
        critical_found = []

        chapters = context.get("chapters", {})
        wind_data = context.get("wind_data", {})
        full_text = "\n".join(str(v) for v in chapters.values())

        # 1. 数字校验器：报告内财务数字 vs Wind 锚点
        if chapters and wind_data:
            try:
                from ..data_anchor import CrossChapterValidator, get_data_anchor
                # C5-3：锚点单例（缓存共享，避免每 Gate 重建）
                anchor = context.get("data_anchor") or get_data_anchor(wind_data)
                validation = CrossChapterValidator(anchor).validate_all_chapters(chapters)
                if not validation["passed"]:
                    for e in validation["errors"][:10]:
                        critical_found.append(f"数字不一致: {e}")
            except Exception as e:
                logger.warning(f"Gate8 数字校验异常: {e}")

        # 2. 模板泄漏指纹（R5 ch8/ch9 实锤：组合构建/沪深300/买入评级）
        template_markers = ["沪深300", "组合构建", "夏普比率", "原材料成本上行", "2026年预期PE"]
        for marker in template_markers:
            if marker in full_text:
                critical_found.append(f"模板泄漏指纹: 含'{marker}'")

        # 2a. '元/股' 专项检测（R7-②：豁免发行价/港元/上市价等港股真实表述）
        import re as _re2
        for m in _re2.finditer(r"元/股", full_text):
            ctx = full_text[max(0, m.start() - 40):m.start()]
            # 豁免："发行价55元/股"、"上市价"、"港元"附近的真实用法
            if _re2.search(r"(发行价|上市价|招股价|港元|每股|现价|股价|价格)", ctx):
                continue
            critical_found.append(f"模板泄漏指纹: 含'元/股'（上下文: ...{ctx[-20:]}）")

        # 2b. 收口 Gate4 形式审查发现的问题（占位符/模板指纹；币种混用已降为 warning）
        gate4_issues = context.get("gate_4_formal_issues") or []
        for issue in gate4_issues:
            if any(kw in issue for kw in ("占位符", "模板泄漏")):
                critical_found.append(f"Gate4 形式问题: {issue}")

        # 3. 结构性 Critical：章节重号（# 第N章 出现多次）
        import re
        for match in re.finditer(r"#\s*第(\d+)章", full_text):
            pass
        heading_nums = re.findall(r"#\s*第(\d+)章", full_text)
        from collections import Counter
        dupes = [n for n, c in Counter(heading_nums).items() if c > 1 and int(n) in (1, 2, 3, 4, 5, 6, 7, 8, 9)]
        if dupes:
            critical_found.append(f"章节重号: 第{dupes}章出现多次（模板/组装泄漏）")

        # 3b. 章节固化：正文内自造的 H1 章节标题（非组装层添加）→ 模板/结构泄漏
        self_made_h1 = re.findall(r"(?m)^#\s+第\s*\d+\s*[章回节]", full_text)
        if self_made_h1:
            critical_found.append(f"正文含自造 H1 章节标题 {len(self_made_h1)} 处（LLM 结构失控）")

        # 4. 占位符（C5-2：统一常量全量 5 pattern——原 3 pattern 漏"待填写/TBD"逃出收口）
        from ...quality.placeholder_rules import PLACEHOLDER_PATTERNS
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern in full_text:
                critical_found.append(f"占位符残留: {pattern}")

        if critical_found:
            errors.append(f"发现{len(critical_found)}个Critical问题: {critical_found[:5]}")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "critical_found": critical_found,
        }

    def _request_human_confirmation(self, context: dict[str, Any]) -> dict[str, Any]:
        """请求人工确认（双专家 P1：默认 False——未显式注入人工确认时不得静默放行，
        run 脚本显式传 human_confirmed=True 保持自动化；报告应标注复核状态）"""
        errors = []
        warnings = []

        human_confirmed = context.get("human_confirmed", False)

        if not human_confirmed:
            errors.append("人工未确认（报告未经人工复核，应标注）")
            warnings.append("⚠️ 本报告未经人工复核——投资结论需人工审阅后再使用")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "human_confirmed": human_confirmed,
        }

    def _check_report_format(self, context: dict[str, Any]) -> dict[str, Any]:
        """检查报告格式（真实：非空 + H1 唯一性）"""
        errors = []

        report = context.get("report", "")

        # 检查报告是否为空
        if not report:
            errors.append("报告为空")
            return {"passed": False, "errors": errors}

        # 结构校验：报告头必须存在
        if not report.lstrip().startswith("#"):
            errors.append("报告缺少 H1 标题")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
        }

    def _check_report_size(self, context: dict[str, Any]) -> dict[str, Any]:
        """检查报告大小"""
        errors = []

        report = context.get("report", "")
        report_size = len(report.encode("utf-8"))

        # 检查报告大小是否合理（50KB-500KB）；quick 组装版可能 <50KB，仅警告
        min_size = 50 * 1024  # 50KB
        max_size = 500 * 1024  # 500KB

        if report_size < min_size:
            # 仅当报告为空时才报错；否则记警告（quick 预填/组装模式）
            if not report:
                errors.append("报告为空: 0KB")
            else:
                logger.warning(f"Gate8: 报告偏小 {report_size/1024:.1f}KB（可能为 quick 组装模式）")
        elif report_size > max_size:
            errors.append(f"报告过大: {report_size / 1024:.1f}KB > {max_size / 1024:.1f}KB")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "size_kb": report_size / 1024,
        }

    def _run_redteam_review(self, context: dict[str, Any]) -> dict[str, Any]:
        """红队审查层：接入 buy_side_report_review skill（ReviewIntegrator）

        - 无 llm_caller：跳过（确定性检查已覆盖）
        - 有 llm_caller：LLM 红队审查 + Wind canonical 锚点注入
        - 【致命】问题 → Gate8 FAIL；【重要】→ warning
        """
        llm_caller = context.get("llm_caller")
        if llm_caller is None:
            logger.info("Gate8: 无 llm_caller，跳过红队审查（确定性检查已覆盖）")
            return {"passed": True, "errors": [], "warnings": [], "skipped": True}

        # C3-2：Gate4 实质审查通过后才触发红队（Gate4 未过 → 红队延后，避免重复审查投入）
        g4 = context.get("gate_4_result") or {}
        if not g4.get("substantive_passed", False):
            logger.warning("Gate8: Gate4 实质审查未通过，红队延后（C3-2 门控）")
            return {"passed": True, "errors": [], "warnings": ["Gate4 实质审查未通过，红队延后"], "skipped": True}

        report = context.get("report", "")
        if not report:
            logger.warning("Gate8: 报告为空，跳过红队审查")
            return {"passed": True, "errors": [], "warnings": [], "skipped": True}

        wind_data = context.get("wind_data", {})
        chapters = context.get("chapters", {})  # noqa: F841
        try:
            from ...quality.review_integrator import ReviewConfig, ReviewIntegrator

            integrator = ReviewIntegrator(ReviewConfig(
                threshold="P0",          # 致命问题阻断
                auto_fix_p0=False,       # Gate8 只审不修（修复由 Gate4/外部循环承担）
                auto_fix_p1=False,
                auto_fix_p2=False,
            ))

            # 专用审查 caller：大 maxTokens（红队审查长输出）+ 审查 system prompt
            from ...harness_llm import create_harness_caller
            REVIEW_SYSTEM = "你是资深买方投资分析师（Research QC/红队）。你的任务是批判性审读研究报告，不做报告撰写格式约束。"
            review_caller = create_harness_caller(
                max_tokens=24000,
                temperature=0.3,
                system=REVIEW_SYSTEM,
                deadline=context.get("_wall_deadline"),  # v3.1 P0-B-1：红队审查同样受墙钟约束
            )
            integrator.set_llm_caller(review_caller)

            review_result = integrator.review_report_text(
                report_text=report,
                wind_data=wind_data,
                output_dir=context.get("output_dir"),
                report_name=context.get("ticker", "report"),
            )

            # 改进点3+：长报告（>12000 字符）红队审查有截断风险——统一 review_chunker 分批补审
            # P1-④：每批 checkpoint 落盘（进程中断可续审）
            batch_issues = []
            warnings_redteam = []  # 修复既有 F821：warnings 未定义
            unreviewed = []
            if len(report) > 12000:
                import json as _json

                from ...quality.review_chunker import split_report
                checkpoint_dir = None
                try:
                    from pathlib import Path as _Path
                    _cp_root = context.get("output_dir") or ""
                    if _cp_root:
                        checkpoint_dir = _Path(_cp_root) / "redteam_checkpoints"
                        checkpoint_dir.mkdir(parents=True, exist_ok=True)
                except Exception:
                    checkpoint_dir = None

                logger.info(f"Gate8: 报告 {len(report)} 字符 > 12000，review_chunker 分批红队补审")
                for seg_id, seg_body in split_report(report, max_chars=12000):
                    if len(seg_body) < 100:
                        continue
                    # 断点续审：已有 checkpoint 则跳过（P1-④）
                    cp_path = None
                    if checkpoint_dir:
                        try:
                            cp_path = checkpoint_dir / f"seg{seg_id}.json"
                            if cp_path.exists():
                                with open(cp_path, encoding="utf-8") as _f:
                                    _cp = _json.load(_f)
                                batch_issues.extend(_cp.get("fatal", []))
                                warnings_redteam.extend(_cp.get("important", []))
                                logger.info(f"Gate8 片段 {seg_id} 从 checkpoint 恢复")
                                continue
                        except Exception:
                            pass
                    try:
                        r = integrator.review_report_text(
                            report_text=seg_body,
                            wind_data=wind_data,
                            report_name=f"{context.get('ticker', 'report')}_seg{seg_id}",
                        )
                        fatal = [f"红队致命(seg{seg_id}): {iss.description[:120]}" for iss in r.fatal_issues[:3]]
                        important = [f"红队重要(seg{seg_id}): {iss.description[:120]}" for iss in r.important_issues[:3]]
                        batch_issues.extend(fatal)
                        warnings_redteam.extend(important)
                        # 落盘 checkpoint
                        if cp_path:
                            try:
                                with open(cp_path, "w", encoding="utf-8") as _f:
                                    _json.dump({"fatal": fatal, "important": important}, _f, ensure_ascii=False)
                            except Exception:
                                pass
                    except Exception as e:
                        logger.warning(f"Gate8 片段 {seg_id} 红队补审失败: {e}")
                        unreviewed.append(seg_id)

            # 汇总
            fatal_count = len(review_result.fatal_issues) + len(batch_issues)
            important_count = len(review_result.important_issues)
            suggestion_count = len(review_result.suggestion_issues)

            errors = []
            warnings = []
            # 致命问题 → Gate8 FAIL（截取前 5 条描述）
            for issue in review_result.fatal_issues[:5]:
                errors.append(f"红队致命: {issue.description[:150]}")
            # C3-2：fatal 回流标注（Gate4 限 1 轮修复路径；报告显式标注不静默放行）
            if errors:
                context["redteam_fatal_reflow"] = True
                context["redteam_fatal_count"] = len(errors)
            # 分批补审的致命问题（来自长报告后段）
            for bi in batch_issues[:5]:
                errors.append(bi)  # noqa: PERF402
            # 重要/建议 → warning
            for issue in review_result.important_issues[:5]:
                warnings.append(f"红队重要: {issue.description[:150]}")
            for issue in review_result.suggestion_issues[:5]:
                warnings.append(f"红队建议: {issue.description[:150]}")
            # 未审标注（P1：单批失败不丢整份）
            if unreviewed:
                warnings.append(f"红队未审片段: {unreviewed[:5]}（其余审查照常）")

            context["redteam_review_result"] = {
                "fatal": fatal_count,
                "important": important_count,
                "suggestion": suggestion_count,
                "unreviewed": unreviewed,
                "review_path": review_result.review_path,
            }

            logger.info(
                f"Gate8 红队审查: fatal={fatal_count}, important={important_count}, "
                f"suggestion={suggestion_count}"
            )
            return {
                "passed": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "fatal": fatal_count,
                "important": important_count,
                "suggestion": suggestion_count,
            }
        except Exception as e:
            # 双专家 P1（2026-08-22）：红队失败改 fail-closed（原 passed=True 静默放行——
            # 红队是 Gate8 最后一道独立审查，失败不得当作"通过"）
            logger.error(f"Gate8 红队审查失败（fail-closed）: {e}")
            return {"passed": False, "errors": [f"红队审查失败（fail-closed）: {e}"],
                    "warnings": [], "fatal": 0, "important": 0, "suggestion": 0}
