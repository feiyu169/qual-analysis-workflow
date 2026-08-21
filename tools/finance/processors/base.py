"""
Processor Base - 处理器基类

所有处理器必须继承 BaseProcessor 并实现:
- extract_sections(): 从 Markdown 中提取章节
- extract_tables(): 从 Markdown 中提取表格
"""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SectionResult:
    """章节提取结果"""

    name: str
    content: str
    start_pos: int = 0
    end_pos: int = 0
    page_ref: str | None = None


@dataclass
class TableResult:
    """表格提取结果"""

    name: str
    table_type: str  # income_statement, balance_sheet, cash_flow, segment, other
    data: list[dict] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    page_ref: str | None = None
    confidence: float = 0.0


class BaseProcessor(ABC):
    """处理器基类

    所有处理器必须实现 extract_sections 和 extract_tables。
    基类提供通用的正则匹配辅助方法。
    """

    @abstractmethod
    def extract_sections(self, markdown: str) -> dict[str, str]:
        """从 Markdown 中提取章节

        Args:
            markdown: 解析后的 Markdown 文本

        Returns:
            section_name → content 字典
        """
        ...

    @abstractmethod
    def extract_tables(self, markdown: str) -> list[dict]:
        """从 Markdown 中提取表格

        Args:
            markdown: 解析后的 Markdown 文本

        Returns:
            表格列表，每个包含 name, type, data 等字段
        """
        ...

    def _find_pattern(
        self,
        text: str,
        pattern: str,
        flags: int = re.IGNORECASE | re.MULTILINE,
    ) -> re.Match | None:
        """查找正则匹配

        Args:
            text: 文本
            pattern: 正则表达式
            flags: 正则标志

        Returns:
            匹配结果或 None
        """
        return re.search(pattern, text, flags)

    def _extract_between(
        self,
        text: str,
        start_pattern: str,
        end_pattern: str,
        flags: int = re.IGNORECASE | re.MULTILINE,
    ) -> str | None:
        """提取两个模式之间的文本

        Args:
            text: 文本
            start_pattern: 起始模式
            end_pattern: 结束模式
            flags: 正则标志

        Returns:
            匹配的文本或 None
        """
        start_match = re.search(start_pattern, text, flags)
        if not start_match:
            return None

        end_match = re.search(end_pattern, text[start_match.end():], flags)
        if end_match:
            return text[start_match.start():start_match.end() + end_match.end()]
        else:
            return text[start_match.start():]

    def _split_by_pattern(
        self,
        text: str,
        pattern: str,
        flags: int = re.IGNORECASE | re.MULTILINE,
    ) -> list[tuple[str, str]]:
        """按模式分割文本

        Args:
            text: 文本
            pattern: 分割模式
            flags: 正则标志

        Returns:
            (标题, 内容) 元组列表
        """
        matches = list(re.finditer(pattern, text, flags))
        if not matches:
            return []

        sections = []
        for i, match in enumerate(matches):
            title = match.group(0).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            sections.append((title, content))

        return sections
