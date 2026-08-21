"""
分析深度审查模块

功能：
1. 使用LLM检查分析是否深入
2. 检查是否有定量分析（不仅仅是定性描述）
3. 检查是否有敏感性分析
4. 检查是否有行业对比

审查原则：不降低买方报告分析的专业性和质量
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

# v3.1 P0-A-3：确定性/终止性异常白名单（不降级，fail-closed 上抛）
from ..llm_errors import (
    DeterministicLLMFailure,
    LLMCallBudgetExceeded,
    WallClockDeadlineExceeded,
)

logger = logging.getLogger(__name__)


@dataclass
class DepthIssue:
    """分析深度问题"""
    issue_type: str  # "shallow_analysis", "missing_quantitative", "missing_sensitivity", "missing_comparison"
    severity: str  # "fatal", "important", "suggestion"
    description: str
    chapter: int
    score: int  # 0-100


@dataclass
class DepthReviewResult:
    """分析深度审查结果"""
    passed: bool
    issues: list[DepthIssue] = field(default_factory=list)
    score: float = 100.0
    chapter_scores: dict[int, int] = field(default_factory=dict)


class DepthReviewer:
    """分析深度审查器"""

    def __init__(self):
        # 分析深度评估维度
        self.depth_dimensions = {
            "定量分析": {
                "keywords": ["数据", "比例", "百分比", "增长率", "金额", "数量"],
                "weight": 0.3,
            },
            "数据支撑": {
                "keywords": ["来源", "引用", "根据", "数据显示", "Wind", "年报"],
                "weight": 0.25,
            },
            "敏感性分析": {
                "keywords": ["情景", "假设", "敏感性", "乐观", "悲观", "基准"],
                "weight": 0.2,
            },
            "行业对比": {
                "keywords": ["行业", "可比", "同行", "对比", "竞争"],
                "weight": 0.15,
            },
            "历史趋势": {
                "keywords": ["趋势", "历史", "变化", "演变", "发展"],
                "weight": 0.1,
            },
        }

        # LLM审查prompt模板
        self.review_prompt_template = """
请评估以下章节的分析深度：

{content}
{wind_anchor}

评估维度：
1. 定量分析：是否有具体数据支撑（而不仅仅是定性描述）？数据是否与 Wind 锚点一致？
2. 数据支撑：是否引用了可靠的数据来源（如Wind、年报）？
3. 敏感性分析：是否考虑了不同情景（乐观/悲观/基准）？
4. 行业对比：是否与可比公司或行业平均水平进行了对比？
5. 历史趋势：是否分析了历史变化趋势？

请对每个维度给出评分（0-100），并指出具体问题。

输出格式：
定量分析: [分数]
数据支撑: [分数]
敏感性分析: [分数]
行业对比: [分数]
历史趋势: [分数]
总分: [分数]
问题: [具体问题描述]
"""

    def check(
        self,
        chapters: dict[int, str],
        llm_caller: Callable[[str, str], str] | None = None,
        wind_data: dict | None = None,
    ) -> DepthReviewResult:
        """
        执行分析深度审查

        Args:
            chapters: 各章节内容 {chapter_num: content}
            llm_caller: LLM调用函数（可选）
            wind_data: Wind 数据（用于构建锚点表，注入 prompt 供 LLM 对照）

        Returns:
            DepthReviewResult
        """
        issues = []
        chapter_scores = {}

        # 构建 Wind 锚点表（审查改进：LLM 有标准答案可对照）
        wind_anchor = ""
        if wind_data:
            try:
                from ..qual_v8.data_anchor import get_data_anchor
                anchor = get_data_anchor(wind_data)
                all_a = anchor.get_all_anchors()
                if all_a:
                    fys = sorted({dp.fiscal_year for pts in all_a.values()
                                  for dp in pts if dp.fiscal_year is not None})
                    rows = []
                    for k, pts in all_a.items():
                        row = {dp.fiscal_year: f"{dp.value:.2f}" for dp in pts if dp.fiscal_year is not None}
                        rows.append(f"| {k} | " + " | ".join(row.get(fy, "—") for fy in fys) + " |")
                    wind_anchor = "| 指标 | " + " | ".join(f"FY{fy}" for fy in fys) + " |\n|------|" + \
                        "--------|" * len(fys) + "\n" + "\n".join(rows)
            except Exception as e:
                logger.warning(f"深度审查锚点构建失败: {e}")

        for ch_num, content in chapters.items():
            # 1. 使用关键词进行快速评估
            keyword_score = self._evaluate_by_keywords(content)

            # 2. 使用LLM进行深度评估（如果可用）
            llm_score = None
            llm_issues = []
            if llm_caller:
                llm_score, llm_issues = self._evaluate_by_llm(content, ch_num, llm_caller, wind_anchor)

            # 3. 综合评分
            if llm_score is not None:
                # LLM评分权重更高
                final_score = int(keyword_score * 0.3 + llm_score * 0.7)
            else:
                final_score = keyword_score

            chapter_scores[ch_num] = final_score

            # 4. 检查是否低于阈值
            if final_score < 60:
                severity = "fatal" if final_score < 40 else "important"
                issues.append(DepthIssue(
                    issue_type="shallow_analysis",
                    severity=severity,
                    description=f"第{ch_num}章分析深度不足（评分{final_score}/100）",
                    chapter=ch_num,
                    score=final_score,
                ))

            # 5. 添加LLM发现的具体问题
            issues.extend(llm_issues)

        # 计算总体评分
        if chapter_scores:
            overall_score = sum(chapter_scores.values()) / len(chapter_scores)
        else:
            overall_score = 100.0

        # 检查是否有致命问题
        fatal_count = sum(1 for i in issues if i.severity == "fatal")
        important_count = sum(1 for i in issues if i.severity == "important")

        score = overall_score
        score -= fatal_count * 10
        score -= important_count * 5
        score = max(0.0, min(100.0, score))

        passed = fatal_count == 0 and score >= 60.0

        if not passed:
            logger.warning(f"分析深度审查不通过: score={score:.0f}, issues={len(issues)}")

        return DepthReviewResult(
            passed=passed,
            issues=issues,
            score=score,
            chapter_scores=chapter_scores,
        )

    def _evaluate_by_keywords(self, content: str) -> int:
        """使用关键词进行快速评估"""
        score = 0
        total_weight = 0

        for dimension, config in self.depth_dimensions.items():  # noqa: PERF102
            keywords = config["keywords"]
            weight = config["weight"]

            # 统计关键词出现次数
            keyword_count = sum(1 for kw in keywords if kw in content)

            # 计算该维度得分（0-100）
            if keyword_count >= 3:
                dimension_score = 100
            elif keyword_count >= 2:
                dimension_score = 70
            elif keyword_count >= 1:
                dimension_score = 40
            else:
                dimension_score = 0

            score += dimension_score * weight
            total_weight += weight

        # 归一化到0-100
        if total_weight > 0:
            return int(score / total_weight)
        return 0

    def _evaluate_by_llm(
        self,
        content: str,
        ch_num: int,
        llm_caller: Callable[[str, str], str],
        wind_anchor: str = "",
    ) -> tuple[int | None, list[DepthIssue]]:
        """使用LLM进行深度评估（审查改进：注入 Wind 锚点 + 自适应截断）

        P1-③：单章 ≤20000 字符全文送审；超限按小节分批（避免无谓截断）。
        """
        issues = []

        # 自适应分批（P1）：超 20000 按小节切，分批评分后取最低（保守）
        segments = _split_for_review(content, max_chars=20000)

        scores = []
        try:
            for seg in segments:
                anchor_section = f"\n\n## Wind 验证数据（数据支撑评估的标准答案）\n{wind_anchor}" if wind_anchor else ""
                prompt = self.review_prompt_template.format(
                    content=seg,
                    wind_anchor=anchor_section,
                )
                response = llm_caller(f"depth_review_ch{ch_num}", prompt)
                score = self._parse_llm_score(response)
                if score is not None:
                    scores.append(score)
                issues.extend(self._parse_llm_issues(response, ch_num))

            if not scores:
                return None, issues
            # 多段取最低分（保守：任一局部深度不足即视为整体不足）
            return min(scores), issues

        except (DeterministicLLMFailure, LLMCallBudgetExceeded, WallClockDeadlineExceeded):
            raise  # v3.1 P0-A-3 白名单：预算/墙钟/确定性失败不降级（fail-closed）
        except Exception as e:
            logger.warning(f"LLM深度审查失败: {e}")
            return None, []

    def _parse_llm_score(self, response: str) -> int:
        """解析LLM返回的评分"""
        # 尝试提取总分
        total_pattern = r"总分[：:]\s*(\d+)"
        match = re.search(total_pattern, response)
        if match:
            return int(match.group(1))

        # 尝试提取各个分数并计算平均
        scores = []
        for dimension in self.depth_dimensions.keys():  # noqa: SIM118
            pattern = f"{dimension}[：:]\\s*(\\d+)"
            match = re.search(pattern, response)
            if match:
                scores.append(int(match.group(1)))

        if scores:
            return int(sum(scores) / len(scores))

        # 默认返回中等分数
        return 50

    def _parse_llm_issues(self, response: str, ch_num: int) -> list[DepthIssue]:
        """解析LLM返回的问题"""
        issues = []

        # 提取问题描述
        problem_pattern = r"问题[：:]\s*(.+?)(?:\n|$)"
        match = re.search(problem_pattern, response)
        if match:
            problem_text = match.group(1).strip()

            # 根据问题内容判断类型
            if "定量" in problem_text or "数据" in problem_text:
                issue_type = "missing_quantitative"
            elif "敏感性" in problem_text or "情景" in problem_text:
                issue_type = "missing_sensitivity"
            elif "对比" in problem_text or "行业" in problem_text:
                issue_type = "missing_comparison"
            else:
                issue_type = "shallow_analysis"

            issues.append(DepthIssue(
                issue_type=issue_type,
                severity="suggestion",
                description=f"第{ch_num}章: {problem_text}",
                chapter=ch_num,
                score=0,
            ))

        return issues


def check_depth(
    chapters: dict[int, str],
    llm_caller: Callable[[str, str], str] | None = None,
    wind_data: dict | None = None,
) -> DepthReviewResult:
    """
    分析深度审查（入口函数）

    Args:
        chapters: 各章节内容 {chapter_num: content}
        llm_caller: LLM调用函数（可选）
        wind_data: Wind 数据（注入锚点表）

    Returns:
        DepthReviewResult
    """
    reviewer = DepthReviewer()
    return reviewer.check(chapters, llm_caller, wind_data)


def _split_for_review(content: str, max_chars: int = 20000) -> list[str]:
    """P1-③ 自适应分批：≤max_chars 全文；超限按小节/句子边界切"""
    if len(content) <= max_chars:
        return [content]
    # 按 ## 小节切
    import re
    sub_parts = re.split(r"(?m)(?=^##\s)", content)
    segments = []
    buf = ""
    for sp in sub_parts:
        if len(buf) + len(sp) > max_chars and buf:
            segments.append(buf)
            buf = sp
        else:
            buf += sp
    if buf:
        segments.append(buf)
    # 单段仍超限 → 按句子边界
    final = []
    for seg in segments:
        if len(seg) <= max_chars:
            final.append(seg)
            continue
        sents = re.split(r"(?<=[。！？\n])", seg)
        buf = ""
        for s in sents:
            if len(buf) + len(s) > max_chars and buf:
                final.append(buf)
                buf = s
            else:
                buf += s
        if buf:
            final.append(buf)
    return final
