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
    """跨章节一致性检查器（v9：实现 CheckerProtocol）"""

    @property
    def name(self) -> str:
        """检查器名称（CheckerProtocol 接口）。"""
        return "CrossChapterConsistency"

    def check(self, chapters: dict[int, str], ctx: object = None) -> object:
        """CheckerProtocol 接口（v9）。返回 CheckResult。"""
        from ..qual_v8.contracts.types import CheckResult
        result = self._check_consistency(chapters)
        violations = tuple(result.issues) if result.issues else ()
        return CheckResult(
            checker_name="CrossChapterConsistency",
            passed=result.passed,
            score=result.score,
            violations=violations,
        )

    def _check_consistency(self, chapters: dict[int, str]) -> ConsistencyResult:
        """原有检查逻辑（由 check() 委托调用）。"""
        return self._check_consistency_impl(chapters)

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
        # 2026-08-22：现金流状态模式精确化——"现金流背离"（正现金流+负利润）和
        # "自由现金流为负"（经营现金流正但 capex 大）不等于"经营现金流为负"。
        # 旧模式 r"现金流.*?为负" 会误匹配"现金流表现背离...ROE为负"等合理描述。
        self.conclusion_patterns = {
            "现金流状态": [
                r"经营.*?现金流.*?首次转正",
                r"经营.*?现金流.*?持续为负",
                r"经营.*?现金流.*?转正",
                r"经营活动.*?现金.*?为负",
                r"现金流量?\s*净额.*?为负",
            ],
            "盈利状态": [
                r"盈利.*?拐点",
                r"持续亏损",
                r"亏损收窄",
            ],
        }

    def _check_consistency_impl(self, chapters: dict[int, str]) -> ConsistencyResult:
        """
        检查跨章节一致性（内部实现，由 check/_check_consistency 委托调用）

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

        2026-08-22 P5 诊断修复：统一使用 DataAnchor.extract_data_spans 提取，
        消除自建 regex 的 3 类假阳性：
        ① 不排除子公司/分部口径限定词（ADVC 已修，此处未同步）→ "子公司总资产31.63亿"
           误与合并口径 1031.63 冲突
        ② "净亏损+11.39" vs "净利润-11.39" 符号翻转→fatal
        ③ _year_before 只看前 150 字符→跨财年误归因
        """
        if self._anchor is None:
            return {}

        data: dict[str, list] = {}

        # 统一提取（含子公司/分部排除、语境过滤、单位归一）
        spans = self._anchor.extract_data_spans(content)

        # 按 canonical 指标分组，每指标每财年取最新值（避免同指标多次出现的冲突）
        seen: dict[str, dict[int | None, float]] = {}  # {metric: {fy: value}}
        for item in spans:
            if item["unit"] == "%":
                continue  # 百分比不参与跨章数值比较
            metric = item["metric_key"]
            if metric.startswith("pct:"):
                continue
            value = item["value"]

            # 财年归因：先看 span 前后的年份标注，再用 DataAnchor
            pos = item["span"][0]
            fy = None
            context_fy = None  # 上下文标注的财年（可能与锚点归因不一致）
            after = content[pos:pos + 30]
            m2 = re.search(r"(?:亿元|亿|万元|万)?[（(]?\s*(20\d{2})\s*年", after)
            if m2:
                context_fy = int(m2.group(1))
            else:
                ctx = content[max(0, pos - 150):pos]
                years = re.findall(r"(?:FY\s*)?(20\d{2})(?:\s*年)?", ctx)
                if years:
                    context_fy = int(years[-1])

            # DataAnchor 归因（最终依据——数值真实来源）
            anchor_fy = None
            try:
                attr = self._anchor.attribute_text_value(metric, value)
                anchor_fy = attr["fiscal_year"]
                # 只在上下文未标注财年时才收入 unattributed_historical
                if attr["is_historical"] and anchor_fy is not None and context_fy is None:
                    self.unattributed_historical.append(
                        f"{metric}={value} 命中 FY{anchor_fy} 锚点但未标注财年"
                    )
            except Exception:
                anchor_fy = None

            # 财年冲突检测：上下文标注与锚点归因不一致 → 以锚点为准
            # （LLM 可能在 2025 年上下文中错误引用了 FY2023 的值）
            if context_fy is not None and anchor_fy is not None and context_fy != anchor_fy:
                fy = anchor_fy  # 以锚点归因为准
            elif context_fy is not None:
                fy = context_fy
            else:
                fy = anchor_fy

            # 每指标每财年只保留最新值（同一 span 后出现的覆盖）
            if metric not in seen:
                seen[metric] = {}
            if fy not in seen[metric]:
                seen[metric][fy] = value

        # 转为旧格式 {metric: [(fy, value), ...]}
        for metric, fy_vals in seen.items():
            data[metric] = [(fy, val) for fy, val in fy_vals.items()]

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

        # 4. 派生指标跨章一致性：净现比（经营现金流/净利润）
        _ratio_patterns = [
            r"净现比[：:]\s*(-?\d+\.?\d*)\s*[%％倍]",
            r"现金流转化率[：:]\s*(-?\d+\.?\d*)\s*[%％倍]",
            r"经营现金流.*?净利润.*?(\d+\.?\d*)\s*倍",
        ]
        _ratio_by_ch: dict[int, dict[int | None, float]] = {}
        for ch_num, content in chapters.items():
            for pat in _ratio_patterns:
                for m in re.finditer(pat, content):
                    try:
                        val = float(m.group(1))
                        if "%" in pat:
                            val = val / 100.0
                        ctx = content[max(0, m.start() - 150):m.start()]
                        years = re.findall(r"(?:FY\s*)?(20\d{2})(?:\s*年)?", ctx)
                        fy = int(years[-1]) if years else None
                        _ratio_by_ch.setdefault(ch_num, {})[fy] = val
                    except (ValueError, IndexError):
                        continue

        _latest = self._anchor.get_latest_fiscal_year() if self._anchor else None
        _ratio_by_fy: dict[int | None, dict[int, float]] = {}
        for ch_num, fy_vals in _ratio_by_ch.items():
            for fy, val in fy_vals.items():
                bucket = fy if fy is not None else _latest
                _ratio_by_fy.setdefault(bucket, {})[ch_num] = val

        for fy, values in _ratio_by_fy.items():
            if len(values) < 2:
                continue
            unique = set(values.values())
            if len(unique) <= 1:
                continue
            ch_list = list(values.keys())
            for i in range(len(ch_list)):
                for j in range(i + 1, len(ch_list)):
                    ch1, ch2 = ch_list[i], ch_list[j]
                    v1, v2 = values[ch1], values[ch2]
                    fy_txt = f"FY{fy}" if fy else "最新财年"
                    if abs(v1 - v2) / max(abs(v1), abs(v2), 1e-9) <= 0.05:
                        continue
                    sev = "fatal" if (v1 > 0) != (v2 > 0) else "important"
                    issues.append(ConsistencyIssue(
                        issue_type="data_conflict",
                        severity=sev,
                        description=f"净现比({fy_txt})在第{ch1}章={v1:.1%}，第{ch2}章={v2:.1%}",
                        chapter1=ch1, line1=0, content1=f"净现比={v1:.1%}",
                        chapter2=ch2, line2=0, content2=f"净现比={v2:.1%}",
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
                # v9：未标注财年的结论（fy=None）不参与跨章冲突判断
                # 三财年报告中，"2024年现金流为负、2025年现金流转正"是合法叙事，
                # 未标注财年的描述（如"现金流量净额为负"）可能是历史引用，
                # 不应默认归入最新财年与新值冲突。
                if fy is None:
                    continue
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
        """判断两个结论是否冲突

        2026-08-22：增加"混合描述豁免"——当两个结论都包含正面关键词时，
        即使其中一个也含负面词（如"转正...但自由现金流仍为负"），不算冲突。
        这类混合描述在三财年报告中常见（改善但仍有不足）。

        2026-08-23：增加"改善性关键词"——"收窄""拐点""减亏"等描述改善趋势的词
        标为正面（不是负面）。"亏损收窄"含"亏损"但本质是改善描述，不应判为负面。
        """
        # 正面关键词（含改善趋势）
        positive_keywords = ["转正", "改善", "增长", "上升", "提升", "突破", "拐点", "收窄", "减亏", "好转"]
        # 负面关键词（纯恶化）
        negative_keywords = ["为负", "下降", "恶化", "持续亏损", "扩大", "加剧"]

        conc1_positive = any(kw in conc1 for kw in positive_keywords)
        conc1_negative = any(kw in conc1 for kw in negative_keywords)

        conc2_positive = any(kw in conc2 for kw in positive_keywords)
        conc2_negative = any(kw in conc2 for kw in negative_keywords)

        # 混合描述豁免：两个结论都含正面词 → 不算冲突（改善+不足并存是合理描述）
        if conc1_positive and conc2_positive:
            return False

        # 一个纯正面一个纯负面则冲突
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
    return checker._check_consistency(chapters)
