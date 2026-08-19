"""
CN Sections - A 股章节映射

覆盖 A 股年报、半年报、季报的章节结构。
"""

import logging
import re
from typing import Optional

from .base import BaseProcessor

logger = logging.getLogger(__name__)

# A 股年报章节映射
CN_ANNUAL_SECTIONS = {
    "公司概况": {
        "patterns": [
            r"第[一二三四五六七八九十]+节\s*公司概况",
            r"公司基本情况",
            r"公司简介",
        ],
        "keywords": ["公司概况", "基本情况", "注册资本", "法定代表人"],
        "priority": 1,
    },
    "经营情况": {
        "patterns": [
            r"第[一二三四五六七八九十]+节\s*经营情况",
            r"报告期内.*经营情况",
            r"主营业务.*分析",
        ],
        "keywords": ["经营情况", "主营业务", "营业收入", "行业发展"],
        "priority": 2,
    },
    "财务报告": {
        "patterns": [
            r"第[一二三四五六七八九十]+节\s*财务报告",
            r"财务报表",
            r"合并资产负债表",
            r"合并利润表",
        ],
        "keywords": ["财务报告", "资产负债表", "利润表", "现金流量表"],
        "priority": 3,
    },
    "董事会报告": {
        "patterns": [
            r"第[一二三四五六七八九十]+节\s*董事会报告",
            r"董事会.*工作.*报告",
            r"管理层讨论与分析",
        ],
        "keywords": ["董事会报告", "管理层讨论", "经营计划"],
        "priority": 4,
    },
    "重要事项": {
        "patterns": [
            r"第[一二三四五六七八九十]+节\s*重要事项",
            r"重要事项",
        ],
        "keywords": ["重要事项", "关联交易", "重大合同"],
        "priority": 5,
    },
    "股份变动": {
        "patterns": [
            r"第[一二三四五六七八九十]+节\s*股份变动",
            r"股份变动情况",
            r"股东.*情况",
        ],
        "keywords": ["股份变动", "股东情况", "股本结构"],
        "priority": 6,
    },
}


class CNSectionsProcessor(BaseProcessor):
    """A 股章节映射处理器

    实现 Gate 2.6:
    - extract_sections(): 从 A 股年报/半年报中提取章节
    - extract_tables(): 从 A 股年报中提取表格
    - 支持年报/半年报/季报
    """

    def __init__(self):
        self.sections_config = CN_ANNUAL_SECTIONS

    def extract_sections(self, markdown: str) -> dict[str, str]:
        """从 A 股财报中提取章节

        Args:
            markdown: 解析后的 Markdown 文本

        Returns:
            section_name → content 字典
        """
        sections = {}
        matched_ranges: list[tuple[int, int]] = []

        for section_name, config in self.sections_config.items():
            content = self._find_section_content(markdown, config["patterns"])
            if content:
                sections[section_name] = content

        # 如果未找到任何章节，尝试通用分割
        if not sections:
            sections = self._generic_split(markdown)

        logger.info(f"A 股章节提取: {list(sections.keys())}")
        return sections

    def _find_section_content(
        self,
        text: str,
        patterns: list[str],
    ) -> Optional[str]:
        """查找章节内容

        Args:
            text: 文本
            patterns: 匹配模式列表

        Returns:
            章节内容或 None
        """
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # 查找下一个章节的起始位置
                next_section = re.search(
                    r"\n第[一二三四五六七八九十]+节|\n\s*\d+[\.\、]",
                    text[match.end():],
                    re.IGNORECASE,
                )
                if next_section:
                    return text[match.start():match.end() + next_section.start()].strip()
                else:
                    return text[match.start():].strip()[:50000]  # 限制长度

        return None

    def _generic_split(self, text: str) -> dict[str, str]:
        """通用分割方案

        Args:
            text: 文本

        Returns:
            section_name → content 字典
        """
        sections = {}

        # 按照常见的章节标记分割
        section_markers = [
            (r"公司概况|公司简介|基本情况", "公司概况"),
            (r"经营情况|主营业务|业务回顾", "经营情况"),
            (r"财务报告|财务报表|合并报表", "财务报告"),
            (r"董事会报告|管理层讨论", "董事会报告"),
            (r"重要事项", "重要事项"),
            (r"股东.*情况|股份变动", "股份变动"),
        ]

        for pattern, name in section_markers:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # 取匹配位置附近的内容
                start = max(0, match.start() - 100)
                end = min(len(text), match.start() + 30000)
                sections[name] = text[start:end].strip()

        return sections

    def extract_tables(self, markdown: str) -> list[dict]:
        """从 A 股财报中提取表格

        Args:
            markdown: 解析后的 Markdown 文本

        Returns:
            表格列表
        """
        tables = []

        # 查找财务三表
        table_patterns = [
            (r"合并资产负债表|资产负债表", "balance_sheet"),
            (r"合并利润表|利润表", "income_statement"),
            (r"合并现金流量表|现金流量表", "cash_flow"),
            (r"分部报告|分部信息", "segment"),
        ]

        for pattern, table_type in table_patterns:
            match = re.search(pattern, markdown, re.IGNORECASE)
            if match:
                # 提取表格区域
                table_content = self._extract_table_region(markdown, match.start())
                if table_content:
                    tables.append({
                        "name": match.group(0),
                        "type": table_type,
                        "content": table_content,
                        "source": "cn_annual",
                    })

        logger.info(f"A 股表格提取: {len(tables)} 个")
        return tables

    def _extract_table_region(self, text: str, start_pos: int, max_chars: int = 20000) -> Optional[str]:
        """提取表格区域

        Args:
            text: 文本
            start_pos: 起始位置
            max_chars: 最大字符数

        Returns:
            表格区域文本或 None
        """
        end_pos = min(start_pos + max_chars, len(text))
        return text[start_pos:end_pos].strip()
