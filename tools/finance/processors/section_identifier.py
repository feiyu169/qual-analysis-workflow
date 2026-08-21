"""
Section Identifier - 通用章节识别

作为降级方案，当专用处理器无法识别章节时使用。
支持:
- 中文数字章节 (第一节, 第二节...)
- 英文 Item 编号 (Item 1, Item 2...)
- 标题层级 (# Heading, ## Heading...)
"""

import logging
import re

from .base import BaseProcessor

logger = logging.getLogger(__name__)

# 中文数字映射
CN_NUMBERS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
}

# 通用章节标题关键词
SECTION_KEYWORDS = {
    "overview": ["概述", "简介", "Overview", "Introduction", "Summary"],
    "business": ["业务", "经营", "Business", "Operations"],
    "financial": ["财务", "Finance", "Financial"],
    "risk": ["风险", "Risk", "Risks"],
    "management": ["管理", "Management", "Board"],
    "governance": ["治理", "Governance", "Corporate"],
    "compensation": ["薪酬", "Compensation", "Remuneration"],
    "shareholders": ["股东", "Shareholder", "Equity"],
    "outlook": ["前景", "展望", "Outlook", "Prospects"],
}


class SectionIdentifier(BaseProcessor):
    """通用章节识别器

    作为降级方案，当专用处理器 (cn_sections, hk_sections, us_*_sections)
    无法识别章节时使用。

    支持三种章节标记格式:
    1. 中文数字: 第一节, 第二节...
    2. 英文 Item: Item 1, Item 2...
    3. Markdown 标题: # Heading, ## Heading...
    """

    def extract_sections(self, markdown: str) -> dict[str, str]:
        """通用章节识别

        Args:
            markdown: 解析后的 Markdown 文本

        Returns:
            section_name → content 字典
        """
        # 尝试多种分割策略
        sections = {}

        # 策略 1: 中文数字章节
        cn_sections = self._split_by_cn_sections(markdown)
        if cn_sections:
            sections.update(cn_sections)

        # 策略 2: 英文 Item 编号
        if not sections:
            item_sections = self._split_by_items(markdown)
            if item_sections:
                sections.update(item_sections)

        # 策略 3: Markdown 标题
        if not sections:
            heading_sections = self._split_by_headings(markdown)
            if heading_sections:
                sections.update(heading_sections)

        # 策略 4: 按关键词分割
        if not sections:
            keyword_sections = self._split_by_keywords(markdown)
            if keyword_sections:
                sections.update(keyword_sections)

        # 最终降级: 按长度分段
        if not sections:
            sections = self._split_by_length(markdown)

        logger.info(f"通用章节识别: {len(sections)} 个章节")
        return sections

    def _split_by_cn_sections(self, text: str) -> dict[str, str]:
        """按中文数字章节分割"""
        sections = {}
        pattern = r"第([一二三四五六七八九十]+)节[：:\s]*(.*)"
        matches = list(re.finditer(pattern, text))

        for i, match in enumerate(matches):
            cn_num = match.group(1)
            title = match.group(2).strip()
            section_num = CN_NUMBERS.get(cn_num, i + 1)
            name = f"第{cn_num}节" + (f": {title}" if title else "")

            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()

            if content:
                sections[name] = content

        return sections

    def _split_by_items(self, text: str) -> dict[str, str]:
        """按英文 Item 编号分割"""
        sections = {}
        pattern = r"Item\s+(\d+[A-Z]?)[:\.\s]+(.*)"
        matches = list(re.finditer(pattern, text, re.IGNORECASE))

        for i, match in enumerate(matches):
            item_num = match.group(1)
            title = match.group(2).strip()
            name = f"Item {item_num}" + (f": {title}" if title else "")

            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()

            if content:
                sections[name] = content

        return sections

    def _split_by_headings(self, text: str) -> dict[str, str]:
        """按 Markdown 标题分割"""
        sections = {}
        # 匹配 # 和 ## 标题
        pattern = r"^(#{1,3})\s+(.+)$"
        matches = list(re.finditer(pattern, text, re.MULTILINE))

        for i, match in enumerate(matches):
            level = len(match.group(1))
            title = match.group(2).strip()

            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()

            if content and len(content) > 100:
                sections[title] = content

        return sections

    def _split_by_keywords(self, text: str) -> dict[str, str]:
        """按关键词分割"""
        sections = {}

        for category, keywords in SECTION_KEYWORDS.items():
            for keyword in keywords:
                match = re.search(
                    rf"(?:^|\n).*{re.escape(keyword)}.*(?:\n|$)",
                    text,
                    re.IGNORECASE,
                )
                if match:
                    start = max(0, match.start() - 100)
                    end = min(len(text), match.start() + 10000)
                    sections[f"{category}_{keyword}"] = text[start:end].strip()
                    break

        return sections

    def _split_by_length(self, text: str, chunk_size: int = 20000) -> dict[str, str]:
        """按长度分段（最终降级方案）"""
        sections = {}
        total_len = len(text)
        num_chunks = (total_len + chunk_size - 1) // chunk_size

        for i in range(num_chunks):
            start = i * chunk_size
            end = min((i + 1) * chunk_size, total_len)
            chunk = text[start:end].strip()
            if chunk:
                sections[f"Section_{i+1}"] = chunk

        return sections

    def extract_tables(self, markdown: str) -> list[dict]:
        """通用表格提取

        Args:
            markdown: 解析后的 Markdown 文本

        Returns:
            表格列表
        """
        tables = []
        # 简单按行查找可能的表格区域
        table_keywords = [
            "income", "revenue", "profit", "loss",
            "balance", "asset", "liability", "equity",
            "cash flow", "operating", "investing", "financing",
            "收入", "利润", "资产", "负债", "权益", "现金流",
        ]

        for keyword in table_keywords:
            match = re.search(re.escape(keyword), markdown, re.IGNORECASE)
            if match:
                start = max(0, match.start() - 200)
                end = min(len(markdown), match.start() + 10000)
                tables.append({
                    "name": f"Table containing '{keyword}'",
                    "type": "other",
                    "content": markdown[start:end].strip(),
                    "source": "generic_identifier",
                })

        logger.info(f"通用表格识别: {len(tables)} 个")
        return tables
