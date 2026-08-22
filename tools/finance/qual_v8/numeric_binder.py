"""数字回填器（PGNB 架构层，v2——heavyskill K8 审查升级）——LLM 写作占位符 → 程序按锚点回填

docs/qual-pgnb-architecture.md 方案实现 + heavyskill 审查升级：
v1：只有 7 个财务绝对额占位符（根治性 4/10——派生指标/运营数据缺失、裸数字未拦截）
v2 升级（heavyskill 三条建议）：
1. **派生指标程序化**：毛利率/净利率/ROE/营业利润率/同比增速等由程序按锚点计算，
   LLM 引用派生占位符不自算（[{{毛利率}}] → 程序算 FY2025 毛利/营收）
2. **裸数字硬拦截**：validate_against_anchor 检查章节裸财务数字（非占位符）vs 锚点，
   不匹配 → 记问题（配合校验器 fail-closed，不依赖 prompt 配合）
3. **运营/别名归一**：占位符指标名 canonical 归一 + 无锚点严格 [数据待核]
"""
import logging
import re

logger = logging.getLogger(__name__)

# 占位符语法：[{{指标名}}] 或 [{{指标名:财年}}]（可选指定财年，默认最新）
PLACEHOLDER_RE = re.compile(r"\[{{([^}:]+)(?::(\d{4}))?}}\]")

# 派生指标 → (公式名, [依赖锚点指标])——程序计算，LLM 只引用不自算
DERIVED_METRICS: dict[str, dict] = {
    "毛利率": {"formula": "毛利/营收（毛利暂无锚点→标记不可得）", "deps": [], "available": False},
    "净利率": {"formula": "归母净利润/营业收入", "deps": ["归母净利润", "营业收入"], "available": True},
    "营业利润率": {"formula": "营业利润/营业收入", "deps": ["营业利润", "营业收入"], "available": True},
    "ROE": {"formula": "归母净利润/年所有者权益合计", "deps": ["归母净利润", "年所有者权益合计"], "available": True},
    "资产负债率": {"formula": "年负债合计/总资产", "deps": ["年负债合计", "总资产"], "available": True},
    "营收同比": {"formula": "(本期营收-上期营收)/上期营收", "deps": ["营业收入"], "available": True},
    "净利同比": {"formula": "(本期净利-上期净利)/上期净利", "deps": ["归母净利润"], "available": True},
    "经营现金流/营收": {"formula": "经营现金流/营业收入", "deps": ["经营活动现金流量净额", "营业收入"], "available": True},
}


def _calc_derived(metric: str, pts_dict: dict[str, list], fy: int | None) -> float | None:
    """按公式计算派生指标值（程序计算——LLM 不自算）"""
    spec = DERIVED_METRICS.get(metric)
    if not spec or not spec["available"]:
        return None
    deps = spec["deps"]
    if metric in ("营收同比", "净利同比"):
        # 需要相邻两财年
        key = deps[0]
        pts = pts_dict.get(key) or []
        if len(pts) < 2:
            return None
        # 按财年排序取最新两期
        sorted_pts = sorted(pts, key=lambda dp: dp.fiscal_year or 0)
        cur, prev = sorted_pts[-1], sorted_pts[-2]
        if prev.value == 0:
            return None
        return (cur.value - prev.value) / abs(prev.value)
    # 比率类：deps[0]/deps[1]
    a_pts = pts_dict.get(deps[0]) or []
    b_pts = pts_dict.get(deps[1]) or []
    if not a_pts or not b_pts:
        return None
    a_sorted, b_sorted = sorted(a_pts, key=lambda dp: dp.fiscal_year or 0), sorted(b_pts, key=lambda dp: dp.fiscal_year or 0)
    if fy is not None:
        a = next((dp.value for dp in a_sorted if dp.fiscal_year == fy), None)
        b = next((dp.value for dp in b_sorted if dp.fiscal_year == fy), None)
    else:
        a, b = a_sorted[-1].value, b_sorted[-1].value
    if a is None or b is None or b == 0:
        return None
    return a / b


def _format_value(value: float) -> str:
    """锚点值格式化：两位小数，负值保留符号"""
    return f"{value:.2f}"


def _format_pct(value: float) -> str:
    """百分比格式化（派生比率类）：-11.39%"""
    return f"{value:.2%}"


def bind_placeholders(content: str, anchor, chapter_num: int,
                      fiscal_year: int | None = None,
                      ops_data: dict | None = None) -> tuple[str, list[str]]:
    """回填章节中的占位符。

    Args:
        content: LLM 生成内容（含 [{{指标}}] 占位符）
        anchor: DataAnchor（财务锚点单一事实来源）
        chapter_num: 章节号
        fiscal_year: 默认回填财年（None=最新）
        ops_data: 运营数据锚点（v3：财报提取的 DAU/GMV/交付量等——
                  {指标名: {value, source}}，由 fact_extractor 提供，源=财报）

    Returns:
        (回填后内容, 未解析占位符列表)——未解析的保留 [数据待核] + 记 warning（不静默）
    """
    if not content or not anchor:
        return content, []

    unresolved: list[str] = []

    # 收集全部锚点（供派生指标计算）
    pts_dict: dict[str, list] = {}
    try:
        all_anchors = anchor.get_all_anchors() if hasattr(anchor, "get_all_anchors") else {}
        for k, pts in all_anchors.items():
            pts_dict[k] = list(pts)
    except Exception:
        pts_dict = {}

    def _resolve(match: re.Match) -> str:
        metric = match.group(1).strip()
        fy_spec = match.group(2)
        try:
            fy = int(fy_spec) if fy_spec else (fiscal_year or None)

            # v3：运营数据锚点（财报提取——用户原则：Wind 没有的由财报提供）
            if ops_data and metric in ops_data:
                _ops = ops_data[metric]
                if isinstance(_ops, dict) and _ops.get("value") is not None:
                    _v = _ops["value"]
                    _src = _ops.get("source", "")
                    return f"{_v}{_ops.get('unit', '')}{('（' + _src + '）') if _src else ''}"
                unresolved.append(f"{metric}（运营数据缺失）")
                return f"[数据待核:{metric}]"

            # 派生指标 → 程序计算（heavyskill 升级①：LLM 只引用不自算）
            if metric in DERIVED_METRICS:
                spec = DERIVED_METRICS[metric]
                if not spec["available"]:
                    unresolved.append(f"{metric}（锚点缺失，不可派生）")
                    return f"[数据待核:{metric}]"
                val = _calc_derived(metric, pts_dict, fy)
                if val is None:
                    unresolved.append(f"{metric}（派生计算失败/依赖缺失）")
                    return f"[数据待核:{metric}]"
                # 同比类输出百分比；比率类输出百分比
                return _format_pct(val)

            # 原始指标 → 查锚点
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


# ====================================================================
# heavyskill 升级③：裸数字程序绑定（2026-08-22 实测驱动——拦截即替换，零 LLM 重写依赖）
# ====================================================================


def bind_bare_numbers(content: str, anchor, chapter_num: int) -> tuple[str, list[str]]:
    """裸数字程序绑定：LLM 未用占位符直接写财务数字时，若该指标有锚点且值不匹配
    任一财年 → **程序把数字替换为 [{{指标}}] 占位符**（占位符随后由 bind_placeholders
    按锚点回填，数字 100% 来自锚点）；命中锚点/无锚点/年份 → 原样保留。

    实测背景（2026-08-22 小鹏全流程）：第5章 LLM 写"营业利润=12.5"（锚点 -44.16）、
    "总资产=0.79"（锚点 1031.63），validate_bare_numbers 拦截后依赖 LLM 重写，
    而重试引导"删除不符数值"→ LLM 删光所有数字 → 空壳章（0 小数）。
    修复：拦截即程序替换为占位符，不进入重试循环——LLM 无法靠"删数字"逃避校验。

    Returns:
        (替换后内容, fixes 列表)——无法判定的（无锚点）保留原文，由 validate_bare_numbers 收口
    """
    if not content or not anchor:
        return content, []

    fixes: list[str] = []
    pts_dict: dict[str, list] = {}
    try:
        all_anchors = anchor.get_all_anchors() if hasattr(anchor, "get_all_anchors") else {}
        for k, pts in all_anchors.items():
            pts_dict[k] = list(pts)
    except Exception:
        pts_dict = {}

    def _repl(m: re.Match) -> str:
        metric = m.group(1)
        try:
            value = float(m.group(2))
        except (TypeError, ValueError):
            return m.group(0)
        # 4 位年份豁免（2023.0/2024.0 误写为财务值——年份非财务数字）
        if 2020 <= value <= 2035 and value == int(value) and len(m.group(2).split(".")[0]) == 4:
            return m.group(0)
        unit = m.group(3) or "亿"
        v = value
        if unit in ("万元", "万"):
            v = value / 10000.0

        # 百分比指标：派生可计算 → 程序比对；不可计算 → 保留（语义检测兜底）
        if unit == "%":
            if metric in DERIVED_METRICS and DERIVED_METRICS[metric]["available"]:
                calc = _calc_derived(metric, pts_dict, None)
                if calc is not None and abs((v / 100.0) - calc) <= 0.01:
                    return m.group(0)  # 命中派生计算值 → 合法
                if calc is not None:
                    head = m.group(0)[: m.start(2) - m.start(0)]
                    tail = m.group(0)[m.end(2) - m.start(0):]
                    fixes.append(f"{metric}: {value}% → 占位符（程序计算 {calc:.2%}）")
                    return head + f"[{{{{{metric}}}}}]" + tail
            return m.group(0)

        # 绝对额指标
        pts = anchor.get_metric_points(metric)
        if not pts:
            return m.group(0)  # 无锚点（毛利率/运营数据）→ 保留，不猜测
        if any(
            dp.value is not None
            and abs(v - dp.value) / max(abs(dp.value), 1e-9) <= 0.01
            for dp in pts
        ):
            return m.group(0)  # 命中任一财年锚点 → 合法

        # 幻觉数字 → 替换为占位符（保留指标名与单位，数字位置换占位符）
        head = m.group(0)[: m.start(2) - m.start(0)]
        tail = m.group(0)[m.end(2) - m.start(0):]
        latest = pts[-1]
        fixes.append(
            f"{metric}: {value} → 占位符（锚点 FY{latest.fiscal_year}={latest.value:.2f}）"
        )
        return head + f"[{{{{{metric}}}}}]" + tail

    new_content = _METRIC_NUM_RE.sub(_repl, content)
    return new_content, fixes


# ====================================================================
# heavyskill 升级②：裸财务数字硬拦截（不依赖 prompt 配合）
# ====================================================================

# 财务指标名 → 匹配"指标名 + 数字 + 单位"的裸数字（非占位符）
# 单位组含 %（净利率5.0% 紧跟）与 亿元/万（营收14.0亿元）
_METRIC_NUM_RE = re.compile(
    r"(营业收入|营业利润|归母净利润|经营活动现金流量净额|总资产|"
    r"年负债合计|年所有者权益合计|净利润|毛利率|净利率|营业利润率)\s*"
    r"[^\d\-]{0,8}(-?\d+\.?\d*)\s*(亿元|亿|万元|万|%)?"
)


def validate_bare_numbers(content: str, anchor, chapter_num: int) -> list[str]:
    """检查章节中的裸财务数字（LLM 未用占位符直接写数）——heavyskill 升级②。

    裸数字与锚点任一财年值偏差>1% → 记问题（配合校验器 fail-closed；
    即使锚点命中也可能口径错误，但至少拦截纯幻觉如 14.0 vs 767.20）。

    Returns:
        问题列表（空=无裸数字幻觉）
    """
    if not content or not anchor:
        return []

    # 收集全部锚点（供派生指标计算比对）
    pts_dict: dict[str, list] = {}
    try:
        all_anchors = anchor.get_all_anchors() if hasattr(anchor, "get_all_anchors") else {}
        for k, pts in all_anchors.items():
            pts_dict[k] = list(pts)
    except Exception:
        pts_dict = {}

    problems: list[str] = []
    for m in _METRIC_NUM_RE.finditer(content):
        metric = m.group(1)
        try:
            value = float(m.group(2))
        except (TypeError, ValueError):
            continue
        # v3：4 位年份豁免——LLM 把财年（2023/2024/2025）写成 "2024.0" 放在指标后
        # （"营业收入2024.0亿元"= FY2024 引用误写，非财务值幻觉）——豁免避免误报重试
        if 2020 <= value <= 2035 and value == int(value) and len(m.group(2).split(".")[0]) == 4:
            continue
        # 单位万元→亿
        unit = m.group(3) or "亿"
        if unit in ("万元", "万"):
            value = value / 10000.0
        # 百分比指标（净利率/营业利润率）→ 用派生指标程序计算结果比对（heavyskill 升级②）
        if unit == "%" and metric in DERIVED_METRICS:
            spec = DERIVED_METRICS[metric]
            if spec["available"]:
                calc = _calc_derived(metric, pts_dict, None)
                if calc is not None and abs((value / 100.0) - calc) > 0.01:
                    problems.append(
                        f"第{chapter_num}章 裸数字幻觉: {metric}={value}%"
                        f"（程序计算应为 {calc:.2%}，应用 [{{{{{metric}}}}}] 占位符）"
                    )
            continue
        if unit == "%":
            continue  # 非锚点百分比跳过
        # 与锚点任一财年比对（1% 容差）
        pts = anchor.get_metric_points(metric)
        if not pts:
            continue
        hit = any(
            dp.value is not None
            and abs(value - dp.value) / max(abs(dp.value), 1e-9) <= 0.01
            for dp in pts
        )
        if not hit:
            problems.append(
                f"第{chapter_num}章 裸数字幻觉: {metric}={value}（不匹配任一财年锚点，"
                f"应用 [{{{{{metric}}}}}] 占位符）"
            )
    return problems


# ====================================================================
# v3：占位符语义错配检测（heavyskill 建议③——[{{毛利率}}] 误用等）
# ====================================================================

# 占位符上下文关键词 → 期望指标（检测 LLM 用错占位符：如写"毛利率[{{营业收入}}]"）
_PLACEHOLDER_CONTEXT_HINTS: dict[str, str] = {
    "毛利率": "毛利率",
    "净利率": "净利率",
    "净利": "归母净利润",
    "利润": "营业利润",
    "营收": "营业收入",
    "收入": "营业收入",
    "现金": "经营活动现金流量净额",
    "资产": "总资产",
    "负债": "年负债合计",
    "权益": "年所有者权益合计",
}


def validate_placeholder_semantics(content: str) -> list[str]:
    """检测占位符语义错配——LLM 写了 [{{指标}}] 但上下文暗示另一指标。

    例："毛利率[{{营业收入}}]" → 应写 [{{毛利率}}]（净利率是派生指标）。
    规则：占位符前 15 字符内出现关键指标词，且与该占位符指标不匹配 → 问题。

    Returns:
        问题列表（空=无错配）
    """
    if not content:
        return []

    problems: list[str] = []
    for m in PLACEHOLDER_RE.finditer(content):
        metric = m.group(1).strip()
        ctx_before = content[max(0, m.start() - 15):m.start()]
        for kw, expected in _PLACEHOLDER_CONTEXT_HINTS.items():
            if kw in ctx_before and expected != metric:
                problems.append(
                    f"占位符语义错配: 上下文'{ctx_before[-10:]}'暗示'{expected}'，"
                    f"但用了'[{{{{{metric}}}}}]'——应写 [{{{{{expected}}}}}]"
                )
                break
    return problems
