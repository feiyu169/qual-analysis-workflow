"""
跨章节一致性检查模块

功能：
1. 检查不同章节中相同数据是否一致
2. 检查不同章节中相同结论是否一致
3. 检查不同章节中相同时间点是否一致

解决批判性审阅发现的问题：
- F1: 经营现金流正负打架
- I1: 总资产口径打架
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyIssue:
    """一致性问题"""
    issue_type: str  # "data_conflict", "conclusion_conflict", "time_conflict"
    severity: str  # "fatal", "important", "suggestion"
    description: str
    chapter1: int
    line1: int
    content1: str
    chapter2: int
    line2: int
    content2: str


@dataclass
class ConsistencyResult:
    """一致性检查结果"""
    passed: bool
    issues: list[ConsistencyIssue] = field(default_factory=list)
    score: float = 100.0


class CrossChapterConsistencyChecker:
    """跨章节一致性检查器"""

    def __init__(self, wind_data: dict | None = None):
        # 财年语义单源：DataAnchor 归因（FiscalSemantics——未标注数字引用按锚点值归因财年，
        # 不再一律视为"最新财年"，架构级消除历史引用误报）
        self._anchor = None
        if wind_data:
            try:
                from ..qual_v8.data_anchor import get_data_anchor
                self._anchor = get_data_anchor(wind_data)
            except Exception:
                self._anchor = None
        # 未标注历史引用警告收集
        self.unattributed_historical: list[str] = []
        # 关键财务指标正则模式
        self.financial_patterns = {
            "经营现金流": [
                r"经营.*?现金流.*?(\d+\.?\d*)\s*亿",
                r"经营.*?现金流.*?(-?\d+\.?\d*)\s*亿",
                r"经营.*?现金流.*?转正",
                r"经营.*?现金流.*?为负",
            ],
            "总资产": [
                r"总资产.*?(\d+\.?\d*)\s*亿",
                r"资产.*?总计.*?(\d+\.?\d*)\s*亿",
            ],
            "净利润": [
                r"净利润.*?(-?\d+\.?\d*)\s*亿",
                r"净亏损.*?(\d+\.?\d*)\s*亿",
            ],
            "营业收入": [
                r"营业收入.*?(\d+\.?\d*)\s*亿",
                r"营收.*?(\d+\.?\d*)\s*亿",
            ],
            "毛利率": [
                r"毛利率.*?(\d+\.?\d*)\s*%",
                r"毛利率.*?(\d+\.?\d*)\s*个百分点",
            ],
        }

        # 关键结论正则模式
        self.conclusion_patterns = {
            "现金流状态": [
                r"现金流.*?首次转正",
                r"现金流.*?持续为负",
                r"现金流.*?转正",
                r"现金流.*?为负",
            ],
            "盈利状态": [
                r"盈利.*?拐点",
                r"持续亏损",
                r"亏损收窄",
            ],
        }

    def check(self, chapters: dict[int, str]) -> ConsistencyResult:
        """
        检查跨章节一致性

        Args:
            chapters: 各章节内容 {chapter_num: content}

        Returns:
            ConsistencyResult
        """
        issues = []

        # 1. 检查财务数据一致性
        financial_issues = self._check_financial_consistency(chapters)
        issues.extend(financial_issues)

        # 2. 检查结论一致性
        conclusion_issues = self._check_conclusion_consistency(chapters)
        issues.extend(conclusion_issues)

        # 3. 检查时间点一致性
        time_issues = self._check_time_consistency(chapters)
        issues.extend(time_issues)

        # 计算评分
        fatal_count = sum(1 for i in issues if i.severity == "fatal")
        important_count = sum(1 for i in issues if i.severity == "important")
        suggestion_count = sum(1 for i in issues if i.severity == "suggestion")

        score = 100.0
        score -= fatal_count * 40
        score -= important_count * 15
        score -= suggestion_count * 5
        score = max(0.0, min(100.0, score))

        passed = fatal_count == 0 and score >= 60.0

        if not passed:
            logger.warning(f"跨章节一致性检查不通过: score={score:.0f}, issues={len(issues)}")

        return ConsistencyResult(
            passed=passed,
            issues=issues,
            score=score,
        )

    def _extract_financial_data(self, content: str, ch_num: int) -> dict[str, list]:
        """从章节内容中提取财务数据（多财年感知：按财年分组）

        三财年报告（FY2023/24/25）中，同一章节会合法引用多个财年的值
        （如营业收入 306.76/408.66/767.20 亿）。旧实现只取第一个匹配，
        导致不同章节"第一个匹配"落在不同财年 → 假冲突（108 项假阳性）。
        现改为提取 {indicator: [(fy, value), ...]}，由调用方按财年对齐比较。
        """
        data: dict[str, list] = {}

        def _year_before(pos: int) -> int | None:
            """数字所属财年：先看数字后紧跟的 '20XX年'（如 "841.63亿元（2023年）"），
            再看数字前 150 字符内最近的 '20XX年'；都没有则用 DataAnchor 归因
            （值命中历史财年锚点 → 该财年；未命中 → None 视为最新财年引用）。"""
            # 数字后紧跟年份（更具体，如 "总资产841.63亿元（2023年）"）
            after = content[pos:pos + 30]
            m2 = re.search(r"(?:亿元|亿|万元|万)?[（(]?\s*(20\d{2})\s*年", after)
            if m2:
                return int(m2.group(1))
            ctx = content[max(0, pos - 150):pos]
            years = re.findall(r"(?:FY\s*)?(20\d{2})(?:\s*年)?", ctx)
            if years:
                return int(years[-1])  # 取最近的（最后一个）年份
            return None

        # 归因：indicator 无年份标注的引用按锚点值定位财年（FiscalSemantics）
        def _attributed_fy(indicator: str, value: float) -> int | None:
            if self._anchor is None:
                return None
            try:
                attr = self._anchor.attribute_text_value(indicator, value)
                if attr["is_historical"]:
                    # 历史引用未标注 → 记 warning（写作遵从度提示，供生成时校验升级）
                    self.unattributed_historical.append(
                        f"{indicator}={value} 命中 FY{attr['fiscal_year']} 锚点但未标注财年"
                    )
                    return attr["fiscal_year"]
                return attr["fiscal_year"]
            except Exception:
                return None

        for indicator, patterns in self.financial_patterns.items():
            for pattern in patterns:
                # 只处理带数值的模式（跳过"转正/为负"等结论模式）
                if r"(\d" not in pattern and r"(-?\d" not in pattern:
                    continue
                try:
                    for m in re.finditer(pattern, content):
                        try:
                            value = float(m.group(1))
                        except (ValueError, IndexError):
                            continue
                        fy = _year_before(m.start())
                        if fy is None:
                            fy = _attributed_fy(indicator, value)
                        if indicator not in data:
                            data[indicator] = []
                        data[indicator].append((fy, value))
                except Exception:  # noqa: S112 —— 单值解析失败跳过（正则边界）
                    continue
                # 一个 indicator 取全量匹配后不再重复模式（同 indicator 多模式仅兜底）
                if data.get(indicator):
                    break

        return data

    def _check_financial_consistency(self, chapters: dict[int, str]) -> list[ConsistencyIssue]:
        """检查财务数据一致性（多财年感知：仅比较同财年的跨章引用）"""
        issues = []

        # 提取各章节中的财务数据
        chapter_data = {}
        for ch_num, content in chapters.items():
            chapter_data[ch_num] = self._extract_financial_data(content, ch_num)

        # 比对相同指标+相同财年 在不同章节中的值
        # chapter_data = {ch_num: {indicator: [(fy, value), ...]}}
        # 先收集所有指标
        all_indicators = set()
        for data in chapter_data.values():
            all_indicators.update(data.keys())

        for indicator in all_indicators:
            # 按财年聚合：{fy: {ch: value}}
            # FiscalSemantics：未归因（None=默认最新语境）与最新财年合并——未标注引用视为当期，
            # 与命中最新锚点的引用同桶比较（否则 999(未命中) 与 1031.63(FY2025) 不碰，真实冲突漏报）
            _latest = self._anchor.get_latest_fiscal_year() if self._anchor else None
            by_fy: dict[int | None, dict[int, float]] = {}
            for ch_num, data in chapter_data.items():
                points = data.get(indicator) or []
                for fy, value in points:
                    bucket = fy if fy is not None else _latest
                    by_fy.setdefault(bucket, {})[ch_num] = value

            for fy, values in by_fy.items():
                if len(values) < 2:
                    continue
                unique_values = set(values.values())
                if len(unique_values) <= 1:
                    continue
                ch_list = list(values.keys())
                for i in range(len(ch_list)):
                    for j in range(i + 1, len(ch_list)):
                        ch1, ch2 = ch_list[i], ch_list[j]
                        val1, val2 = values[ch1], values[ch2]
                        fy_txt = f"FY{fy}" if fy else "最新财年"

                        # 1% 容差内（767.20 vs 767 四舍五入写法）→ 不算冲突，跳过
                        if abs(val1 - val2) / max(abs(val1), abs(val2), 1e-9) <= 0.01:
                            continue

                        # 判断严重程度
                        if indicator in ("经营现金流", "净利润"):
                            # 符号冲突（正vs负）是致命问题
                            if (val1 > 0 and val2 < 0) or (val1 < 0 and val2 > 0):
                                severity = "fatal"
                            else:
                                severity = "important"
                        else:
                            # 数值差异超过20%是重要问题
                            if abs(val1 - val2) / max(abs(val1), abs(val2)) > 0.2:
                                severity = "important"
                            else:
                                severity = "suggestion"

                        issues.append(ConsistencyIssue(
                            issue_type="data_conflict",
                            severity=severity,
                            description=f"{indicator}({fy_txt})在第{ch1}章={val1}亿，第{ch2}章={val2}亿",
                            chapter1=ch1,
                            line1=0,
                            content1=f"{indicator}={val1}亿",
                            chapter2=ch2,
                            line2=0,
                            content2=f"{indicator}={val2}亿",
                        ))

        return issues

    def _check_conclusion_consistency(self, chapters: dict[int, str]) -> list[ConsistencyIssue]:
        """检查结论一致性（多财年感知：仅比较同财年的结论）

        修复：三财年报告中"2024年现金流为负、2025年现金流转正"是合法叙事，
        旧实现按章节提取第一条结论跨章比较 → 大量假冲突。
        现提取 {topic: [(fy, conclusion), ...]}，仅同财年结论做正负冲突判断。
        """
        issues = []

        # 提取各章节中的结论（按财年）
        chapter_conclusions = {}
        for ch_num, content in chapters.items():
            chapter_conclusions[ch_num] = self._extract_conclusions(content, ch_num)

        # 比对相同主题+相同财年 在不同章节中的结论
        all_topics = set()
        for data in chapter_conclusions.values():
            all_topics.update(data.keys())

        for topic in all_topics:
            # 按财年聚合：{fy: {ch: conclusion}}
            by_fy: dict[int | None, dict[int, str]] = {}
            for ch_num, data in chapter_conclusions.items():
                points = data.get(topic) or []
                for fy, conc in points:
                    by_fy.setdefault(fy, {})[ch_num] = conc

            for fy, conclusions in by_fy.items():
                if len(conclusions) < 2:
                    continue
                ch_list = list(conclusions.keys())
                for i in range(len(ch_list)):
                    for j in range(i + 1, len(ch_list)):
                        ch1, ch2 = ch_list[i], ch_list[j]
                        conc1, conc2 = conclusions[ch1], conclusions[ch2]

                        # 判断是否冲突
                        if self._is_conclusion_conflict(conc1, conc2):
                            fy_txt = f"FY{fy}" if fy else "最新财年"
                            issues.append(ConsistencyIssue(
                                issue_type="conclusion_conflict",
                                severity="fatal",
                                description=f"{topic}({fy_txt})在第{ch1}章='{conc1}'，第{ch2}章='{conc2}'",
                                chapter1=ch1,
                                line1=0,
                                content1=conc1,
                                chapter2=ch2,
                                line2=0,
                                content2=conc2,
                            ))

        return issues

    def _check_time_consistency(self, chapters: dict[int, str]) -> list[ConsistencyIssue]:
        """检查时间点一致性"""
        issues = []

        # 提取各章节中的时间点
        chapter_times = {}
        for ch_num, content in chapters.items():
            chapter_times[ch_num] = self._extract_time_points(content, ch_num)

        # 比对相同时间点在不同章节中的引用
        time_references = {}
        for ch_num, times in chapter_times.items():
            for time_ref in times:
                if time_ref not in time_references:
                    time_references[time_ref] = []
                time_references[time_ref].append(ch_num)

        # 检查同一时间点在不同章节中的数据是否一致
        for time_ref, chapters_using in time_references.items():
            if len(chapters_using) >= 2:
                # 提取该时间点在各章节中的数据
                time_data = {}
                for ch_num in chapters_using:
                    content = chapters[ch_num]
                    data = self._extract_data_for_time(content, time_ref)
                    if data:
                        time_data[ch_num] = data

                # 比对数据
                if len(time_data) >= 2:
                    for indicator in ["总资产", "净利润", "营业收入"]:
                        values = {}
                        for ch_num, data in time_data.items():
                            if indicator in data:
                                values[ch_num] = data[indicator]

                        if len(values) >= 2:
                            ch_list = list(values.keys())
                            for i in range(len(ch_list)):
                                for j in range(i + 1, len(ch_list)):
                                    ch1, ch2 = ch_list[i], ch_list[j]
                                    val1, val2 = values[ch1], values[ch2]
                                    # 1% 容差（767.20 vs 767 四舍五入写法不算冲突）
                                    if abs(val1 - val2) / max(abs(val1), abs(val2), 1e-9) <= 0.01:
                                        continue
                                    issues.append(ConsistencyIssue(
                                        issue_type="time_conflict",
                                        severity="important",
                                        description=f"{time_ref}的{indicator}在第{ch1}章={val1}亿，第{ch2}章={val2}亿",
                                        chapter1=ch1,
                                        line1=0,
                                        content1=f"{indicator}={val1}亿",
                                        chapter2=ch2,
                                        line2=0,
                                        content2=f"{indicator}={val2}亿",
                                    ))

        return issues

    def _extract_conclusions(self, content: str, ch_num: int) -> dict[str, list]:
        """从章节内容中提取结论（按财年分组）{topic: [(fy, conclusion), ...]}"""
        conclusions: dict[str, list] = {}

        def _year_before_conclusion(pos: int) -> int | None:
            """结论匹配位置前最近 '20XX年'（150 字符内），无则 None"""
            ctx = content[max(0, pos - 150):pos]
            years = re.findall(r"(20\d{2})\s*年", ctx)
            return int(years[-1]) if years else None

        for topic, patterns in self.conclusion_patterns.items():
            for pattern in patterns:
                for m in re.finditer(pattern, content):
                    fy = _year_before_conclusion(m.start())
                    if topic not in conclusions:
                        conclusions[topic] = []
                    conclusions[topic].append((fy, m.group(0)))
        return conclusions

    def _extract_time_points(self, content: str, ch_num: int) -> list[str]:
        """从章节内容中提取时间点"""
        time_points = []

        # 匹配年份
        year_pattern = r"(20\d{2})\s*年"
        years = re.findall(year_pattern, content)
        time_points.extend([f"{y}年" for y in years])

        # 匹配季度
        quarter_pattern = r"(20\d{2})\s*年?\s*(Q[1-4]|[上下]半年|[一二三四]季度)"
        quarters = re.findall(quarter_pattern, content)
        time_points.extend([f"{y}{q}" for y, q in quarters])

        return list(set(time_points))

    def _extract_data_for_time(self, content: str, time_ref: str) -> dict[str, float]:
        """提取特定时间点附近各指标的数据 {indicator: value}

        修复：旧实现只取第一个匹配且一律存为"净利润"键 → 指标张冠李戴产生假冲突。
        现按指标分别匹配 time_ref 之后最近的一个数值。
        """
        data = {}
        time_pattern = re.escape(time_ref)
        for indicator, patterns in self.financial_patterns.items():
            for pattern in patterns:
                # 只处理带数值的模式（跳过"转正/为负"等结论模式）
                if r"(\d" not in pattern and r"(-?\d" not in pattern:
                    continue
                # 时间点 + 指标 + 数值
                m = re.search(
                    time_pattern + r".{0,80}?" + pattern,
                    content,
                )
                if m and m.groups():
                    try:
                        value = float(m.group(1))
                        # 若数值后有显式年份标签且与 time_ref 不同 → 跳过（"2025年…总资产841.63亿元（2023年）"）
                        after = content[m.end():m.end() + 20]
                        trailing = re.search(r"(20\d{2})\s*年", after)
                        if trailing and trailing.group(1) != time_ref[:4]:
                            continue
                        data[indicator] = value
                        break
                    except (ValueError, IndexError):
                        continue
        return data

    def _is_conclusion_conflict(self, conc1: str, conc2: str) -> bool:
        """判断两个结论是否冲突"""
        # 正面关键词
        positive_keywords = ["转正", "改善", "增长", "上升", "提升"]
        # 负面关键词
        negative_keywords = ["为负", "下降", "恶化", "亏损", "减少"]

        conc1_positive = any(kw in conc1 for kw in positive_keywords)
        conc1_negative = any(kw in conc1 for kw in negative_keywords)

        conc2_positive = any(kw in conc2 for kw in positive_keywords)
        conc2_negative = any(kw in conc2 for kw in negative_keywords)

        # 一个正面一个负面则冲突
        return (conc1_positive and conc2_negative) or (conc1_negative and conc2_positive)


def check_cross_chapter_consistency(chapters: dict[int, str],
                                    wind_data: dict | None = None) -> ConsistencyResult:
    """
    检查跨章节一致性（入口函数）

    Args:
        chapters: 各章节内容 {chapter_num: content}
        wind_data: Wind 数据（FiscalSemantics 归因——未标注引用按锚点值定位财年；None 则旧行为）

    Returns:
        ConsistencyResult
    """
    checker = CrossChapterConsistencyChecker(wind_data=wind_data)
    return checker.check(chapters)
