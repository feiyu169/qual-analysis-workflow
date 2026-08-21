"""
US 20-F Sections - 美股 20-F 章节映射

20-F 是外国私人发行人 (FPI) 使用的年报格式。
使用 Item 1-19 结构。
"""

import logging
import re

from .base import BaseProcessor

logger = logging.getLogger(__name__)

US_20F_SECTIONS = {
    "Identity of Directors": {
        "pattern": r"Item\s+1[:\.\s]",
        "priority": 1,
        "keywords": ["Identity of Directors", "Senior Management"],
    },
    "Offer Statistics": {
        "pattern": r"Item\s+3[:\.\s]",
        "priority": 2,
        "keywords": ["Offer Statistics", "Buy-Back"],
    },
    "Risk Factors": {
        "pattern": r"Item\s+3[\.\s]+D",
        "priority": 3,
        "keywords": ["Risk Factors"],
    },
    "Information on the Company": {
        "pattern": r"Item\s+4[:\.\s]",
        "priority": 4,
        "keywords": ["Information on the Company", "Business Overview"],
    },
    "Operating and Financial Review": {
        "pattern": r"Item\s+5[:\.\s]",
        "priority": 5,
        "keywords": ["Operating and Financial Review", "MD&A"],
    },
    "Directors and Officers": {
        "pattern": r"Item\s+6[:\.\s]",
        "priority": 6,
        "keywords": ["Directors", "Senior Management", "Employees"],
    },
    "Major Shareholders": {
        "pattern": r"Item\s+7[:\.\s]",
        "priority": 7,
        "keywords": ["Major Shareholders", "Related Party"],
    },
    "Financial Information": {
        "pattern": r"Item\s+8[:\.\s]",
        "priority": 8,
        "keywords": ["Financial Statements", "Consolidated"],
    },
    "Listing Details": {
        "pattern": r"Item\s+9[:\.\s]",
        "priority": 9,
        "keywords": ["Listing", "Offering"],
    },
    "Additional Information": {
        "pattern": r"Item\s+10[:\.\s]",
        "priority": 10,
        "keywords": ["Additional Information", "Memorandum"],
    },
    "Quantitative Disclosures": {
        "pattern": r"Item\s+11[:\.\s]",
        "priority": 11,
        "keywords": ["Quantitative", "Qualitative Disclosures"],
    },
    "Description of Securities": {
        "pattern": r"Item\s+12[:\.\s]",
        "priority": 12,
        "keywords": ["Description of Securities"],
    },
    "Defaults": {
        "pattern": r"Item\s+13[:\.\s]",
        "priority": 13,
        "keywords": ["Defaults", "Dividends"],
    },
    "Material Modifications": {
        "pattern": r"Item\s+14[:\.\s]",
        "priority": 14,
        "keywords": ["Material Modifications"],
    },
    "Controls and Procedures": {
        "pattern": r"Item\s+15[:\.\s]",
        "priority": 15,
        "keywords": ["Controls and Procedures"],
    },
    "Auditors": {
        "pattern": r"Item\s+16[:\.\s]",
        "priority": 16,
        "keywords": ["Auditors", "Audit"],
    },
    "Financial Statements (Item 18)": {
        "pattern": r"Item\s+18[:\.\s]",
        "priority": 17,
        "keywords": ["Financial Statements"],
    },
    "Exhibits": {
        "pattern": r"Item\s+19[:\.\s]",
        "priority": 18,
        "keywords": ["Exhibits"],
    },
}


class US20FSectionsProcessor(BaseProcessor):
    """美股 20-F 章节映射处理器

    实现 Gate 2.10:
    - extract_sections(): 从 20-F 中提取 Item 1-19 结构的章节
    - extract_tables(): 提取财务报表
    """

    def __init__(self):
        self.sections_config = US_20F_SECTIONS

    def extract_sections(self, markdown: str) -> dict[str, str]:
        """从 20-F 中提取章节

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

        logger.info(f"20-F 章节提取: {list(sections.keys())}")
        return sections

    def _generic_split(self, text: str) -> dict[str, str]:
        """通用分割方案"""
        sections = {}
        item_pattern = r"Item\s+(\d+[A-Z]?)[:\.\s]"
        matches = list(re.finditer(item_pattern, text, re.IGNORECASE))

        for i, match in enumerate(matches):
            item_num = match.group(1)
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            if content:
                sections[f"Item {item_num}"] = content

        return sections

    def extract_tables(self, markdown: str) -> list[dict]:
        """从 20-F 中提取表格"""
        tables = []

        table_patterns = [
            (r"Consolidated\s+Statements?\s+of\s+Income|Consolidated.*Operations", "income_statement"),
            (r"Consolidated\s+Balance\s+Sheets?", "balance_sheet"),
            (r"Consolidated\s+Statements?\s+of\s+Cash\s+Flows?", "cash_flow"),
            (r"Segment\s+Information|Revenue\s+by\s+Segment", "segment"),
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
                    "source": "20-F",
                })

        logger.info(f"20-F 表格提取: {len(tables)} 个")
        return tables
