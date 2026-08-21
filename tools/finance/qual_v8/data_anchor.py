"""
数据锚点机制（修复版 2026-08-18）

用于跨章节数据同步，确保各章节引用的数据一致。

修复项：
- B1: _extract_data 死代码 → 真实提取（指标名+数字+单位）写入字典
- B2: init_from_wind_data 键契约 → canonical 键 + 别名表（与 assemble_wind_data 输出对齐）
- B3: DataPoint 增加 fiscal_year 维度；锚点可存 3 年列表
- B4: validate/fix 财年感知：仅校验报告中出现且锚点有同财年的数字
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# canonical 键别名表（Wind 原始键 / 旧检查器期望键 → canonical 键）
# 与 tools/finance/assemble_wind_data.py 的 FIELD_MAP 输出对齐
CANONICAL_ALIASES: dict[str, str] = {
    "年营业收入": "营业收入",
    "营业收入": "营业收入",
    "营业总收入": "营业收入",
    "年营业总收入": "营业收入",
    "年净利润": "归母净利润",
    "净利润": "净利润",
    "归母净利润": "归母净利润",
    "年归母净利润": "归母净利润",
    "年营业利润": "营业利润",
    "营业利润": "营业利润",
    "年资产总计": "总资产",
    "总资产": "总资产",
    "年负债合计": "年负债合计",
    "负债合计": "年负债合计",
    "年所有者权益合计": "年所有者权益合计",
    "年归属母公司股东权益": "年所有者权益合计",
    "归母净资产": "归母净资产",
    "年归母净资产": "归母净资产",
    "经营活动现金流量净额": "经营活动现金流量净额",
    "经营活动产生的现金流量净额": "经营活动现金流量净额",
    "年经营活动现金流量净额": "经营活动现金流量净额",
    "过去三年每年经营活动产生的现金流量净额": "经营活动现金流量净额",
    "购建固定资产、无形资产和其他长期资产支付的现金": "购建固定资产、无形资产和其他长期资产支付的现金",
    "年购建固定资产无形资产和其他长期资产支付的现金": "购建固定资产、无形资产和其他长期资产支付的现金",
}


def canonical_key(key: str) -> str:
    """任意键 → canonical 键（找不到则原样返回）"""
    return CANONICAL_ALIASES.get(key, key)


# 财务指标 → 单位
_METRIC_UNITS: dict[str, str] = {
    "营业收入": "亿元", "净利润": "亿元", "归母净利润": "亿元", "营业利润": "亿元",
    "总资产": "亿元", "年负债合计": "亿元", "年所有者权益合计": "亿元", "归母净资产": "亿元",
    "经营活动现金流量净额": "亿元", "购建固定资产、无形资产和其他长期资产支付的现金": "亿元",
}


@dataclass
class DataPoint:
    """数据点（含财年维度）"""
    key: str
    value: float
    unit: str
    source: str
    timestamp: str
    fiscal_year: int | None = None  # B3: 财年维度


class DataAnchor:
    """
    数据锚点（唯一数据源）

    在Gate 2提取的数据作为唯一数据源
    在Gate 4检查各章节引用的数据是否与锚点一致
    当发现数据不一致时，使用锚点数据替换
    """

    def __init__(self):
        self.anchors: dict[str, list[DataPoint]] = {}  # key -> 按财年排列的锚点列表
        self._init_default_anchors()

    def _init_default_anchors(self):
        """初始化默认锚点（空；由 init_from_wind_data 填充）"""

    def set_anchor(self, key: str, value: float, unit: str = "亿元",
                   source: str = "Wind", fiscal_year: int | None = None):
        """设置数据锚点（同 key 多财年追加）"""
        k = canonical_key(key)
        self.anchors.setdefault(k, [])
        # 同财年覆盖，不同财年追加
        for i, dp in enumerate(self.anchors[k]):
            if dp.fiscal_year == fiscal_year:
                self.anchors[k][i] = DataPoint(
                    key=k, value=value, unit=unit, source=source,
                    timestamp=datetime.now().isoformat(), fiscal_year=fiscal_year,  # noqa: DTZ005
                )
                logger.info(f"[DataAnchor] 覆盖锚点: {k} FY{fiscal_year}={value}{unit} ({source})")
                return
        self.anchors[k].append(DataPoint(
            key=k, value=value, unit=unit, source=source,
            timestamp=datetime.now().isoformat(), fiscal_year=fiscal_year,  # noqa: DTZ005
        ))
        logger.info(f"[DataAnchor] 设置锚点: {k} FY{fiscal_year}={value}{unit} ({source})")

    def get_anchor(self, key: str, fiscal_year: int | None = None) -> float | None:
        """获取数据锚点（指定财年；未指定取最新）"""
        k = canonical_key(key)
        if k not in self.anchors:
            return None
        points = self.anchors[k]
        if fiscal_year is not None:
            for dp in points:
                if dp.fiscal_year == fiscal_year:
                    return dp.value
            return None
        return points[-1].value if points else None

    def get_all_anchors(self) -> dict[str, list[DataPoint]]:
        """获取所有锚点"""
        return {k: list(v) for k, v in self.anchors.items()}

    def get_latest_fiscal_year(self) -> int | None:
        """获取最新财年（所有锚点中最大的 fiscal_year）"""
        fys = [dp.fiscal_year for pts in self.anchors.values() for dp in pts if dp.fiscal_year]
        return max(fys) if fys else None

    def validate_chapter(self, chapter_num: int, chapter_content: str,
                         fiscal_year: int | None = None) -> list[str]:
        """验证章节数据是否与锚点一致（财年感知）"""
        errors = []
        chapter_data = self._extract_data(chapter_content)
        for metric, value in chapter_data.items():
            k = canonical_key(metric)
            anchor_value = self.get_anchor(k, fiscal_year=fiscal_year)
            if anchor_value is None:
                # 无同财年锚点：若该指标有锚点但财年不同，提示标注财年；否则跳过（运营数据无锚点）
                if self.get_anchor(k) is not None and fiscal_year is None:
                    errors.append(f"第{chapter_num}章{metric}={value}，锚点财年不明确，请标注FY")
                continue
            if abs(value - anchor_value) / max(abs(anchor_value), 1e-9) > 0.01:  # 1%误差
                errors.append(f"第{chapter_num}章{metric}={value}，锚点={anchor_value}（FY{fiscal_year}）")
        return errors

    def validate_chapter_any_fy(self, chapter_num: int, chapter_content: str) -> list[str]:
        """验证章节数据：数值命中**任一财年**锚点即通过（多财年章节兼容）。

        修复场景：ch6/ch7 等章节合法引用 FY2024 历史值（如总资产 827.06 亿），
        若只对最新财年校验会把合法历史值误判为错误、导致 patch 修复被回滚。
        此处只拦截**不匹配任何财年**的数值（模板残留/幻觉数字）。
        """
        errors = []
        chapter_data = self._extract_data(chapter_content)
        for metric, value in chapter_data.items():
            k = canonical_key(metric)
            points = self.anchors.get(k) or []
            if not points:
                continue  # 运营数据无锚点
            # 命中任一财年（±1%）即通过
            if any(
                dp.fiscal_year is not None
                and abs(value - dp.value) / max(abs(dp.value), 1e-9) <= 0.01
                for dp in points
            ):
                continue
            # 不匹配任何财年 → 报错（附锚点列表供参考）
            latest = points[-1]
            fys = sorted({dp.fiscal_year for dp in points if dp.fiscal_year is not None})
            fy_txt = ",".join(f"FY{fy}" for fy in fys) if fys else "财年未知"
            errors.append(
                f"第{chapter_num}章{metric}={value}，不匹配任一财年锚点"
                f"（{fy_txt}，最新FY{latest.fiscal_year}={latest.value:.2f}）"
            )
        return errors

    def fix_chapter(self, chapter_num: int, chapter_content: str,
                    fiscal_year: int | None = None) -> tuple[str, list[str]]:
        """修复章节数据（替换为锚点数据）"""
        fixes = []
        chapter_data = self._extract_data(chapter_content)
        for metric, value in chapter_data.items():
            k = canonical_key(metric)
            anchor_value = self.get_anchor(k, fiscal_year=fiscal_year)
            if anchor_value is not None and abs(value - anchor_value) / max(abs(anchor_value), 1e-9) > 0.01:
                old_text = _find_number_context(chapter_content, metric, value)
                if old_text:
                    chapter_content = chapter_content.replace(old_text, old_text.replace(str(value), f"{anchor_value:.2f}"), 1)
                    fixes.append(f"{metric}: {value} -> {anchor_value}")
        return chapter_content, fixes

    def _extract_data(self, content: str) -> dict[str, float]:
        """从内容中提取数据（修复死代码：真实写入字典）

        识别模式："营业收入80.0亿元" / "归母净利润 -7.76 亿元" / "净利润为11.4亿元" 等。
        """
        data: dict[str, float] = {}
        if not content:
            return data

        # 指标关键词 → canonical 键（按长度降序，避免"净利润"先匹配"归母净利润"的子串）
        metric_patterns = sorted(_METRIC_UNITS.keys(), key=len, reverse=True)

        # 通用模式：<指标词>非数字{0,15}<可选负号><数字><可选空格><单位>
        # 0,15 容纳"累计减少/较上年同期增长"等变化语境（R7-① 排除变化量需看到这些词）
        for metric in metric_patterns:
            pattern = re.compile(
                re.escape(metric) + r"[^\d\-]{0,15}(-?\d+\.?\d*)\s*(亿元|亿|万元|万|%)"
            )
            for m in pattern.finditer(content):
                # R7-①：排除"变化量/修饰量"语境，保留"增长至/降至 X 亿元"最终值
                match_text = m.group(0)
                # 变化量/修饰量排除：变化词后直接跟数字（非"至/到/达"）或含"含/减值"等
                # 例："下降2.5亿元"→排除；"增长至78.66亿元"→保留（至豁免）；"含商誉减值约5.4亿元"→排除
                if re.search(
                    r"(?:累计|同比|环比|减少|增加|下降|上升|收缩|增长|降低|提高|缩小|扩大|变化|变动|跌幅|涨幅|下滑|回落|回升)"
                    r"(?!\s*(?:至|到|达))\s*\d",
                    match_text,
                ) or re.search(r"(含|其中|减值|拖累|影响|涉及|主要系|主要受).{0,8}?\d", match_text):
                    continue
                # 匹配串后修饰（"降至150亿元以下"、"约5.4亿元左右"）：以下/以上/左右 在单位后
                ctx_after = content[m.end():m.end() + 6]
                if re.search(r"(以下|以上|左右|不足|超过|不低于|不超过|区间|范围|至\s*$)", ctx_after):
                    continue
                # 匹配串内以"约/约"结尾（"约5.4亿元"——"约"在数字前，已在 match_text 内检查）
                if re.search(r"(约|约\s*)\d", match_text) and re.search(r"(以下|以上|左右)$", match_text):
                    continue
                ctx_near = content[max(0, m.start() - 6):m.start()]
                if re.search(r"(减少|增加|下降|上升|收缩|增长|降低|提高|缩小|扩大|变化|变动|跌幅|涨幅|下滑|回落|回升)$", ctx_near):
                    continue
                try:
                    value = float(m.group(1))
                    unit = m.group(2)
                    if unit in ("万元", "万"):
                        value = value / 10000.0  # 统一为亿元
                    elif unit == "%":
                        continue  # 百分比另行处理（不入财务锚点）
                    k = canonical_key(metric)
                    data[k] = value  # 同指标后出现的覆盖（简单策略）
                except ValueError:
                    continue

        # 百分比指标（毛利率等）
        pct_pattern = re.compile(r"(毛利率|净利率|营业利润率)[^\d\-]{0,8}(-?\d+\.?\d*)\s*%")
        for m in pct_pattern.finditer(content):
            try:
                data[f"{m.group(1)}_pct"] = float(m.group(2))
            except ValueError:
                continue

        return data

    def init_from_wind_data(self, wind_data: dict[str, Any]):
        """从Wind数据初始化锚点（修复键契约：canonical 键 + 3年列表 + 财年标签）"""
        if not wind_data:
            return

        year_labels = (wind_data.get("_year_labels") or {}).get("财年") or [None, None, None]

        # 利润表
        income = wind_data.get("income", {})
        _init_series(self, income, year_labels, [
            ("营业收入", "亿元"), ("净利润", "亿元"), ("归母净利润", "亿元"), ("营业利润", "亿元"),
        ])

        # 资产负债表
        balance = wind_data.get("balance", {})
        _init_series(self, balance, year_labels, [
            ("总资产", "亿元"), ("年负债合计", "亿元"), ("年所有者权益合计", "亿元"), ("归母净资产", "亿元"),
        ])

        # 现金流量表
        cashflow = wind_data.get("cashflow", {})
        _init_series(self, cashflow, year_labels, [
            ("经营活动现金流量净额", "亿元"),
            ("购建固定资产、无形资产和其他长期资产支付的现金", "亿元"),
        ])

        logger.info(f"[DataAnchor] 从Wind数据初始化了{len(self.anchors)}组锚点")


def _init_series(anchor: DataAnchor, table: dict[str, Any], year_labels: list[Any],
                 specs: list[tuple[str, str]]):
    """从某张表按 canonical 键初始化多财年锚点"""
    for canonical, unit in specs:
        # 优先 canonical 键；否则在别名表中找
        values = None
        if canonical in table:
            values = table[canonical]
        else:
            for raw, c in CANONICAL_ALIASES.items():
                if c == canonical and raw in table:
                    values = table[raw]
                    break
        if isinstance(values, list) and values:
            for i, v in enumerate(values):
                if v is None:
                    continue
                fy = year_labels[i] if i < len(year_labels) else None
                try:
                    anchor.set_anchor(canonical, float(v), unit, "Wind", fiscal_year=fy)
                except (TypeError, ValueError):
                    continue


def _find_number_context(content: str, metric: str, value: float) -> str | None:
    """在内容中找到包含 指标+数值 的最小片段，用于精确替换"""
    # 找指标第一次出现的位置，取其后 30 字符
    idx = content.find(metric)
    if idx == -1:
        return None
    snippet = content[idx:idx + 40]
    # 若 snippet 不含该数值（可能是别的数值），返回 None 避免错替
    return snippet if str(value) in snippet else None


class CrossChapterValidator:
    """跨章节数据验证器"""

    def __init__(self, data_anchor: DataAnchor):
        self.data_anchor = data_anchor

    def validate_all_chapters(self, chapters: dict[int, str]) -> dict[str, Any]:
        """验证所有章节的数据一致性（多财年兼容）

        用 validate_chapter_any_fy：数值命中任一财年锚点即通过，
        避免把合法引用的历史财年值（如 ch6/ch7 的 FY2024 总资产 827.06 亿）误判为错误；
        只拦截不匹配任何财年的数字（模板残留/幻觉）。
        """
        all_errors = []
        for chapter_num, content in chapters.items():
            errors = self.data_anchor.validate_chapter_any_fy(chapter_num, content)
            if errors:
                all_errors.extend([f"第{chapter_num}章: {e}" for e in errors])

        return {
            "passed": len(all_errors) == 0,
            "errors": all_errors,
            "error_count": len(all_errors),
        }

    def fix_all_chapters(self, chapters: dict[int, str]) -> tuple[dict[int, str], list[str]]:
        """修复所有章节的数据"""
        all_fixes = []
        fixed_chapters = {}
        latest_fy = self.data_anchor.get_latest_fiscal_year()

        for chapter_num, content in chapters.items():
            fixed_content, fixes = self.data_anchor.fix_chapter(chapter_num, content, fiscal_year=latest_fy)
            fixed_chapters[chapter_num] = fixed_content
            if fixes:
                all_fixes.extend([f"第{chapter_num}章: {fix}" for fix in fixes])

        return fixed_chapters, all_fixes


# ====================================================================
# C5-3：锚点单例工厂（DataAnchor 只读约束——10+ 调用点共享一次构建）
# ====================================================================

_anchor_cache: dict[str, "DataAnchor"] = {}


def get_data_anchor(wind_data: dict[str, Any]) -> "DataAnchor":
    """C5-3：按 wind_data 内容缓存 DataAnchor（init 后只读，10+ 审查环节共享一次构建）。

    用法（替代重复的 `DataAnchor() + init_from_wind_data`）：
        from ..data_anchor import get_data_anchor
        anchor = get_data_anchor(wind_data)
    """
    import json as _json

    key = _json.dumps(wind_data, sort_keys=True, ensure_ascii=False, default=str)
    cached = _anchor_cache.get(key)
    if cached is None:
        cached = DataAnchor()
        cached.init_from_wind_data(wind_data)
        _anchor_cache[key] = cached
    return cached
