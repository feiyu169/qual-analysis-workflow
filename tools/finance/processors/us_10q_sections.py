"""
US 10-Q Sections - 美股 10-Q 季报章节映射

10-Q 使用 Part + Item 结构:
- Part I: Financial Information
  - Item 1: Financial Statements
  - Item 2: MD&A
  - Item 3: Quantitative and Qualitative Disclosures About Market Risk
  - Item 4: Controls and Procedures
- Part II: Other Information
  - Item 1: Legal Proceedings
  - Item 1A: Risk Factors
  - Item 2: Unregistered Sales of Equity Securities
  - Item 3: Defaults Upon Senior Securities
  - Item 4: Mine Safety Disclosures
  - Item 5: Other Information
  - Item 6: Exhibits
"""

import logging
import re

from .base import BaseProcessor

logger = logging.getLogger(__name__)

US_10Q_SECTIONS = {
    # Part I - 财务信息
    "Financial Statements": {
        "pattern": r"Item\s+1[:\.\s]",
        "part": "I",
        "priority": 1,
        "keywords": ["Financial Statements", "Condensed Consolidated"],
    },
    "MD&A": {
        "pattern": r"Item\s+2[:\.\s]",
        "part": "I",
        "priority": 2,
        "keywords": ["Management's Discussion", "Operating Results"],
    },
    "Market Risk": {
        "pattern": r"Item\s+3[:\.\s]",
        "part": "I",
        "priority": 3,
        "keywords": ["Quantitative and Qualitative", "Market Risk"],
    },
    "Controls and Procedures": {
        "pattern": r"Item\s+4[:\.\s]",
        "part": "I",
        "priority": 4,
        "keywords": ["Controls and Procedures"],
    },
    # Part II - 其他信息
    "Legal Proceedings": {
        "pattern": r"(?:Item\s+1[:\.\s](?!.*Part\s+I)|(?<=Part\s+II).*?Item\s+1[:\.\s])",
        "part": "II",
        "priority": 5,
        "keywords": ["Legal Proceedings"],
    },
    "Risk Factors": {
        "pattern": r"Item\s+1A[:\.\s]",
        "part": "II",
        "priority": 6,
        "keywords": ["Risk Factors"],
    },
    "Use of Proceeds": {
        "pattern": r"Item\s+2[:\.\s].*Part\s+II",
        "part": "II",
        "priority": 7,
        "keywords": ["Unregistered Sales", "Use of Proceeds"],
    },
    "Defaults": {
        "pattern": r"Item\s+3[:\.\s].*Part\s+II",
        "part": "II",
        "priority": 8,
        "keywords": ["Defaults Upon Senior Securities"],
    },
    "Mine Safety": {
        "pattern": r"Item\s+4[:\.\s].*Part\s+II",
        "part": "II",
        "priority": 9,
        "keywords": ["Mine Safety"],
    },
    "Exhibits": {
        "pattern": r"Item\s+6[:\.\s]",
        "part": "II",
        "priority": 10,
        "keywords": ["Exhibits"],
    },
}


class US10QSectionsProcessor(BaseProcessor):
    """美股 10-Q 季报章节映射处理器

    实现 Gate 2.9 (v2.0 新增):
    - extract_sections(): 从 10-Q 中提取 Part + Item 结构的章节
    - extract_tables(): 提取季度财务报表
    """

    def __init__(self):
        self.sections_config = US_10Q_SECTIONS

    def extract_sections(self, markdown: str) -> dict[str, str]:
        """从 10-Q 中提取章节

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

        logger.info(f"10-Q 章节提取: {list(sections.keys())}")
        return sections

    def _generic_split(self, text: str) -> dict[str, str]:
        """通用分割方案"""
        sections = {}
        item_pattern = r"Item\s+(\d+[A-Z]?)[:\.\s]"
        matches = list(re.finditer(item_pattern, text, re.IGNORECASE))

        item_names = {
            "1": "Financial Statements",
            "2": "MD&A",
            "3": "Market Risk",
            "4": "Controls and Procedures",
            "1A": "Risk Factors",
            "2": "Unregistered Sales",
            "3": "Defaults",
            "5": "Other Information",
            "6": "Exhibits",
        }

        for i, match in enumerate(matches):
            item_num = match.group(1)
            item_name = item_names.get(item_num, f"Item {item_num}")
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            if content:
                key = item_name
                if key in sections:
                    key = f"{item_name}_PartII"
                sections[key] = content

        return sections

    def extract_tables(self, markdown: str) -> list[dict]:
        """从 10-Q 中提取表格"""
        tables = []

        table_patterns = [
            (r"Condensed\s+Consolidated.*Statements?\s+of.*(?:Income|Operations)", "income_statement"),
            (r"Condensed\s+Consolidated\s+Balance\s+Sheets?", "balance_sheet"),
            (r"Condensed\s+Consolidated.*Cash\s+Flows?", "cash_flow"),
            (r"Segment|Revenue\s+by\s+Segment", "segment"),
        ]

        for pattern, table_type in table_patterns:
            match = re.search(pattern, markdown, re.IGNORECASE)
            if match:
                start = max(0, match.start() - 200)
                end = min(len(markdown), match.start() + 15000)
                tables.append({
                    "name": match.group(0),
                    "type": table_type,
                    "content": markdown[start:end].strip(),
                    "source": "10-Q",
                })

        logger.info(f"10-Q 表格提取: {len(tables)} 个")
        return tables
