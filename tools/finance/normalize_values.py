"""数值转写归一预处理器（B5-2：配对原文正则复核，拦截单位错误）

拦截"4.102亿→410.2亿"类单位错位：
- parse_number_with_unit：解析中文数值转写（约/以上/区间/千分位/单位）→ 归一为"亿"
- unit_error_detect：提取值 vs 原文数量级复核（10 倍/100 倍错位检测）
- verify_value_against_source：复核命中原文才保留（未命中 → confidence=low）
- anchor_deviation：锚点错位签名检测（ADVC 层0——×10ⁿ/÷10ⁿ/prefix_drop/digit_typo）

单位基准：全部归一为"亿"（财务口径）。
- 万 → 亿：÷10000
- 百万 → 亿：÷100
- 千 → 亿：÷100000
- 元（单价/ARPU 等）不换亿（保持原单位），由调用方标注
"""
import re
from dataclasses import dataclass

# 数字正则（含千分位/负号/小数）
_NUM_RE = re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?")
# 中文单位 → 换算到"亿"的除数
_CN_UNIT_TO_YI = {
    "万亿": 1,      # 万亿→亿：×10000
    "亿": 1,
    "万": 0.0001,
    "千": 1e-5,
    "百万": 0.01,
    "百": 1e-6,
}
# 语境词（约/以上/区间）
_APPROX_PREFIX = ("约", "大约", "接近", "近", "逾", "超", "超过", "达", "高达", "突破")
_RANGE_SEP = ("-", "~", "至", "到")


# ====================================================================
# ADVC 层0：锚点错位签名检测（docs/qual-anchor-repair-architecture.md）
# ====================================================================

@dataclass
class AnchorDeviation:
    """锚点错位签名（一次候选修复的判定结果）"""
    kind: str                      # "multiply10" | "divide10" | "prefix_drop" | "digit_typo"
    anchor_value: float            # 匹配的锚点值
    fiscal_year: int | None        # 锚点财年
    confidence: str = "high"       # "high"（T1 可替换）| "low"（T2 候选）| "hint"（仅提示）
    factor: int | None = None      # ×10^n / ÷10^n 的 n
    note: str = ""


def _digit_string(value: float) -> str:
    """数值 → 纯数字串（去符号/千分位/小数点/尾零）——签名比较基准"""
    s = f"{value:.10f}".rstrip("0").rstrip(".")
    if s.startswith("-"):
        s = s.lstrip("-")
    return s.replace(".", "").replace(",", "")


def anchor_deviation(
    value: float,
    anchors: list[tuple[float, int | None]],
    tolerance: float = 1e-6,
) -> list[AnchorDeviation]:
    """ADVC 层0：值 vs 锚点列表的错位签名检测（纯函数，无 DataAnchor 依赖）。

    签名（数字串比较，单位已归一为"亿"）：
    1. 精确命中（EXACT）→ 不产生偏差（返回空——不是错位）
    2. ×10ⁿ/÷10ⁿ（n=1..4）：覆盖小数点错位（1031.63→103.163）、单位错位（亿↔万×10⁴）
    3. prefix_drop：value 数字串是 anchor 数字串的**后缀**且丢失前缀 ≥2 位
       （覆盖 1031.63→31.63：anchor="103163" ⊃ value="3163"）
       丢 1 位 → digit_typo 弱签名
    4. digit_typo：编辑距离 ≤2（弱提示，仅 hint）

    Args:
        value: 内容中的数值
        anchors: [(锚点值, 财年), ...]（多财年）
        tolerance: 精确比较容差

    Returns:
        AnchorDeviation 列表（可能多个候选——由调用方 FY 归因消歧）
    """
    deviations: list[AnchorDeviation] = []
    v_str = _digit_string(value)

    for anchor_value, fy in anchors:
        if anchor_value is None or anchor_value == 0:
            continue
        # 精确命中 → 不是错位
        if abs(value - anchor_value) <= max(abs(anchor_value), 1e-9) * tolerance:
            continue
        a_str = _digit_string(anchor_value)

        # ×10ⁿ/÷10ⁿ（n=1..4）
        for n in range(1, 5):
            factor = 10 ** n
            if abs(value * factor - anchor_value) <= max(abs(anchor_value), 1e-9) * tolerance:
                deviations.append(AnchorDeviation(
                    kind="multiply10", anchor_value=anchor_value, fiscal_year=fy,
                    confidence="high", factor=n,
                    note=f"{value} ×10^{n} = {anchor_value}",
                ))
            elif abs(value - anchor_value * factor) <= max(abs(value), 1e-9) * tolerance:
                deviations.append(AnchorDeviation(
                    kind="divide10", anchor_value=anchor_value, fiscal_year=fy,
                    confidence="high", factor=n,
                    note=f"{value} ÷10^{n} = {anchor_value}",
                ))

        # prefix_drop：value 串是 anchor 串后缀，丢 ≥2 位前缀（1031.63→31.63）
        # 财务口径：数字串按 2 位小数比较（锚点 1031.6263 → 1031.63，与 LLM 转写一致）
        v2 = _digit_string(round(value, 2))
        a2 = _digit_string(round(anchor_value, 2))
        if a2.endswith(v2) and len(a2) - len(v2) >= 2 and v2:
            deviations.append(AnchorDeviation(
                kind="prefix_drop", anchor_value=anchor_value, fiscal_year=fy,
                confidence="high",
                note=f"{anchor_value}→{value}：数字串丢前缀 {len(a2)-len(v2)} 位",
            ))
        elif v2.endswith(a2) and len(v2) - len(a2) >= 2 and a2:
            # 反向：值多了前缀（如 1031.63 写成 101031.63）
            deviations.append(AnchorDeviation(
                kind="prefix_drop", anchor_value=anchor_value, fiscal_year=fy,
                confidence="high",
                note=f"{value}→{anchor_value}：数字串多前缀 {len(v2)-len(a2)} 位",
            ))
        # 丢 1 位 → 弱签名
        elif a2.endswith(v2) and len(a2) - len(v2) == 1 and v2:
            deviations.append(AnchorDeviation(
                kind="digit_typo", anchor_value=anchor_value, fiscal_year=fy,
                confidence="hint", note=f"{anchor_value}→{value}：丢 1 位（弱签名）",
            ))

    # digit_typo：编辑距离 ≤2（对未命中任何强签名的锚点）
    if not deviations:
        for anchor_value, fy in anchors:
            if anchor_value is None:
                continue
            a_str = _digit_string(anchor_value)
            if abs(len(a_str) - len(v_str)) <= 2 and v_str and a_str:
                # 简单编辑距离（Levenshtein 简化：长度差+不同位）
                dist = _simple_edit_distance(v_str, a_str)
                if 0 < dist <= 2:
                    deviations.append(AnchorDeviation(
                        kind="digit_typo", anchor_value=anchor_value, fiscal_year=fy,
                        confidence="hint", note=f"编辑距离 {dist}（弱签名）",
                    ))

    return deviations


def _simple_edit_distance(a: str, b: str) -> int:
    """简化编辑距离（长度差 + 逐位比较）——够用即可，非通用 Levenshtein"""
    if len(a) < len(b):
        a, b = b, a  # a 较长
    if len(a) - len(b) > 2:
        return len(a) - len(b)
    # 允许 b 在 a 中任意插入位置对齐（最长公共子序列近似）
    best = len(a) + len(b)
    for shift in range(len(a) - len(b) + 1):
        diff = 0
        for i in range(len(b)):
            if a[shift + i] != b[i]:
                diff += 1
        best = min(best, diff + shift + (len(a) - len(b) - shift))
    return best


def _parse_plain_number(s: str) -> float | None:
    """解析纯数字（含千分位 4,102.5 → 4102.5）"""
    m = _NUM_RE.search(s)
    if not m:
        return None
    return float(m.group().replace(",", ""))


def parse_number_with_unit(text: str) -> dict:
    """解析中文数值转写 → 归一为亿。

    Returns:
        {"value_yi": float|None, "unit": str, "approx": bool, "lower_bound": bool,
         "upper_bound": bool, "range": bool, "raw": str}
    """
    result = {"value_yi": None, "unit": "", "approx": False,
              "lower_bound": False, "upper_bound": False, "range": False, "raw": text.strip()}

    if not text:
        return result

    # 语境词
    stripped = text.strip()
    result["approx"] = any(stripped.startswith(p) for p in _APPROX_PREFIX)
    if any(k in stripped for k in ("以上", "及以上", "不低于", "至少")):
        result["lower_bound"] = True
    if any(k in stripped for k in ("以下", "及以下", "不超过", "至多")):
        result["upper_bound"] = True

    # 区间：4.1-4.3亿 / 4.1~4.3亿 / 4.1至4.3亿
    for sep in _RANGE_SEP:
        if sep in stripped:
            parts = stripped.split(sep, 1)
            lo = _parse_plain_number(parts[0])
            hi_text = parts[1]
            hi = _parse_plain_number(hi_text)
            unit = ""
            for u in sorted(_CN_UNIT_TO_YI, key=len, reverse=True):
                if u in hi_text or u in stripped:
                    unit = u
                    break
            if lo is not None and hi is not None:
                factor = _CN_UNIT_TO_YI.get(unit, 1)
                result["value_yi"] = round((lo + hi) / 2 * factor, 4)
                result["range"] = True
                result["unit"] = unit or "亿"
                return result

    # 单值 + 单位（长单位优先——"百万"须先于"万"，避免子串误匹配）
    unit = ""
    for u in sorted(_CN_UNIT_TO_YI, key=len, reverse=True):
        if u in stripped:
            unit = u
            break
    num = _parse_plain_number(stripped)
    if num is None:
        return result
    factor = _CN_UNIT_TO_YI.get(unit, 1)
    result["value_yi"] = round(num * factor, 4)
    result["unit"] = unit or "亿"
    return result


def unit_error_detect(source_text: str, extracted_value: float, tolerance: float = 0.02) -> bool:
    """数量级复核：提取值 vs 原文解析值（拦截 10 倍/100 倍单位错位）。

    Returns:
        True = 原文能找到数量级匹配的值（无单位错误）；False = 数量级不符（可能单位错位）
    """
    parsed = parse_number_with_unit(source_text)
    if parsed["value_yi"] is None or extracted_value is None:
        return True  # 无法核对，不误报
    ref = parsed["value_yi"]
    if ref == 0:
        return True
    ratio = abs(extracted_value - ref) / max(abs(ref), 1e-9)
    # 允许近似语境（约/达）更大容差；精确语境 2%
    tol = tolerance * 5 if parsed["approx"] else tolerance
    return ratio <= tol


def verify_value_against_source(source_text: str, extracted_value: float) -> str:
    """复核命中原文才保留（B5-2 验收）：未命中 → confidence=low。

    Returns:
        "high"（原文数量级匹配）/ "low"（未命中——单位错位或原文无此值）
    """
    if unit_error_detect(source_text, extracted_value):
        return "high"
    return "low"
