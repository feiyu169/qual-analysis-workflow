"""数字回填器（PGNB 架构层）——LLM 写作占位符 → 程序按锚点回填

docs/qual-pgnb-architecture.md 方案实现：
把财务数字从 LLM 写作职责中移出——LLM 只写 [{{指标}}] 占位符，
生成后由程序按 DataAnchor 锚点回填（零 LLM 幻觉数字）。
"""
import logging
import re

logger = logging.getLogger(__name__)

# 占位符语法：[{{指标名}}] 或 [{{指标名:财年}}]（可选指定财年，默认最新）
PLACEHOLDER_RE = re.compile(r"\[{{([^}:]+)(?::(\d{4}))?}}\]")


def _format_value(value: float) -> str:
    """锚点值格式化：两位小数，负值保留符号"""
    return f"{value:.2f}"


def bind_placeholders(content: str, anchor, chapter_num: int,
                      fiscal_year: int | None = None) -> tuple[str, list[str]]:
    """回填章节中的占位符。

    Args:
        content: LLM 生成内容（含 [{{指标}}] 占位符）
        anchor: DataAnchor（锚点单一事实来源）
        chapter_num: 章节号
        fiscal_year: 默认回填财年（None=最新）

    Returns:
        (回填后内容, 未解析占位符列表)——未解析的保留 [数据待核] + 记 warning（不静默）
    """
    if not content or not anchor:
        return content, []

    unresolved: list[str] = []

    def _resolve(match: re.Match) -> str:
        metric = match.group(1).strip()
        fy_spec = match.group(2)
        try:
            fy = int(fy_spec) if fy_spec else (fiscal_year or None)
            pts = anchor.get_metric_points(metric)
            if not pts:
                unresolved.append(f"{metric}（无锚点）")
                return f"[数据待核:{metric}]"
            if fy is not None:
                for dp in pts:
                    if dp.fiscal_year == fy:
                        return f"FY{fy} {_format_value(dp.value)}"
            # 默认最新财年
            latest = pts[-1]
            if latest.fiscal_year:
                return f"FY{latest.fiscal_year} {_format_value(latest.value)}"
            return _format_value(latest.value)
        except Exception as e:
            unresolved.append(f"{metric}（解析异常: {e}）")
            return f"[数据待核:{metric}]"

    bound = PLACEHOLDER_RE.sub(_resolve, content)
    if unresolved:
        logger.warning(
            f"PGNB 回填 {chapter_num} 章：{len(unresolved)} 个占位符无锚点"
            f"（{unresolved[:3]}）——保留 [数据待核] 标注"
        )
    return bound, unresolved
