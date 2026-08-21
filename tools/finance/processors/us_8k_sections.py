"""
US 8-K Sections - 美股 8-K 事件驱动章节映射

8-K 是事件驱动格式，结构不固定。
使用 Item 编号作为主要识别方式。
"""

import logging
import re

from .base import BaseProcessor

logger = logging.getLogger(__name__)

# 8-K 事件类型映射
US_8K_ITEMS = {
    "1.01": "Entry into Material Agreement",
    "1.02": "Termination of Material Agreement",
    "1.03": "Bankruptcy or Receivership",
    "2.01": "Completion of Acquisition or Disposition",
    "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of Direct Financial Obligation",
    "2.04": "Triggering Events That Accelerate Obligations",
    "2.05": "Costs Associated with Exit or Disposal",
    "2.06": "Material Impairments",
    "3.01": "Notice of Delisting",
    "3.02": "Unregistered Sales of Equity Securities",
    "3.03": "Material Modification to Rights",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements",
    "5.01": "Changes in Control",
    "5.02": "Departure/Election of Directors or Officers",
    "5.03": "Amendments to Articles",
    "5.05": "Amendments to Code of Ethics",
    "5.07": "Submission of Matters to Vote",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}


class US8KSectionsProcessor(BaseProcessor):
    """美股 8-K 事件驱动章节映射处理器

    实现 Gate 2.11 (v2.0 新增):
    - extract_sections(): 从 8-K 中识别并提取事件 Item
    - extract_tables(): 提取 8-K 中的财务数据
    """

    def extract_sections(self, markdown: str) -> dict[str, str]:
        """从 8-K 中提取事件章节

        Args:
            markdown: 解析后的 Markdown 文本

        Returns:
            section_name → content 字典
        """
        sections = {}

        for item_code, item_name in US_8K_ITEMS.items():
            pattern = rf"Item\s+{re.escape(item_code)}"
            match = re.search(pattern, markdown, re.IGNORECASE)
            if match:
                content = self._extract_item_content(markdown, match, item_code)
                sections[f"Item {item_code}: {item_name}"] = content

        if not sections:
            sections = self._generic_split(markdown)

        logger.info(f"8-K 章节提取: {list(sections.keys())}")
        return sections

    def _extract_item_content(
        self,
        text: str,
        match: re.Match,
        current_code: str,
    ) -> str:
        """提取单个 Item 的内容

        Args:
            text: 全文
            match: 当前 Item 的匹配结果
            current_code: 当前 Item 编号

        Returns:
            Item 内容文本
        """
        # 查找下一个 Item
        next_item_pattern = r"Item\s+\d+\.\d+"
        next_match = re.search(next_item_pattern, text[match.end():], re.IGNORECASE)

        if next_match:
            return text[match.start():match.end() + next_match.start()].strip()
        else:
            content = text[match.start():]
            if len(content) > 50000:
                content = content[:50000]
            return content.strip()

    def _generic_split(self, text: str) -> dict[str, str]:
        """通用分割方案"""
        sections = {}
        item_pattern = r"Item\s+(\d+\.\d+)"
        matches = list(re.finditer(item_pattern, text, re.IGNORECASE))

        for i, match in enumerate(matches):
            item_code = match.group(1)
            item_name = US_8K_ITEMS.get(item_code, f"Item {item_code}")
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            if content:
                sections[f"Item {item_code}: {item_name}"] = content

        return sections

    def extract_tables(self, markdown: str) -> list[dict]:
        """从 8-K 中提取表格

        8-K 通常在 Item 2.02 (Results of Operations) 中包含财务数据。
        """
        tables = []

        # Item 2.02: Results of Operations and Financial Condition
        match = re.search(r"Item\s+2\.02", markdown, re.IGNORECASE)
        if match:
            start = match.start()
            end = min(len(markdown), start + 20000)
            tables.append({
                "name": "Item 2.02: Results of Operations",
                "type": "income_statement",
                "content": markdown[start:end].strip(),
                "source": "8-K",
            })

        # Item 9.01: Financial Statements and Exhibits
        match = re.search(r"Item\s+9\.01", markdown, re.IGNORECASE)
        if match:
            start = match.start()
            end = min(len(markdown), start + 20000)
            tables.append({
                "name": "Item 9.01: Financial Statements and Exhibits",
                "type": "other",
                "content": markdown[start:end].strip(),
                "source": "8-K",
            })

        logger.info(f"8-K 表格提取: {len(tables)} 个")
        return tables


def identify_8k_events(markdown: str) -> list[dict]:
    """识别 8-K 中的事件（独立函数）

    Args:
        markdown: 解析后的 Markdown 文本

    Returns:
        事件列表，每个包含 item_code, item_name, content
    """
    events = []

    for item_code, item_name in US_8K_ITEMS.items():
        pattern = rf"Item\s+{re.escape(item_code)}"
        match = re.search(pattern, markdown, re.IGNORECASE)
        if match:
            # 提取内容
            next_pattern = r"Item\s+\d+\.\d+"
            next_match = re.search(next_pattern, markdown[match.end():], re.IGNORECASE)
            if next_match:
                content = markdown[match.start():match.end() + next_match.start()].strip()
            else:
                content = markdown[match.start():].strip()[:50000]

            events.append({
                "item_code": item_code,
                "item_name": item_name,
                "content": content,
            })

    return events
