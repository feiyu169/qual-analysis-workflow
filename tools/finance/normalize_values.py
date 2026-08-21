"""数值转写归一预处理器（B5-2：配对原文正则复核，拦截单位错误）

拦截"4.102亿→410.2亿"类单位错位：
- parse_number_with_unit：解析中文数值转写（约/以上/区间/千分位/单位）→ 归一为"亿"
- unit_error_detect：提取值 vs 原文数量级复核（10 倍/100 倍错位检测）
- verify_value_against_source：复核命中原文才保留（未命中 → confidence=low）

单位基准：全部归一为"亿"（财务口径）。
- 万 → 亿：÷10000
- 百万 → 亿：÷100
- 千 → 亿：÷100000
- 元（单价/ARPU 等）不换亿（保持原单位），由调用方标注
"""
import re

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
