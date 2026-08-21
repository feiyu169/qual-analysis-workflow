"""
HK Sections - 港股章节映射

覆盖港股年报、半年报、季报的章节结构。
"""

import logging
import re

from .base import BaseProcessor

logger = logging.getLogger(__name__)

# 港股年报章节映射
HK_ANNUAL_SECTIONS = {
    "公司资料": {
        "patterns": [
            r"公司资料",
            r"Corporate\s+Information",
            r"公司简介",
        ],
        "keywords": ["公司资料", "注册办事处", "核数师"],
        "priority": 1,
    },
    "财务摘要": {
        "patterns": [
            r"财务摘要",
            r"Financial\s+Summary",
            r"财务概要",
            r"五年.*财务.*概要",
        ],
        "keywords": ["财务摘要", "收入", "利润", "股息"],
        "priority": 2,
    },
    "管理层报告": {
        "patterns": [
            r"管理层.*讨论.*分析",
            r"Management.*Discussion.*Analysis",
            r"主席.*报告",
            r"业务.*回顾",
        ],
        "keywords": ["管理层讨论", "业务回顾", "前景", "策略"],
        "priority": 3,
    },
    "财务报表": {
        "patterns": [
            r"综合.*损益.*表",
            r"综合.*收益.*表",
            r"综合.*财务.*状况.*表",
            r"综合.*现金流量.*表",
            r"Consolidated.*Statement",
        ],
        "keywords": ["综合损益", "综合财务状况", "综合现金流量"],
        "priority": 4,
    },
    "董事报告": {
        "patterns": [
            r"董事.*报告",
            r"Report\s+of\s+the\s+Directors",
            r"董事会.*报告",
        ],
        "keywords": ["董事报告", "董事", "股本"],
        "priority": 5,
    },
    "其他资料": {
        "patterns": [
            r"其他资料",
            r"Additional\s+Information",
            r"企业管治",
        ],
        "keywords": ["其他资料", "企业管治", "环境"],
        "priority": 6,
    },
}


class HKSectionsProcessor(BaseProcessor):
    """港股章节映射处理器

    实现 Gate 2.7:
    - extract_sections(): 从港股年报/半年报中提取章节
    - extract_tables(): 从港股年报中提取表格
    - 支持中英文双语财报
    """

    def __init__(self):
        self.sections_config = HK_ANNUAL_SECTIONS

    def extract_sections(self, markdown: str) -> dict[str, str]:
        """从港股财报中提取章节

        Args:
            markdown: 解析后的 Markdown 文本

        Returns:
            section_name → content 字典
        """
        sections = {}

        for section_name, config in self.sections_config.items():
            content = self._find_section_content(markdown, config["patterns"])
            if content:
                sections[section_name] = content

        # 降级方案
        if not sections:
            sections = self._generic_split(markdown)

        logger.info(f"港股章节提取: {list(sections.keys())}")
        return sections

    def _find_section_content(
        self,
        text: str,
        patterns: list[str],
    ) -> str | None:
        """查找章节内容"""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # 查找下一个主要章节
                next_markers = [
                    r"\n公司资料|\nCorporate\s+Information",
                    r"\n财务摘要|\nFinancial\s+Summary",
                    r"\n管理层|\nManagement",
                    r"\n财务报表|\nFinancial\s+Statements",
                    r"\n董事报告|\nReport\s+of\s+Directors",
                    r"\n其他资料|\nAdditional\s+Information",
                ]
                next_pattern = "|".join(next_markers)
                next_section = re.search(next_pattern, text[match.end():], re.IGNORECASE)
                if next_section:
                    return text[match.start():match.end() + next_section.start()].strip()
                else:
                    return text[match.start():].strip()[:50000]
        return None

    def _generic_split(self, text: str) -> dict[str, str]:
        """通用分割方案"""
        sections = {}
        markers = [
            (r"公司资料|Corporate\s+Information", "公司资料"),
            (r"财务摘要|Financial\s+Summary|财务概要", "财务摘要"),
            (r"管理层.*讨论|Management.*Discussion|主席.*报告|业务.*回顾", "管理层报告"),
            (r"综合.*表|Consolidated.*Statement|财务报表", "财务报表"),
            (r"董事.*报告|Report.*Directors", "董事报告"),
            (r"其他资料|Additional\s+Information", "其他资料"),
        ]

        for pattern, name in markers:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                start = max(0, match.start() - 100)
                end = min(len(text), match.start() + 30000)
                sections[name] = text[start:end].strip()

        return sections

    def extract_tables(self, markdown: str) -> list[dict]:
        """从港股财报中提取表格"""
        tables = []

        table_patterns = [
            (r"综合.*损益.*表|Consolidated.*Income|综合.*收益.*表", "income_statement"),
            (r"综合.*财务.*状况.*表|Consolidated.*Balance|综合.*资产负债.*表", "balance_sheet"),
            (r"综合.*现金流量.*表|Consolidated.*Cash\s+Flow", "cash_flow"),
            (r"分部.*报告|Segment", "segment"),
        ]

        for pattern, table_type in table_patterns:
            match = re.search(pattern, markdown, re.IGNORECASE)
            if match:
                table_content = self._extract_table_region(markdown, match.start())
                if table_content:
                    tables.append({
                        "name": match.group(0),
                        "type": table_type,
                        "content": table_content,
                        "source": "hk_annual",
                    })

        logger.info(f"港股表格提取: {len(tables)} 个")
        return tables

    def _extract_table_region(self, text: str, start_pos: int, max_chars: int = 20000) -> str | None:
        """提取表格区域"""
        end_pos = min(start_pos + max_chars, len(text))
        return text[start_pos:end_pos].strip()
