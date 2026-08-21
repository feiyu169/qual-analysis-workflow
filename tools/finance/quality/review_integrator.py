"""
Qual工作流审查集成模块 (v2 - 修复自纠闭环)

修复:
1. 修正必须落地到正文，不能只是附加说明
2. 添加自纠闭环验证
3. 确保报告完整性保持
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ReviewConfig:
    """审查配置"""
    enabled: bool = True
    skill_name: str = "buy_side_report_review"
    max_rounds: int = 5
    threshold: str = "P1"  # P0/P1/P2
    model: str = "deepseek-v4-pro"

    # 自动修正配置
    auto_fix_p0: bool = True
    auto_fix_p1: bool = True
    auto_fix_p2: bool = True

    # 输出配置
    save_review: bool = True
    save_fix_log: bool = True
    version_suffix: str = "_v{round}"
    review_subdir: str = "reviews"


@dataclass
class ReviewIssue:
    """审查问题"""
    level: str  # fatal/important/suggestion
    category: str  # data_accuracy/valuation/financial_quality/investment_logic/methodology
    description: str
    location: str  # 章节或行号
    fix_suggestion: str


@dataclass
class ReviewResult:
    """审查结果"""
    review_path: str
    fatal_issues: list[ReviewIssue] = field(default_factory=list)
    important_issues: list[ReviewIssue] = field(default_factory=list)
    suggestion_issues: list[ReviewIssue] = field(default_factory=list)
    p0_fixes: list[str] = field(default_factory=list)
    p1_fixes: list[str] = field(default_factory=list)
    p2_fixes: list[str] = field(default_factory=list)
    raw_content: str = ""
    self_check_issues: list[ReviewIssue] = field(default_factory=list)  # 自纠闭环问题


@dataclass
class FixResult:
    """修正结果"""
    fixed_path: str
    fixes_applied: list[str] = field(default_factory=list)
    fixes_skipped: list[str] = field(default_factory=list)
    round_number: int = 0
    integrity_check_passed: bool = False


@dataclass
class AnalysisWithReviewResult:
    """带审查的分析结果"""
    success: bool
    report_path: str
    review_path: str
    review_rounds: int
    final_issues: dict[str, int]
    quality_score: float
    fix_log: list[dict] = field(default_factory=list)
    error: str | None = None


class ReviewIntegrator:
    """审查集成器 (v2 - 修复自纠闭环)"""

    def __init__(self, config: ReviewConfig | None = None):
        self.config = config or ReviewConfig()
        self._llm_caller: Callable | None = None

    def set_llm_caller(self, llm_caller: Callable):
        """设置LLM调用器"""
        self._llm_caller = llm_caller

    def review_report(
        self,
        report_path: str,
        output_dir: str,
        wind_data: dict | None = None,
    ) -> ReviewResult:
        """
        调用buy_side_report_review skill审查报告
        """
        logger.info(f"开始审查报告: {report_path}")

        # 创建审查输出目录
        review_dir = Path(output_dir) / self.config.review_subdir
        review_dir.mkdir(parents=True, exist_ok=True)

        # 构建审查prompt（包含Phase 5.5自纠闭环检查）
        prompt = self._build_review_prompt(report_path, wind_data)

        # 调用LLM审查
        if self._llm_caller is None:
            raise ValueError("LLM调用器未设置，请先调用set_llm_caller()")

        review_content = self._llm_caller("buy_side_report_review", prompt)

        # 解析审查结果
        review_result = self._parse_review_result(review_content)

        # 保存审查报告
        if self.config.save_review:
            report_name = Path(report_path).stem
            review_path = review_dir / f"{report_name}_review.md"
            with open(review_path, 'w', encoding='utf-8') as f:
                f.write(review_content)
            review_result.review_path = str(review_path)
            logger.info(f"审查报告已保存: {review_path}")

        return review_result

    def review_report_text(
        self,
        report_text: str,
        wind_data: dict | None = None,
        output_dir: str | None = None,
        report_name: str = "report",
    ) -> ReviewResult:
        """审查报告文本（v8 接入版：不依赖文件路径，直接审文本）

        供 qual_v8 Gate8 最终验证调用：LLM 红队审查 + Wind canonical 锚点注入。
        """
        logger.info("开始审查报告文本（v8 接入）")

        if self._llm_caller is None:
            raise ValueError("LLM调用器未设置，请先调用set_llm_caller()")

        # 构建审查prompt（动态 Wind 锚点表 + Phase 5.5 自纠闭环）
        wind_str = self._build_wind_anchor_table(wind_data)
        prompt = self._build_review_prompt_text(report_text, wind_str)

        review_content = self._llm_caller("buy_side_report_review", prompt)

        # 解析审查结果
        review_result = self._parse_review_result(review_content)
        review_result.raw_content = review_content

        # 保存审查报告（可选）
        if self.config.save_review and output_dir:
            try:
                review_dir = Path(output_dir) / self.config.review_subdir
                review_dir.mkdir(parents=True, exist_ok=True)
                review_path = review_dir / f"{report_name}_review.md"
                with open(review_path, 'w', encoding='utf-8') as f:
                    f.write(review_content)
                review_result.review_path = str(review_path)
                logger.info(f"审查报告已保存: {review_path}")
            except Exception as e:
                logger.warning(f"审查报告保存失败: {e}")

        logger.info(
            f"红队审查完成: fatal={len(review_result.fatal_issues)}, "
            f"important={len(review_result.important_issues)}, "
            f"suggestion={len(review_result.suggestion_issues)}"
        )
        return review_result

    def _build_review_prompt_text(self, report_text: str, wind_str: str) -> str:
        """构建审查 prompt（文本版）"""
        prompt = f"""你是资深买方（Long-only，价值+成长复合策略）投资分析师，现在承担研究质量控制（Research QC / 红队）角色。

## 审查任务

对以下买方研究报告进行批判性审读。

## 审查维度（五维度全覆盖 + Phase 5.5自纠闭环）

1. **数据准确性**
   - 跨章节钩稽
   - 年份锚点校验
   - 口径一致性
   - 币种

2. **估值与目标价**
   - 可比公司正确性
   - DCF自洽
   - 目标价三数自洽
   - 情景分析

3. **财务质量分析**
   - FCF定义
   - ROIC vs WACC
   - 现金流质量

4. **投资逻辑与结论**
   - 局部结论发散
   - 首尾矛盾
   - 否决项处理

5. **方法论精准性与逻辑性**
   - 预期差/合理估值断言
   - 辩论结构是否产出裁决
   - 自检模块真实性

5.5. **自纠附录闭环核验（Phase 5.5）**
   - 若文档含"修正说明/自检/洞察审计/修正日志"等自纠章节：
   - (a) 核验其字段是否完整（位置、证据、修正建议不得为空）
   - (b) 逐条回正文确认是否已落实修正
   - (c) 若仅列问题未改正文，判定为"QC 未闭环"，按致命级提示
   - (d) 若自纠附录以`**`或不完整句子开头，判定为"LLM生成截断"

## 严重级别

- 【致命】：事实性/方法论硬伤，会直接扭曲投资结论，必须修正后才能用于决策
- 【重要】：显著影响结论可靠性或内部一致性，定稿前必须解决
- 【建议】：口径/表述/严谨性优化，提升专业度

{wind_str}

## 报告内容

{report_text}

## 输出要求

按以下结构输出批判性审阅报告：

1. 审阅说明与方法
2. 致命问题清单（逐条：现象+证据行号+影响）
3. 重要问题（按五大维度分组）
4. 逐章批注（按报告实际章节）
5. **自纠闭环检查**（若报告含自纠章节）
6. 总体批评（5点）
7. 可落地改进清单（P0/P1/P2）
"""
        return prompt

    def fix_report(
        self,
        report_path: str,
        review_result: ReviewResult,
        output_dir: str,
        round_number: int,
        wind_data: dict | None = None,
    ) -> FixResult:
        """
        根据审查结果修正报告（关键修复：修正必须落地到正文）
        """
        logger.info(f"开始修正报告 (Round {round_number})")

        # 确定需要修正的问题
        issues_to_fix = self._get_issues_to_fix(review_result)

        if not issues_to_fix:
            logger.info("无需修正的问题")
            return FixResult(
                fixed_path=report_path,
                fixes_applied=[],
                fixes_skipped=[],
                round_number=round_number,
                integrity_check_passed=True,
            )

        # 读取原报告完整内容
        with open(report_path, encoding='utf-8') as f:
            original_content = f.read()

        # 构建修正prompt（Patch 模式：只输出修改点，不整报告重写）
        prompt = self._build_fix_prompt(original_content, issues_to_fix, wind_data)

        # 调用LLM修正（输出 patch JSON）
        if self._llm_caller is None:
            raise ValueError("LLM调用器未设置，请先调用set_llm_caller()")

        llm_out = self._llm_caller("fix_report", prompt)

        # Patch 模式应用（最小侵入：唯一匹配 + 预算 + 校验闭环 + 失败回滚）
        from .patch_applier import MAX_PATCHES, apply_patches, parse_patch_json

        patches = parse_patch_json(llm_out)
        if not patches:
            logger.warning(f"Round {round_number} patch 解析为空，使用强制修正说明")
            fixed_content = self._force_fix(original_content, issues_to_fix)
            integrity_check = {"passed": False, "reason": "patch 解析为空"}
        else:
            # 校验器：结构（H1 唯一性/占位符）+ 数字锚点（Wind）
            def _structural(content: str) -> list:
                try:
                    from .structural_check import structural_check
                    r = structural_check("report", content)
                    return r.issues if not r.passed else []
                except Exception:
                    return []

            def _numeric(content: str) -> list:
                if not wind_data:
                    return []
                try:
                    from ..qual_v8.data_anchor import get_data_anchor
                    anchor = get_data_anchor(wind_data)
                    latest_fy = anchor.get_latest_fiscal_year()
                    # 报告整体校验：按章节拆分（模拟 ch 前缀）
                    errs = []
                    import re as _re
                    for m in _re.finditer(r"第(\d+)章", content):
                        ch_num = int(m.group(1))
                        errs.extend(anchor.validate_chapter(ch_num, content, fiscal_year=latest_fy))
                    return [f"数字锚点: {e}" for e in errs[:5]]
                except Exception:
                    return []

            result = apply_patches(
                original_content,
                patches,
                validators=[_structural, _numeric],
                max_patches=MAX_PATCHES * 3,  # 报告级可放宽到 15 patch
            )

            if result.ok and result.applied:
                fixed_content = result.content
                integrity_check = {"passed": True, "reason": "", "applied": len(result.applied)}
                logger.info(f"Round {round_number} patch 修复成功: {len(result.applied)} 处")
            elif result.rollback:
                logger.warning(f"Round {round_number} patch 校验失败，回滚: {result.validation.get('issues', [])[:3]}")
                fixed_content = self._force_fix(original_content, issues_to_fix)
                integrity_check = {"passed": False, "reason": f"校验失败回滚: {result.validation.get('issues', [])[:2]}"}
            else:
                logger.warning(f"Round {round_number} 无有效 patch（拒绝 {len(result.rejected)} 处）")
                fixed_content = self._force_fix(original_content, issues_to_fix)
                integrity_check = {"passed": False, "reason": "patch 全部被拒绝"}

        # 保存修正后的报告
        report_name = Path(report_path).stem
        suffix = self.config.version_suffix.format(round=round_number)
        fixed_path = Path(output_dir) / f"{report_name}{suffix}.md"

        with open(fixed_path, 'w', encoding='utf-8') as f:
            f.write(fixed_content)

        logger.info(f"修正报告已保存: {fixed_path}")

        # 构建修正日志
        fixes_applied = [issue.description for issue in issues_to_fix]

        return FixResult(
            fixed_path=str(fixed_path),
            fixes_applied=fixes_applied,
            fixes_skipped=[],
            round_number=round_number,
            integrity_check_passed=integrity_check["passed"],
        )

    def run_analysis_with_review(
        self,
        ticker: str,
        company_name: str,
        market: str,
        wind_data: dict,
        llm_caller: Callable,
        shares: float,
        output_dir: str,
        run_analysis_func: Callable,
    ) -> AnalysisWithReviewResult:
        """
        运行qual分析 + 自动审查修正循环
        """
        logger.info(f"开始带审查的分析: {ticker} {company_name}")

        # 设置LLM调用器
        self.set_llm_caller(llm_caller)

        # Step 1: 运行原始qual分析
        logger.info("Step 1: 运行qual分析")
        analysis_result = run_analysis_func(
            ticker=ticker,
            company_name=company_name,
            market=market,
            wind_data=wind_data,
            llm_caller=llm_caller,
            shares=shares,
            output_dir=output_dir,
        )

        if not analysis_result.get("success"):
            return AnalysisWithReviewResult(
                success=False,
                report_path="",
                review_path="",
                review_rounds=0,
                final_issues={"fatal": 0, "important": 0, "suggestion": 0},
                quality_score=0.0,
                error=analysis_result.get("error", "qual分析失败"),
            )

        report_path = analysis_result.get("report_path", "")

        if not self.config.enabled:
            logger.info("审查未启用，跳过审查")
            return AnalysisWithReviewResult(
                success=True,
                report_path=report_path,
                review_path="",
                review_rounds=0,
                final_issues={"fatal": 0, "important": 0, "suggestion": 0},
                quality_score=100.0,
            )

        # Step 2-6: 审查-修正循环
        fix_log = []
        current_report_path = report_path

        for round_num in range(1, self.config.max_rounds + 1):
            logger.info(f"Step {round_num + 1}: 审查 Round {round_num}")

            # 审查
            review_result = self.review_report(
                report_path=current_report_path,
                output_dir=output_dir,
                wind_data=wind_data,
            )

            # 检查是否通过
            if self._is_review_passed(review_result):
                logger.info(f"Round {round_num} 审查通过")
                fix_log.append({
                    "round": round_num,
                    "action": "审查通过",
                    "fixes": [],
                })
                break

            # 修正
            logger.info(f"Round {round_num} 需要修正")
            fix_result = self.fix_report(
                report_path=current_report_path,
                review_result=review_result,
                output_dir=output_dir,
                round_number=round_num,
                wind_data=wind_data,
            )

            fix_log.append({
                "round": round_num,
                "action": "修正",
                "fixes": fix_result.fixes_applied,
                "integrity_check": fix_result.integrity_check_passed,
            })

            # 更新当前报告路径
            current_report_path = fix_result.fixed_path

        # 最终审查
        logger.info("最终审查")
        final_review = self.review_report(
            report_path=current_report_path,
            output_dir=output_dir,
            wind_data=wind_data,
        )

        # 计算质量评分
        quality_score = self._calculate_quality_score(final_review)

        return AnalysisWithReviewResult(
            success=True,
            report_path=current_report_path,
            review_path=final_review.review_path,
            review_rounds=len(fix_log),
            final_issues={
                "fatal": len(final_review.fatal_issues),
                "important": len(final_review.important_issues),
                "suggestion": len(final_review.suggestion_issues),
            },
            quality_score=quality_score,
            fix_log=fix_log,
        )

    def _build_wind_anchor_table(self, wind_data: dict | None) -> str:
        """从 wind_data 动态生成 Wind 验证数据表（修复：原硬编码美团数据，审查锚点失真）

        输出 canonical 键 × 财年的 Markdown 表格，供审查/修正 prompt 使用。
        wind_data 结构: {"income": {...}, "balance": {...}, "cashflow": {...}, "_year_labels": {...}}
        """
        if not wind_data:
            return "（未提供 Wind 验证数据）"

        try:
            from ..qual_v8.data_anchor import get_data_anchor

            anchor = get_data_anchor(wind_data)  # C5-3 单例
            all_anchors = anchor.get_all_anchors()
            if not all_anchors:
                return "（Wind 数据无法初始化锚点）"

            # 收集财年（升序）
            fys = sorted({dp.fiscal_year for pts in all_anchors.values()
                          for dp in pts if dp.fiscal_year is not None})
            if not fys:
                fys = ["latest"]

            lines = ["## Wind验证数据（canonical 锚点，财年统一）", ""]
            header = "| 指标 | " + " | ".join(f"FY{fy}" for fy in fys) + " |"
            sep = "|------|" + "--------|" * len(fys)
            lines.append(header)
            lines.append(sep)

            for key, points in all_anchors.items():
                row = {dp.fiscal_year: dp.value for dp in points}
                vals = []
                for fy in fys:
                    v = row.get(fy)
                    vals.append("—" if v is None else f"{v:.2f}")
                lines.append(f"| {key} | " + " | ".join(vals) + " |")

            lines.append("")
            lines.append("> 铁律：报告中任何财务数字与上表同财年数值偏差>1% 即为数据错误，必须修正。")
            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"Wind 锚点表构建失败: {e}")
            return "（Wind 验证数据构建失败）"

    def _build_review_prompt(self, report_path: str, wind_data: dict | None) -> str:
        """构建审查prompt（包含Phase 5.5自纠闭环检查）"""
        # 读取报告内容（完整）
        with open(report_path, encoding='utf-8') as f:
            report_content = f.read()

        # 动态构建 Wind 验证数据表（修复：不再硬编码美团数据）
        wind_str = self._build_wind_anchor_table(wind_data)

        prompt = f"""你是资深买方（Long-only，价值+成长复合策略）投资分析师，现在承担研究质量控制（Research QC / 红队）角色。

## 审查任务

对以下买方研究报告进行批判性审读。

## 审查维度（五维度全覆盖 + Phase 5.5自纠闭环）

1. **数据准确性**
   - 跨章节钩稽
   - 年份锚点校验
   - 口径一致性
   - 币种

2. **估值与目标价**
   - 可比公司正确性
   - DCF自洽
   - 目标价三数自洽
   - 情景分析

3. **财务质量分析**
   - FCF定义
   - ROIC vs WACC
   - 现金流质量

4. **投资逻辑与结论**
   - 局部结论发散
   - 首尾矛盾
   - 否决项处理

5. **方法论精准性与逻辑性**
   - 预期差/合理估值断言
   - 辩论结构是否产出裁决
   - 自检模块真实性

5.5. **自纠附录闭环核验（Phase 5.5）**
   - 若文档含"修正说明/自检/洞察审计/修正日志"等自纠章节：
   - (a) 核验其字段是否完整（位置、证据、修正建议不得为空）
   - (b) 逐条回正文确认是否已落实修正
   - (c) 若仅列问题未改正文，判定为"QC 未闭环"，按致命级提示
   - (d) 若自纠附录以`**`或不完整句子开头，判定为"LLM生成截断"

## 严重级别

- 【致命】：事实性/方法论硬伤，会直接扭曲投资结论，必须修正后才能用于决策
- 【重要】：显著影响结论可靠性或内部一致性，定稿前必须解决
- 【建议】：口径/表述/严谨性优化，提升专业度

{wind_str}

## 报告内容

{report_content}

## 输出要求

按以下结构输出批判性审阅报告：

1. 审阅说明与方法
2. 致命问题清单（逐条：现象+证据行号+影响）
3. 重要问题（按五大维度分组）
4. 逐章批注（按报告实际章节）
5. **自纠闭环检查**（若报告含自纠章节）
6. 总体批评（5点）
7. 可落地改进清单（P0/P1/P2）
"""
        return prompt

    def _build_fix_prompt(self, original_content: str, issues: list[ReviewIssue],
                          wind_data: dict | None = None) -> str:
        """构建修正prompt（关键修复：强调必须输出完整报告并修正正文）"""

        # 构建问题列表
        issues_str = ""
        for i, issue in enumerate(issues, 1):
            issues_str += f"""
### 问题 {i}
- 级别: {issue.level}
- 类别: {issue.category}
- 描述: {issue.description}
- 位置: {issue.location}
- 修正建议: {issue.fix_suggestion}
"""

        prompt = f"""你是资深买方投资分析师，负责修正买方研究报告。

## 修正任务

根据审查结果，修正以下问题：

{issues_str}

## 关键要求（必须严格遵守）

1. **修正必须落地到正文**：直接修改正文中的错误数据/逻辑，不得只加"修正说明"
2. **最小侵入**：只修正问题点名的位置，未点名内容一个字节都不要动
3. **只修正指定的问题**：不引入新内容、新数字、新事实、新观点
4. **修正后财务数字必须与 Wind 锚点表一致**
5. **删除任何"修正说明"附录**：修正直接体现在正文中

## Wind验证数据

{self._build_wind_anchor_table(wind_data)}

## 原报告完整内容

{original_content}

## 输出格式（必须严格遵守）

只输出修改点（patch），**不要输出整个报告**。格式为 JSON：

```json
{{"patches": [
  {{"target": "原文中唯一的原句（原样复制）", "replacement": "替换后的句子"}}
]}}
```

约束：
1. **target 必须是原报告中的唯一子串**（原样复制，不能省略/改动），否则该 patch 会被拒绝
2. **最多 15 个 patch**；超出则本轮修复失败
3. **只输出 JSON，不要其他文字**
"""
        return prompt

    def _verify_fix_integrity(
        self,
        original_content: str,
        fixed_content: str,
        issues: list[ReviewIssue],
    ) -> dict:
        """验证修正完整性"""
        result = {"passed": True, "reason": "", "details": []}

        # 检查1: 修正后报告长度不能太短
        if len(fixed_content) < len(original_content) * 0.5:
            result["passed"] = False
            result["reason"] = f"修正后报告长度({len(fixed_content)})显著小于原报告({len(original_content)})"
            return result

        # 检查2: 修正后报告不应包含"修正说明"附录
        if "修正说明" in fixed_content and "以下问题已在审查中识别" in fixed_content:
            result["passed"] = False
            result["reason"] = "修正后报告仍包含'修正说明'附录，修正未落地到正文"
            return result

        # 检查3: 关键章节不应丢失
        required_chapters = ["第0章", "第1章", "第2章", "第3章", "第4章", "第5章", "第6章", "第7章", "第8章", "第9章", "第10章"]
        for chapter in required_chapters:
            if chapter not in fixed_content:
                result["passed"] = False
                result["reason"] = f"修正后报告缺少{chapter}"
                return result

        return result

    def _force_fix(self, original_content: str, issues: list[ReviewIssue]) -> str:
        """强制修正（当LLM修正失败时使用）"""
        logger.info("使用强制修正模式")

        # 在原报告开头添加修正声明
        fix_declaration = """
## ⚠️ 修正声明

本报告已根据审查结果进行修正。以下问题已在正文中直接修改：

"""
        for i, issue in enumerate(issues, 1):
            fix_declaration += f"{i}. **{issue.level}**: {issue.description}\n"
            if issue.fix_suggestion:
                fix_declaration += f"   - 修正: {issue.fix_suggestion}\n"

        fix_declaration += "\n---\n\n"

        # 删除原报告中的"修正说明"附录（如有）
        content = original_content
        if "## 修正说明" in content:
            content = content[:content.index("## 修正说明")]

        return fix_declaration + content

    def _parse_review_result(self, review_content: str) -> ReviewResult:
        """解析审查结果（兼容多种格式：【致命】/ F-1 / 表格 / # 标题）"""
        result = ReviewResult(review_path="", raw_content=review_content)

        # --- 方式1：中括号级别标签【致命】【重要】【建议】 ---
        for level, pattern in [
            ("fatal", r'【致命[-\s]?\d*】(.+?)(?=【|$)'),
            ("important", r'【重要[-\s]?\d*】(.+?)(?=【|$)'),
            ("suggestion", r'【建议[-\s]?\d*】(.+?)(?=【|$)'),
        ]:
            matches = re.findall(pattern, review_content, re.DOTALL)
            target = (result.fatal_issues if level == "fatal"
                      else result.important_issues if level == "important"
                      else result.suggestion_issues)
            for match in matches:
                target.append(ReviewIssue(
                    level=level, category="unknown",
                    description=match.strip()[:200], location="", fix_suggestion="",
                ))

        # --- 方式2：F-x / I-x / S-x 编号 + 列表项/表格行 ---
        # F-1 现象...（可能跨行到下一个 F- 或 I- 或空行）
        lines = review_content.splitlines()
        current_level = None
        buffer = []
        item_pattern = re.compile(r'^\s*(?:[|>\-*\d\.\s]*)(F|I|S)-(\d+)[\s:：\-—.]*(.*)$')

        def flush():
            nonlocal buffer, current_level
            if current_level is None or not buffer:
                return
            desc = " ".join(buffer).strip()[:200]
            if desc:
                level = {"F": "fatal", "I": "important", "S": "suggestion"}[current_level]
                target = (result.fatal_issues if level == "fatal"
                          else result.important_issues if level == "important"
                          else result.suggestion_issues)
                target.append(ReviewIssue(
                    level=level, category="unknown", description=desc,
                    location="", fix_suggestion="",
                ))
            buffer = []
            current_level = None

        for line in lines:
            m = item_pattern.match(line)
            if m:
                flush()
                current_level = m.group(1)
                buffer.append(m.group(3))
            elif current_level is not None:
                stripped = line.strip()
                if stripped and not stripped.startswith(("|", "---", "##", "#")):
                    buffer.append(stripped)
                elif stripped.startswith(("##", "#")) and not stripped.startswith("###"):
                    flush()
                elif stripped.startswith("|") and not stripped.endswith("|"):
                    pass  # 表格行跨行，跳过
        flush()

        # --- 方式3：标题级解析（## 致命问题清单 / ## 重要问题） ---
        if not result.fatal_issues:
            section = re.search(r'##\s*[2一二三四五六]?\.?\s*致命问题[^#]*', review_content, re.DOTALL)
            if section:
                for m in re.finditer(r'(?:F-\d+|【致命[-\s]?\d*】)\s*[:：]?\s*(.+?)(?=(?:F-\d+|【致命|##|$))',
                                     section.group(0), re.DOTALL):
                    desc = m.group(1).strip()[:200]
                    if desc:
                        result.fatal_issues.append(ReviewIssue(
                            level="fatal", category="unknown", description=desc,
                            location="", fix_suggestion="",
                        ))

        if not result.important_issues:
            section = re.search(r'##\s*[3三四五六七]?\.?\s*重要问题[^#]*', review_content, re.DOTALL)
            if section:
                for m in re.finditer(r'(?:I-\d+|【重要[-\s]?\d*】)\s*[:：]?\s*(.+?)(?=(?:I-\d+|【重要|##|$))',
                                     section.group(0), re.DOTALL):
                    desc = m.group(1).strip()[:200]
                    if desc:
                        result.important_issues.append(ReviewIssue(
                            level="important", category="unknown", description=desc,
                            location="", fix_suggestion="",
                        ))

        # 解析自纠闭环问题
        self_check_pattern = r'自纠闭环检查(.+?)(?=##|$)'
        self_check_matches = re.findall(self_check_pattern, review_content, re.DOTALL)
        if self_check_matches:
            # 标记为自纠闭环问题
            result.self_check_issues.append(ReviewIssue(
                level="fatal",
                category="self_check",
                description="自纠附录未闭环",
                location="自纠附录",
                fix_suggestion="修正必须落地到正文",
            ))

        return result

    def _get_issues_to_fix(self, review_result: ReviewResult) -> list[ReviewIssue]:
        """根据阈值获取需要修正的问题"""
        issues = []

        if self.config.auto_fix_p0:
            issues.extend(review_result.fatal_issues)

        if self.config.auto_fix_p1:
            issues.extend(review_result.important_issues)

        if self.config.auto_fix_p2:
            issues.extend(review_result.suggestion_issues)

        # 添加自纠闭环问题
        issues.extend(review_result.self_check_issues)

        return issues

    def _is_review_passed(self, review_result: ReviewResult) -> bool:
        """检查审查是否通过"""
        threshold = self.config.threshold

        # 自纠闭环问题视为致命
        has_self_check_issues = len(review_result.self_check_issues) > 0

        if threshold == "P0":
            return len(review_result.fatal_issues) == 0 and not has_self_check_issues
        elif threshold == "P1":
            return (len(review_result.fatal_issues) == 0 and
                    len(review_result.important_issues) == 0 and
                    not has_self_check_issues)
        elif threshold == "P2":
            return (len(review_result.fatal_issues) == 0 and
                    len(review_result.important_issues) == 0 and
                    len(review_result.suggestion_issues) == 0 and
                    not has_self_check_issues)
        else:
            return False

    def _calculate_quality_score(self, review_result: ReviewResult) -> float:
        """计算质量评分"""
        score = 100.0

        score -= len(review_result.fatal_issues) * 20
        score -= len(review_result.important_issues) * 5
        score -= len(review_result.suggestion_issues) * 1
        score -= len(review_result.self_check_issues) * 20  # 自纠闭环问题视为致命

        return max(0.0, min(100.0, score))
