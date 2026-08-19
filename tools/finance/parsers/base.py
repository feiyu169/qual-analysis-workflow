"""
Parser Base - 解析器基类

所有解析器必须继承 BaseParser 并实现 parse() 方法。
parse() 返回 ParsedFiling 对象，包含 markdown 和 metadata。
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ParsedFiling:
    """解析后的财报数据

    Attributes:
        markdown: 转换后的 Markdown 文本
        tables: 提取的表格列表
        metadata: 元数据（标题、日期、页数等）
        page_count: 总页数
        source_path: 源文件路径
    """

    markdown: str
    tables: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    page_count: int = 0
    source_path: str = ""

    def __post_init__(self):
        if not self.source_path and "source_path" in self.metadata:
            self.source_path = self.metadata["source_path"]

    @property
    def length(self) -> int:
        """Markdown 文本长度"""
        return len(self.markdown)

    @property
    def table_count(self) -> int:
        """表格数量"""
        return len(self.tables)


class BaseParser(ABC):
    """解析器基类

    所有解析器必须实现 parse 方法，将 PDF 文件转换为 ParsedFiling。
    """

    @abstractmethod
    def parse(
        self,
        pdf_path: Path,
        ticker: str,
        form_type: str,
    ) -> ParsedFiling:
        """解析财报 PDF

        Args:
            pdf_path: PDF 文件路径
            ticker: 股票代码
            form_type: 表单类型

        Returns:
            ParsedFiling 对象

        Raises:
            FileNotFoundError: PDF 文件不存在
            RuntimeError: 解析失败
        """
        ...

    def _validate_path(self, pdf_path: Path) -> Path:
        """验证 PDF 路径

        Args:
            pdf_path: PDF 文件路径

        Returns:
            验证后的路径

        Raises:
            FileNotFoundError: 文件不存在
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {path}")
        if not path.suffix.lower() == ".pdf":
            logger.warning(f"文件扩展名不是 .pdf: {path}")
        return path
