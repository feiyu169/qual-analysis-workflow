"""
Table Extractor - 财务表格提取器

支持提取四类主要财务表格:
- income_statement: 利润表
- balance_sheet: 资产负债表
- cash_flow: 现金流量表
- segment: 分部报告
"""

import logging
import re
from dataclasses import dataclass, field

from .base import BaseProcessor

logger = logging.getLogger(__name__)


# 表格识别关键词
TABLE_KEYWORDS = {
    "income_statement": {
        "en": [
            "Consolidated Statements of Income",
            "Consolidated Statements of Operations",
            "Consolidated Statements of Comprehensive Income",
            "Income Statement",
            "Profit or Loss",
            "Revenue",
            "Net Income",
        ],
        "zh": [
            "利润表",
            "合并利润表",
            "综合损益表",
            "损益表",
            "收益表",
            "营业收入",
        ],
    },
    "balance_sheet": {
        "en": [
            "Consolidated Balance Sheets",
            "Balance Sheet",
            "Statement of Financial Position",
            "Total Assets",
            "Total Liabilities",
            "Stockholders' Equity",
        ],
        "zh": [
            "资产负债表",
            "合并资产负债表",
            "综合财务状况表",
            "资产总计",
            "负债合计",
            "所有者权益",
        ],
    },
    "cash_flow": {
        "en": [
            "Consolidated Statements of Cash Flows",
            "Cash Flow Statement",
            "Cash Flows from Operating",
            "Cash Flows from Investing",
            "Cash Flows from Financing",
        ],
        "zh": [
            "现金流量表",
            "合并现金流量表",
            "经营活动",
            "投资活动",
            "筹资活动",
        ],
    },
    "segment": {
        "en": [
            "Segment Information",
            "Revenue by Segment",
            "Reportable Segments",
            "Geographic Information",
            "Business Segments",
        ],
        "zh": [
            "分部报告",
            "分部信息",
            "按业务分部",
            "按地区分部",
        ],
    },
}


@dataclass
class ExtractedTable:
    """提取的表格"""

    name: str
    table_type: str  # income_statement, balance_sheet, cash_flow, segment
    content: str
    headers: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    source_language: str = "unknown"  # en, zh


class FinancialTableExtractor(BaseProcessor):
    """财务表格提取器

    实现 Gate 2.12:
    - extract_sections(): 提取包含财务表格的章节
    - extract_tables(): 提取并分类财务表格
    - 支持 income_statement/balance_sheet/cash_flow/segment
    - 支持中英文双语
    """

    def __init__(self):
        self.table_keywords = TABLE_KEYWORDS

    def extract_sections(self, markdown: str) -> dict[str, str]:
        """提取包含财务表格的章节

        Args:
            markdown: 解析后的 Markdown 文本

        Returns:
            section_name → content 字典
        """
        sections = {}

        for table_type, keywords in self.table_keywords.items():
            for lang, keyword_list in keywords.items():
                for keyword in keyword_list:
                    match = re.search(re.escape(keyword), markdown, re.IGNORECASE)
                    if match:
                        start = max(0, match.start() - 500)
                        end = min(len(markdown), match.start() + 15000)
                        sections[f"{table_type}_{lang}"] = markdown[start:end].strip()
                        break
                if f"{table_type}_{lang}" in sections:
                    break

        return sections

    def extract_tables(self, markdown: str) -> list[dict]:
        """提取并分类财务表格

        Args:
            markdown: 解析后的 Markdown 文本

        Returns:
            表格列表，每个包含 name, type, content, confidence 等字段
        """
        tables = []
        found_types = set()

        # 按优先级查找表格
        priority_order = [
            "income_statement",
            "balance_sheet",
            "cash_flow",
            "segment",
        ]

        for table_type in priority_order:
            keywords = self.table_keywords[table_type]

            for lang, keyword_list in keywords.items():
                for keyword in keyword_list:
                    if table_type in found_types:
                        break

                    match = re.search(re.escape(keyword), markdown, re.IGNORECASE)
                    if match:
                        content = self._extract_table_content(markdown, match)
                        confidence = self._calculate_confidence(content, keyword)

                        tables.append({
                            "name": keyword,
                            "type": table_type,
                            "content": content,
                            "confidence": confidence,
                            "source_language": lang,
                        })
                        found_types.add(table_type)
                        break

        logger.info(f"财务表格提取: {len(tables)} 个 ({list(found_types)})")
        return tables

    def _extract_table_content(
        self,
        text: str,
        match: re.Match,
        max_chars: int = 15000,
    ) -> str:
        """提取表格内容

        Args:
            text: 全文
            match: 关键词匹配结果
            max_chars: 最大字符数

        Returns:
            表格内容文本
        """
        start = max(0, match.start() - 200)
        end = min(len(text), match.start() + max_chars)
        return text[start:end].strip()

    def _calculate_confidence(self, content: str, keyword: str) -> float:
        """计算表格识别置信度

        Args:
            content: 表格内容
            keyword: 关键词

        Returns:
            置信度 (0.0 - 1.0)
        """
        score = 0.3  # 基础分

        # 包含数字越多，越可能是财务表格
        numbers = re.findall(r"\d[\d,\.]+", content)
        if len(numbers) > 10:
            score += 0.2
        elif len(numbers) > 5:
            score += 0.1

        # 包含表格标记
        if "|" in content or "\t" in content:
            score += 0.1

        # 包含货币符号
        if any(c in content for c in ["$", "¥", "€", "£", "HK$"]):
            score += 0.1

        # 包含常见的行项目
        common_items = [
            "Total", "Net", "Revenue", "Income", "Expense",
            "Assets", "Liabilities", "Equity",
            "合计", "总计", "净", "收入", "费用", "资产", "负债",
        ]
        for item in common_items:
            if item.lower() in content.lower():
                score += 0.05
                break

        return min(score, 1.0)

    def extract_numeric_data(self, content: str) -> dict[str, list[str]]:
        """从表格内容中提取数值数据

        Args:
            content: 表格内容

        Returns:
            行项目名 → 数值列表 的字典
        """
        data = {}
        lines = content.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 尝试匹配 "项目名 数值1 数值2 ..." 格式
            parts = re.split(r"\s{2,}|\t", line)
            if len(parts) >= 2:
                name = parts[0].strip()
                values = []
                for part in parts[1:]:
                    cleaned = part.strip().replace(",", "")
                    if re.match(r"^-?[\d\.]+$", cleaned):
                        values.append(cleaned)
                if values:
                    data[name] = values

        return data
