"""
日期锚点检查模块

功能：
1. 检查报告中日期引用的一致性
2. 检查数据来源的时点是否一致
3. 检查"当前"、"最新"等模糊时间词的使用

解决批判性审阅发现的问题：
- I5: 日期锚点混乱
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DateAnchorIssue:
    """日期锚点问题"""
    issue_type: str  # "anchor_conflict", "ambiguous_date", "future_reference"
    severity: str  # "fatal", "important", "suggestion"
    description: str
    chapter: int
    line: int
    date1: str
    date2: str


@dataclass
class DateAnchorResult:
    """日期锚点检查结果"""
    passed: bool
    issues: List[DateAnchorIssue] = field(default_factory=list)
    score: float = 100.0
    base_date: Optional[str] = None  # 基准日期


class DateAnchorChecker:
    """日期锚点检查器"""
    
    def __init__(self):
        # 日期格式模式
        self.date_patterns = {
            "年月日": [
                r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
                r"(20\d{2})-(\d{2})-(\d{2})",
                r"(20\d{2})/(\d{2})/(\d{2})",
            ],
            "年月": [
                r"(20\d{2})\s*年\s*(\d{1,2})\s*月",
                r"(20\d{2})-(\d{2})",
                r"(20\d{2})/(\d{2})",
            ],
            "年末/季末": [
                r"(20\d{2})\s*年\s*末",
                r"(20\d{2})\s*年?\s*(Q[1-4]|[上下]半年|[一二三四]季度)\s*末?",
            ],
            "模糊时间": [
                r"当前",
                r"最新",
                r"截至.*?(20\d{2})",
                r"(20\d{2})\s*年\s*报",
            ],
        }
        
        # 未来时间引用模式
        self.future_patterns = [
            r"(20\d{2})\s*年\s*(Q[1-4]|[一二三四]季度)",
            r"(20\d{2})\s*年\s*三季报",
            r"(20\d{2})\s*年\s*年报",
        ]
    
    def check(
        self,
        chapters: Dict[int, str],
        report_date: Optional[str] = None,
    ) -> DateAnchorResult:
        """
        检查日期锚点一致性
        
        Args:
            chapters: 各章节内容 {chapter_num: content}
            report_date: 报告日期（用于判断未来引用）
        
        Returns:
            DateAnchorResult
        """
        issues = []
        
        # 1. 提取所有日期引用
        all_dates = self._extract_all_dates(chapters)
        
        # 2. 确定基准日期
        base_date = self._determine_base_date(all_dates, report_date)
        
        # 3. 检查日期锚点冲突
        anchor_issues = self._check_anchor_conflicts(chapters, all_dates)
        issues.extend(anchor_issues)
        
        # 4. 检查模糊时间词
        ambiguous_issues = self._check_ambiguous_dates(chapters)
        issues.extend(ambiguous_issues)
        
        # 5. 检查未来时间引用
        future_issues = self._check_future_references(chapters, base_date)
        issues.extend(future_issues)
        
        # 6. 检查数据来源时点
        source_issues = self._check_source_timing(chapters)
        issues.extend(source_issues)
        
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
            logger.warning(f"日期锚点检查不通过: score={score:.0f}, issues={len(issues)}")
        
        return DateAnchorResult(
            passed=passed,
            issues=issues,
            score=score,
            base_date=base_date,
        )
    
    def _extract_all_dates(self, chapters: Dict[int, str]) -> Dict[int, List[str]]:
        """提取所有日期引用"""
        all_dates = {}
        
        for ch_num, content in chapters.items():
            dates = []
            
            # 提取各种格式的日期
            for date_type, patterns in self.date_patterns.items():
                for pattern in patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        if isinstance(match, tuple):
                            # 组合日期部分
                            date_str = "-".join(match)
                        else:
                            date_str = match
                        dates.append(date_str)
            
            all_dates[ch_num] = list(set(dates))
        
        return all_dates
    
    def _determine_base_date(
        self,
        all_dates: Dict[int, List[str]],
        report_date: Optional[str],
    ) -> str:
        """确定基准日期"""
        if report_date:
            return report_date
        
        # 从所有日期中找最频繁的年份
        year_counts = {}
        for ch_num, dates in all_dates.items():
            for date in dates:
                year_match = re.search(r"(20\d{2})", date)
                if year_match:
                    year = year_match.group(1)
                    year_counts[year] = year_counts.get(year, 0) + 1
        
        if year_counts:
            # 返回最频繁的年份
            return max(year_counts.items(), key=lambda x: x[1])[0]
        
        return "2024"  # 默认
    
    def _check_anchor_conflicts(
        self,
        chapters: Dict[int, str],
        all_dates: Dict[int, List[str]],
    ) -> List[DateAnchorIssue]:
        """检查日期锚点冲突（多财年报告兼容）

        三财年报告（FY2023/24/25）中不同章节合法聚焦不同财年
        （ch1 主打最新财年、ch6 引用历史财年）——章节间年份不同不是冲突。
        真正的冲突是：某章以**历史财年**为主要引用且**完全未引用最新财年**
        （即 R6 的 "ch5 锚 FY2024 而应锚 FY2025" 问题）。

        基准财年取所有章节中最新的年份（= Wind 最新财年）。
        """
        issues = []

        # 基准 = 全局最新年份
        all_years = set()
        for ch_num, dates in all_dates.items():
            for date in dates:
                m = re.search(r"(20\d{2})", date)
                if m:
                    all_years.add(int(m.group(1)))
        if not all_years:
            return issues
        base_year = max(all_years)

        # 每章主引用年份 + 是否引用过基准年份
        for ch_num, dates in all_dates.items():
            if not dates:
                continue
            year_counts = {}
            for date in dates:
                m = re.search(r"(20\d{2})", date)
                if m:
                    y = int(m.group(1))
                    year_counts[y] = year_counts.get(y, 0) + 1
            if not year_counts:
                continue
            primary_year = max(year_counts.items(), key=lambda x: x[1])[0]
            has_base = base_year in year_counts
            # 主引用是历史年份且从未引用最新财年 → 锚点错位（真问题）
            if primary_year < base_year and not has_base:
                line = self._find_year_line(chapters[ch_num], str(primary_year))
                issues.append(DateAnchorIssue(
                    issue_type="anchor_conflict",
                    severity="important",
                    description=f"第{ch_num}章主要引用{primary_year}年数据但未引用最新财年{base_year}年，"
                                f"应以{base_year}年为当期（历史年份仅作对比）",
                    chapter=ch_num,
                    line=line,
                    date1=f"{primary_year}年",
                    date2=f"{base_year}年",
                ))

        return issues
    
    def _check_ambiguous_dates(self, chapters: Dict[int, str]) -> List[DateAnchorIssue]:
        """检查模糊时间词"""
        issues = []
        
        ambiguous_patterns = [
            (r"当前", "当前"),
            (r"最新", "最新"),
            (r"近期", "近期"),
            (r"目前", "目前"),
        ]
        
        for ch_num, content in chapters.items():
            for pattern, keyword in ambiguous_patterns:
                matches = list(re.finditer(pattern, content))
                for match in matches:
                    # 检查上下文是否有具体日期
                    start = max(0, match.start() - 50)
                    end = min(len(content), match.end() + 50)
                    context = content[start:end]
                    
                    # 如果上下文没有具体日期，报告问题
                    has_specific_date = bool(re.search(r"20\d{2}\s*年", context))
                    
                    if not has_specific_date:
                        line = content[:match.start()].count("\n") + 1
                        issues.append(DateAnchorIssue(
                            issue_type="ambiguous_date",
                            severity="suggestion",
                            description=f"第{ch_num}章使用模糊时间词'{keyword}'，未指定具体日期",
                            chapter=ch_num,
                            line=line,
                            date1=keyword,
                            date2="未指定",
                        ))
        
        return issues
    
    def _check_future_references(
        self,
        chapters: Dict[int, str],
        base_date: str,
    ) -> List[DateAnchorIssue]:
        """检查未来时间引用"""
        issues = []
        
        # 确定基准年份
        base_year_match = re.search(r"(20\d{2})", base_date)
        if not base_year_match:
            return issues
        
        base_year = int(base_year_match.group(1))
        
        for ch_num, content in chapters.items():
            # 检查是否引用了未来年份的数据
            for pattern in self.future_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        year_str = match[0]
                    else:
                        year_str = match
                    
                    try:
                        year = int(year_str)
                        if year > base_year:
                            line = self._find_year_line(content, year_str)
                            issues.append(DateAnchorIssue(
                                issue_type="future_reference",
                                severity="important",
                                description=f"第{ch_num}章引用了未来年份{year}年的数据（基准年份为{base_year}年）",
                                chapter=ch_num,
                                line=line,
                                date1=f"{year}年",
                                date2=f"{base_year}年",
                            ))
                    except ValueError:
                        continue
        
        return issues
    
    def _check_source_timing(self, chapters: Dict[int, str]) -> List[DateAnchorIssue]:
        """检查数据来源时点"""
        issues = []
        
        # 检查同一章节内数据来源的时点是否一致
        for ch_num, content in chapters.items():
            # 提取数据来源时点
            source_dates = []
            
            # 匹配"来源：XXX年报"、"数据来源：XXX季报"等
            source_pattern = r"(?:来源|数据来源)[：:]\s*.*?(20\d{2})\s*年"
            matches = re.findall(source_pattern, content)
            source_dates.extend(matches)
            
            # 匹配脚注中的日期
            footnote_pattern = r"\[\^?\d+\].*?(20\d{2})\s*年"
            matches = re.findall(footnote_pattern, content)
            source_dates.extend(matches)
            
            # 检查是否有不同时点的数据来源
            if len(set(source_dates)) > 1:
                line = self._find_source_line(content)
                issues.append(DateAnchorIssue(
                    issue_type="anchor_conflict",
                    severity="suggestion",
                    description=f"第{ch_num}章数据来源时点不一致：{', '.join(set(source_dates))}",
                    chapter=ch_num,
                    line=line,
                    date1=source_dates[0] if source_dates else "",
                    date2=source_dates[1] if len(source_dates) > 1 else "",
                ))
        
        return issues
    
    def _find_year_line(self, content: str, year: str) -> int:
        """查找年份所在行号"""
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if year in line:
                return i + 1
        return 0
    
    def _find_source_line(self, content: str) -> int:
        """查找数据来源所在行号"""
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "来源" in line or "数据来源" in line:
                return i + 1
        return 0


def check_date_anchor(
    chapters: Dict[int, str],
    report_date: Optional[str] = None,
) -> DateAnchorResult:
    """
    检查日期锚点（入口函数）
    
    Args:
        chapters: 各章节内容 {chapter_num: content}
        report_date: 报告日期
    
    Returns:
        DateAnchorResult
    """
    checker = DateAnchorChecker()
    return checker.check(chapters, report_date)
