"""
统一数值提取器（v9 新增，对标 dayu agent_type 模式化设计）。

合并 numeric_binder._METRIC_NUM_RE + data_anchor._extract_data_spans 的 regex 逻辑：
- 单一事实来源：所有数值提取从此模块走
- 动态生成 pattern：从 _METRIC_UNITS 自动生成，新增指标只改一处
- 财年上下文感知：前向捕获 FY2023/2024/2025 等财年标注
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .data_anchor import _METRIC_UNITS, canonical_key


@dataclass(frozen=True)
class NumericSpan:
    """提取到的数值区间（不可变）。"""
    metric: str          # canonical 指标名
    value: float         # 数值
    unit: str            # 单位
    span: tuple[int, int]  # (start, end) 在原文中的位置
    text: str            # 匹配的原文片段
    fy_context: int | None = None  # 前向财年上下文（FY2023 等）


def _build_metric_pattern() -> str:
    """从 _METRIC_UNITS 动态生成 regex pattern（新增指标只改 _METRIC_UNITS）。"""
    names = sorted(_METRIC_UNITS.keys(), key=len, reverse=True)
    escaped = "|".join(re.escape(n) for n in names)
    return (
        r"(?:(FY\d{4}|20\d{2}年?|去年|上年|前年)\s*)?"
        rf"({escaped})\s*"
        r"[^\d\-]{0,8}(-?\d+\.?\d*)\s*(亿元|亿|万元|万|%)?"
    )


_METRIC_NUM_RE = re.compile(_build_metric_pattern())


def _parse_fy_context(ctx: str | None) -> int | None:
    """从上下文字符串解析财年（FY2023/2024年 等）。"""
    if not ctx:
        return None
    m = re.search(r'(?:FY)?(\d{4})', ctx)
    if m:
        return int(m.group(1))
    return None


class NumericExtractor:
    """统一数值提取器——所有数值提取从此模块走。

    用法：
        extractor = NumericExtractor()
        spans = extractor.extract_spans(content)
        bare_numbers = extractor.extract_bare_numbers(content)
    """

    def __init__(self, pattern: re.Pattern | None = None) -> None:
        self._pattern = pattern or _METRIC_NUM_RE

    def extract_spans(self, content: str) -> list[NumericSpan]:
        """提取所有指标+数值区间（含财年上下文）。"""
        spans: list[NumericSpan] = []
        for m in self._pattern.finditer(content):
            fy_ctx = _parse_fy_context(m.group(1))
            metric = m.group(2)
            try:
                value = float(m.group(3))
            except (TypeError, ValueError):
                continue
            unit = m.group(4) or "亿"
            spans.append(NumericSpan(
                metric=canonical_key(metric),
                value=value,
                unit=unit,
                span=(m.start(), m.end()),
                text=m.group(0),
                fy_context=fy_ctx,
            ))
        return spans

    def extract_bare_numbers(self, content: str) -> list[NumericSpan]:
        """提取未命中锚点的裸数字（用于 bind_bare_numbers）。"""
        return self.extract_spans(content)  # 由调用方比对锚点决定是否"裸"
