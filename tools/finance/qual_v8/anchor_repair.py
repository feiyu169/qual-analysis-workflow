"""锚点驱动的确定性数值修复层（ADVC，docs/qual-anchor-repair-architecture.md）

层1 修复引擎（唯一新组件，零 LLM）：
- repair_chapter_values：单章扫描 → T1 高置信自动替换（span 定位 + 自证）/ T2 低置信（开关）
  / T3 只标注 / digit_typo 弱提示（hints 通道，不阻断）
- sweep_all_chapters：全章确定性清洗（修复循环/组装闸门共用）

T1 六条件：指标绑定（财务锚点指标）+ 唯一高置信签名 + 语境排斥 + span 精确定位 +
自证（替换后整章 validate_chapter_any_fy 必须通过——与修复前同一把 fail-closed 校验器）。
T2 低置信（enable_t2 开关，默认关）：仅弱签名（digit_typo）但候选锚点唯一（FY 上下文唯一）
→ 仍可自动替换（同样走自证闭环）。
T3 只标注：无签名/歧义/跨指标暗示 → UnresolvedValue 证据清单（绝不喂 LLM）。
digit_typo 弱提示（T2 关 或 目标歧义）：hints 清单——提示不阻断，调用方按需呈现。
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RepairFix:
    """一次确定性修复（审计记录）"""
    chapter: int
    metric: str
    metric_key: str
    span: tuple[int, int]
    old_value: float
    new_value: float
    fiscal_year: int | None
    kind: str          # "multiply10" | "divide10" | "prefix_drop" | "digit_typo"
    confidence: str    # "high"（T1）| "low"（T2）


@dataclass
class UnresolvedValue:
    """T3 只标注项（证据化清单，不自动修复）"""
    chapter: int
    metric: str
    metric_key: str
    value: float
    reason: str        # "no_signature" | "ambiguous" | "conflict"
    detail: str


@dataclass
class ChapterRepairResult:
    """单章修复结果"""
    content: str
    fixes: list[RepairFix] = field(default_factory=list)
    unresolved: list[UnresolvedValue] = field(default_factory=list)
    hints: list[UnresolvedValue] = field(default_factory=list)  # P2：digit_typo 弱提示（不阻断）


def _format_value(new_value: float, old_span_text: str) -> str:
    """新值格式化：保留原值的小数位风格（原"31.63"两位小数 → "1031.63"）"""
    # 提取原小数位
    if "." in old_span_text:
        decimals = len(old_span_text.split(".")[1].rstrip("0"))
    else:
        decimals = 0
    decimals = max(0, min(decimals, 4))
    return f"{new_value:.{decimals}f}"


def repair_chapter_values(
    chapter_num: int,
    content: str,
    anchor,
    *,
    enable_t2: bool = False,
) -> ChapterRepairResult:
    """单章确定性数值修复（T1 自动替换 + T2 低置信开关 + T3 只标注 + digit_typo 弱提示）。

    Args:
        chapter_num: 章节号
        content: 章节内容
        anchor: DataAnchor（含锚点 + extract_data_spans + validate_chapter_any_fy）
        enable_t2: T2 低置信修复开关（P1：默认关；开时弱签名+FY 上下文唯一 → 仍可替换，
            自证闭环兜底——宁可不修不误修）

    Returns:
        ChapterRepairResult（清洗后内容 + 修复记录 + 未解决清单 + 弱提示清单）
    """
    result = ChapterRepairResult(content=content)

    from ..normalize_values import anchor_deviation

    spans = anchor.extract_data_spans(content)
    if not spans:
        return result

    # 指标 → 锚点候选列表（多财年）
    def _anchor_candidates(metric_key: str) -> list[tuple[float, int | None]]:
        if metric_key.startswith("pct:"):
            return []  # 百分比指标不入锚点
        return [(dp.value, dp.fiscal_year) for dp in anchor.get_metric_points(metric_key)]

    # 第一遍：判定 T1/T2 替换集 / T3 未解决 / digit_typo 弱提示
    fixes: list[RepairFix] = []
    unresolved: list[UnresolvedValue] = []
    hints: list[UnresolvedValue] = []

    for item in spans:
        metric_key = item["metric_key"]
        value = item["value"]
        if metric_key.startswith("pct:"):
            continue
        candidates = _anchor_candidates(metric_key)
        if not candidates:
            continue

        # 精确命中任一锚点（1% 容差）→ 合法，跳过
        if any(abs(value - av) <= max(abs(av), 1e-9) * 0.01 for av, _ in candidates):
            continue

        devs = anchor_deviation(value, candidates)
        if not devs:
            # T3：无签名（幻觉值）→ 只标注
            unresolved.append(UnresolvedValue(
                chapter=chapter_num, metric=item["metric"], metric_key=metric_key,
                value=value, reason="no_signature",
                detail=f"{item['text']} 不匹配任何锚点的错位模式",
            ))
            continue

        # 高置信且唯一（单一锚点的强签名）
        high = [d for d in devs if d.confidence == "high"]
        if not high:
            # 仅弱签名（digit_typo hint）：
            # - T2 开 + 候选锚点唯一（FY 上下文唯一）→ 低置信替换（自证兜底）
            # - 否则 → digit_typo 弱提示（hints，不阻断；绝不喂 LLM）
            weak = [d for d in devs if d.confidence in ("low", "hint")]
            if enable_t2 and weak:
                unique_targets = {(d.anchor_value, d.fiscal_year) for d in weak}
                if len(unique_targets) == 1:
                    d = weak[0]
                    # 语境排斥：span 文本含近似/区间修饰 → 不修
                    if not any(kw in item["text"] for kw in
                               ("约", "左右", "以上", "以下", "区间", "范围")):
                        fixes.append(RepairFix(
                            chapter=chapter_num, metric=item["metric"],
                            metric_key=metric_key, span=item["span"],
                            old_value=value, new_value=d.anchor_value,
                            fiscal_year=d.fiscal_year, kind=d.kind,
                            confidence="low",  # T2 低置信
                        ))
                        continue
            # T3/T2 未命中 → digit_typo 弱提示（不阻断；记录供调用方呈现）
            hints.append(UnresolvedValue(
                chapter=chapter_num, metric=item["metric"], metric_key=metric_key,
                value=value, reason="digit_typo_hint",
                detail=f"{item['text']} 仅弱签名（{'、'.join(sorted({x.kind for x in weak or devs}))}）",
            ))
            continue

        # 唯一性：多个不同锚点的高置信偏差 → 歧义 T3（不做猜测）
        unique_anchors = {(d.anchor_value, d.fiscal_year) for d in high}
        if len(unique_anchors) > 1:
            unresolved.append(UnresolvedValue(
                chapter=chapter_num, metric=item["metric"], metric_key=metric_key,
                value=value, reason="ambiguous",
                detail=f"{item['text']} 可匹配多锚点 {sorted(unique_anchors)}",
            ))
            continue

        d = high[0]
        # 语境排斥：span 文本含近似/区间修饰 → 不修（extract_data_spans 已排除部分，再兜底）
        if any(kw in item["text"] for kw in ("约", "左右", "以上", "以下", "区间", "范围")):
            unresolved.append(UnresolvedValue(
                chapter=chapter_num, metric=item["metric"], metric_key=metric_key,
                value=value, reason="conflict",
                detail=f"{item['text']} 含近似/区间语境，不自动替换",
            ))
            continue

        fixes.append(RepairFix(
            chapter=chapter_num, metric=item["metric"], metric_key=metric_key,
            span=item["span"], old_value=value, new_value=d.anchor_value,
            fiscal_year=d.fiscal_year, kind=d.kind, confidence=d.confidence,
        ))

    result.hints = hints
    if not fixes:
        result.unresolved = unresolved  # 修复局部 unresolved 未回写 result 的 bug
        return result

    # 第二遍：统一替换（span 从后往前，避免位置偏移）
    new_content = content
    for fix in sorted(fixes, key=lambda f: f.span[0], reverse=True):
        old_span_text = new_content[fix.span[0]:fix.span[1]]
        # span 内定位数字 token（提取数字部分替换，保留前后单位）
        import re
        num_match = re.search(r"-?\d+\.?\d*", old_span_text)
        if not num_match:
            continue
        num_start = fix.span[0] + num_match.start()
        num_end = fix.span[0] + num_match.end()
        replacement = _format_value(fix.new_value, num_match.group(0))
        new_content = new_content[:num_start] + replacement + new_content[num_end:]

    # 第三遍：自证——替换后整章必须通过 validate_chapter_any_fy
    try:
        remaining_errors = anchor.validate_chapter_any_fy(chapter_num, new_content)
    except Exception as e:
        logger.warning(f"ADVC 自证异常（回滚，不修复）: {e}")
        return result  # 自证失败 → 整体回滚（宁可不修不误修）

    if remaining_errors:
        # 自证失败：可能误判 → 回滚全部，转 T3
        logger.warning(
            f"ADVC 自证失败（第{chapter_num}章 {len(fixes)} 处修复回滚）: "
            f"{remaining_errors[:3]}"
        )
        for fix in fixes:
            unresolved.append(UnresolvedValue(
                chapter=chapter_num, metric=fix.metric, metric_key=fix.metric_key,
                value=fix.old_value, reason="conflict",
                detail=f"自证失败：{fix.metric}={fix.old_value} 无法自动校正",
            ))
        return ChapterRepairResult(content=content, fixes=[], unresolved=unresolved,
                                   hints=hints)

    logger.info(f"ADVC 修复第{chapter_num}章 {len(fixes)} 处（自证通过）")
    return ChapterRepairResult(content=new_content, fixes=fixes, unresolved=unresolved,
                               hints=hints)


def sweep_all_chapters(
    chapters: dict[int, str],
    anchor,
    *,
    enable_t2: bool = False,
) -> tuple[dict[int, str], list[RepairFix], list[UnresolvedValue], list[UnresolvedValue]]:
    """全章确定性清洗（ADVC 层1：修复循环轮首 / 组装闸门救援共用）。

    Returns:
        (fixed_chapters, fixes, unresolved, hints) —— 4 元组（P2：hints 为 digit_typo 弱提示）
    """
    fixed: dict[int, str] = dict(chapters)
    all_fixes: list[RepairFix] = []
    all_unresolved: list[UnresolvedValue] = []
    all_hints: list[UnresolvedValue] = []

    for ch_num, content in chapters.items():
        result = repair_chapter_values(ch_num, content, anchor, enable_t2=enable_t2)
        if result.fixes:
            fixed[ch_num] = result.content
        all_fixes.extend(result.fixes)
        all_unresolved.extend(result.unresolved)
        all_hints.extend(result.hints)

    if all_fixes or all_hints:
        logger.info(
            f"ADVC sweep: 修复 {len(all_fixes)} 处 / 未解决 {len(all_unresolved)} 处"
            f" / 弱提示 {len(all_hints)} 处"
        )
    return fixed, all_fixes, all_unresolved, all_hints
