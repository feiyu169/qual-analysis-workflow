"""
US 10-K Sections - 美股 10-K 年报章节映射

10-K 使用 Part + Item 结构:
- Part I: Business, Risk Factors, Properties, Legal Proceedings
- Part II: Financial Data, MD&A, Market Risk, Financial Statements
- Part III: Directors, Executive Compensation, Security Ownership
- Part IV: Exhibits, Financial Statement Schedules
"""

import logging
import re

from .base import BaseProcessor

logger = logging.getLogger(__name__)

US_10K_SECTIONS = {
    "Business": {
        "pattern": r"Item\s+1[:\.\s]",
        "part": "I",
        "priority": 1,
        "keywords": ["Business", "Overview", "Products", "Services"],
    },
    "Risk Factors": {
        "pattern": r"Item\s+1A[:\.\s]",
        "part": "I",
        "priority": 2,
        "keywords": ["Risk Factors", "risks", "uncertainties"],
    },
    "Properties": {
        "pattern": r"Item\s+2[:\.\s]",
        "part": "I",
        "priority": 3,
        "keywords": ["Properties", "facilities", "real estate"],
    },
    "Legal Proceedings": {
        "pattern": r"Item\s+3[:\.\s]",
        "part": "I",
        "priority": 4,
        "keywords": ["Legal Proceedings", "litigation"],
    },
    "MD&A": {
        "pattern": r"Item\s+7[:\.\s]",
        "part": "II",
        "priority": 5,
        "keywords": ["Management's Discussion", "Operating Results", "Financial Condition"],
    },
    "Financial Statements": {
        "pattern": r"Item\s+8[:\.\s]",
        "part": "II",
        "priority": 6,
        "keywords": ["Financial Statements", "Consolidated", "Balance Sheet", "Income Statement"],
    },
    "Market Risk": {
        "pattern": r"Item\s+7A[:\.\s]",
        "part": "II",
        "priority": 7,
        "keywords": ["Quantitative and Qualitative", "Market Risk"],
    },
    "Changes in Accountant": {
        "pattern": r"Item\s+9[:\.\s]",
        "part": "II",
        "priority": 8,
        "keywords": ["Changes in", "Disagreements", "Accountant"],
    },
    "Directors and Officers": {
        "pattern": r"Item\s+10[:\.\s]",
        "part": "III",
        "priority": 9,
        "keywords": ["Directors", "Executive Officers", "Corporate Governance"],
    },
    "Executive Compensation": {
        "pattern": r"Item\s+11[:\.\s]",
        "part": "III",
        "priority": 10,
        "keywords": ["Executive Compensation", "compensation"],
    },
    "Security Ownership": {
        "pattern": r"Item\s+12[:\.\s]",
        "part": "III",
        "priority": 11,
        "keywords": ["Security Ownership", "beneficial owners"],
    },
    "Exhibits": {
        "pattern": r"Item\s+15[:\.\s]",
        "part": "IV",
        "priority": 12,
        "keywords": ["Exhibits", "Financial Statement Schedules"],
    },
}


class US10KSectionsProcessor(BaseProcessor):
    """美股 10-K 年报章节映射处理器

    实现 Gate 2.8:
    - extract_sections(): 从 10-K 中提取 Part + Item 结构的章节
    - extract_tables(): 提取财务三表和分部报告
    """

    def __init__(self):
        self.sections_config = US_10K_SECTIONS

    def extract_sections(self, markdown: str) -> dict[str, str]:
        """从 10-K 中提取章节

        Args:
            markdown: 解析后的 Markdown 文本

        Returns:
            section_name → content 字典
        """
        sections = {}
        section_list = sorted(
            self.sections_config.items(),
            key=lambda x: x[1]["priority"],
        )

        for section_name, config in section_list:
            pattern = config["pattern"]
            match = re.search(pattern, markdown, re.IGNORECASE)
            if match:
                # 查找下一个 Item
                next_item = re.search(
                    r"Item\s+\d+[A-Z]?[:\.\s]",
                    markdown[match.end():],
                    re.IGNORECASE,
                )
                if next_item:
                    content = markdown[match.start():match.end() + next_item.start()]
                else:
                    content = markdown[match.start():]
                    if len(content) > 100000:
                        content = content[:100000]

                sections[section_name] = content.strip()

        if not sections:
            sections = self._generic_split(markdown)

        logger.info(f"10-K 章节提取: {list(sections.keys())}")
        return sections

    def _generic_split(self, text: str) -> dict[str, str]:
        """通用分割方案"""
        sections = {}
        item_pattern = r"Item\s+(\d+[A-Z]?)[:\.\s]"
        matches = list(re.finditer(item_pattern, text, re.IGNORECASE))

        item_names = {
            "1": "Business", "1A": "Risk Factors", "1B": "Unresolved Staff Comments",
            "2": "Properties", "3": "Legal Proceedings", "4": "Mine Safety",
            "5": "Market for Registrant's Common Equity",
            "6": "Selected Financial Data",
            "7": "MD&A", "7A": "Market Risk",
            "8": "Financial Statements", "9": "Changes in Accountant",
            "9A": "Controls and Procedures",
            "10": "Directors and Officers",
            "11": "Executive Compensation",
            "12": "Security Ownership",
            "13": "Certain Relationships",
            "14": "Principal Accountant Fees",
            "15": "Exhibits",
            "16": "Form 10-K Summary",
        }

        for i, match in enumerate(matches):
            item_num = match.group(1)
            item_name = item_names.get(item_num, f"Item {item_num}")
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            if content:
                sections[item_name] = content

        return sections

    def extract_tables(self, markdown: str) -> list[dict]:
        """从 10-K 中提取表格"""
        tables = []

        table_patterns = [
            (r"Consolidated\s+Statements?\s+of\s+Income|Consolidated.*Operations", "income_statement"),
            (r"Consolidated\s+Balance\s+Sheets?", "balance_sheet"),
            (r"Consolidated\s+Statements?\s+of\s+Cash\s+Flows?", "cash_flow"),
            (r"Segment\s+Information|Revenue\s+by\s+Segment|Reportable\s+Segments?", "segment"),
        ]

        for pattern, table_type in table_patterns:
            match = re.search(pattern, markdown, re.IGNORECASE)
            if match:
                start = max(0, match.start() - 200)
                end = min(len(markdown), match.start() + 20000)
                tables.append({
                    "name": match.group(0),
                    "type": table_type,
                    "content": markdown[start:end].strip(),
                    "source": "10-K",
                })

        logger.info(f"10-K 表格提取: {len(tables)} 个")
        return tables
