"""降级解析器。

pdfplumber → PyPDF2 → PyMuPDF 自动回退。
实现完整DocumentStore接口（9个接口）。

降级策略：
1. 尝试pdfplumber（表格提取能力强）
2. 失败则尝试PyPDF2（基础文本提取）
3. 失败则尝试PyMuPDF（fitz，高性能）
4. 都失败则返回空结果
"""

from __future__ import annotations

import logging
from pathlib import Path

from .document_store import (
    DocumentStore,
    SearchHit,
    SectionContent,
    SectionSummary,
    TableContent,
    TableSummary,
)

logger = logging.getLogger(__name__)


class FallbackParser(DocumentStore):
    """降级解析器。

    pdfplumber → PyPDF2 自动回退。
    实现完整DocumentStore接口。
    """

    PARSER_VERSION = "hermes_fallback_parser_v2.5.0"

    def __init__(self, pdf_path: Path):
        """初始化解析器。

        Args:
            pdf_path: PDF文件路径

        Raises:
            FileNotFoundError: PDF文件不存在
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

        self._pdf_path = pdf_path
        self._markdown = ""
        self._tables: list[TableSummary] = []
        self._table_data: dict[str, tuple[list[dict], list[str]]] = {}
        self._page_count = 0
        self._parser_used = "none"

        # 解析文档
        self._parse_document()

    def _parse_document(self):
        """解析文档。"""
        # 尝试pdfplumber
        if self._try_pdfplumber():
            self._parser_used = "pdfplumber"
            return

        # 尝试PyPDF2
        if self._try_pypdf2():
            self._parser_used = "pypdf2"
            return

        # 尝试PyMuPDF
        if self._try_pymupdf():
            self._parser_used = "pymupdf"
            return

        logger.error("所有降级方案均失败")
        self._parser_used = "none"

    def _try_pdfplumber(self) -> bool:
        """尝试使用pdfplumber解析。"""
        try:
            import pdfplumber

            text_parts = []
            tables = []
            table_data_map = {}

            with pdfplumber.open(str(self._pdf_path)) as pdf:
                self._page_count = len(pdf.pages)

                for i, page in enumerate(pdf.pages):
                    # 提取文本
                    text = page.extract_text()
                    if text:
                        text_parts.append(f"<!-- Page {i+1} -->\n{text}")

                    # 提取表格
                    page_tables = page.extract_tables()
                    for j, table_data in enumerate(page_tables):
                        if table_data:
                            # 转换为表格摘要
                            headers = table_data[0] if table_data else []
                            table_ref = f"table_{len(tables)}"

                            tables.append(TableSummary(
                                table_ref=table_ref,
                                caption=None,
                                context_before="",
                                row_count=len(table_data) - 1,
                                col_count=len(headers),
                                table_type="unknown",
                                headers=headers if headers else None,
                                section_ref=None,
                                page_no=i + 1,
                                internal_ref=None,
                                is_financial=None,
                            ))

                            # 保存表格数据
                            data = []
                            for row in table_data[1:]:
                                if headers and len(row) == len(headers):
                                    data.append(dict(zip(headers, row)))
                            table_data_map[table_ref] = (data, headers)

            self._markdown = "\n\n".join(text_parts)
            self._tables = tables
            self._table_data = table_data_map

            logger.info(f"pdfplumber解析完成: {self._page_count} 页, {len(tables)} 表格")
            return True

        except ImportError:
            logger.debug("pdfplumber未安装")
            return False
        except Exception as exc:
            logger.warning(f"pdfplumber解析失败: {exc}")
            return False

    def _try_pypdf2(self) -> bool:
        """尝试使用PyPDF2解析。"""
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(str(self._pdf_path))
            self._page_count = len(reader.pages)

            text_parts = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    text_parts.append(f"<!-- Page {i+1} -->\n{text}")

            self._markdown = "\n\n".join(text_parts)
            self._tables = []
            self._table_data = {}

            logger.info(f"PyPDF2解析完成: {self._page_count} 页")
            return True

        except ImportError:
            logger.debug("PyPDF2未安装")
            return False
        except Exception as exc:
            logger.warning(f"PyPDF2解析失败: {exc}")
            return False

    def _try_pymupdf(self) -> bool:
        """尝试使用PyMuPDF（fitz）解析。"""
        try:
            import fitz  # PyMuPDF

            text_parts = []
            tables = []
            table_data_map = {}

            doc = fitz.open(str(self._pdf_path))
            self._page_count = len(doc)

            for i, page in enumerate(doc):
                # 提取文本
                text = page.get_text()
                if text:
                    text_parts.append(f"<!-- Page {i+1} -->\n{text}")

                # 提取表格（PyMuPDF 表格提取较复杂，这里只做基础文本提取）
                # 可以通过 page.find_tables() 获取表格，但需要额外处理

            doc.close()

            self._markdown = "\n\n".join(text_parts)
            self._tables = tables
            self._table_data = table_data_map

            logger.info(f"PyMuPDF解析完成: {self._page_count} 页")
            return True

        except ImportError:
            logger.debug("PyMuPDF未安装")
            return False
        except Exception as exc:
            logger.warning(f"PyMuPDF解析失败: {exc}")
            return False

    # ============ DocumentStore接口实现 ============

    def list_sections(self) -> list[SectionSummary]:
        """读取章节列表。"""
        # 降级方案无法精确提取章节，返回整个文档作为一个章节
        return [SectionSummary(
            ref="document",
            title=self._pdf_path.stem,
            level=0,
            parent_ref=None,
            preview=self._markdown[:200] if self._markdown else "",
            page_range=list(range(1, self._page_count + 1)),
            internal_ref=None,
        )]

    def list_tables(self) -> list[TableSummary]:
        """读取表格列表。"""
        return self._tables

    def read_section(self, ref: str) -> SectionContent:
        """按ref读取章节内容。"""
        if ref != "document":
            raise KeyError(f"章节不存在: {ref}")

        return SectionContent(
            ref="document",
            title=self._pdf_path.stem,
            content=self._markdown,
            tables=[t.table_ref for t in self._tables],
            word_count=len(self._markdown.split()),
            contains_full_text=True,
            page_range=list(range(1, self._page_count + 1)),
            internal_ref=None,
        )

    def read_table(self, table_ref: str) -> TableContent:
        """按ref读取表格内容。"""
        table = None
        for t in self._tables:
            if t.table_ref == table_ref:
                table = t
                break

        if table is None:
            raise KeyError(f"表格不存在: {table_ref}")

        # 获取表格数据
        data, columns = self._table_data.get(table_ref, ([], []))

        return TableContent(
            table_ref=table.table_ref,
            caption=table.caption,
            data_format="records",
            data=data,
            columns=columns if columns else None,
            row_count=table.row_count,
            col_count=table.col_count,
            section_ref=table.section_ref,
            table_type=table.table_type,
            page_no=table.page_no,
            internal_ref=table.internal_ref,
        )

    def search(self, query: str, within_ref: str | None = None) -> list[SearchHit]:
        """在文档中搜索关键词。"""
        hits = []

        if query.lower() in self._markdown.lower():
            # 提取上下文
            idx = self._markdown.lower().find(query.lower())
            start = max(0, idx - 200)
            end = min(len(self._markdown), idx + len(query) + 200)
            snippet = self._markdown[start:end]

            hits.append(SearchHit(
                ref="document",
                title=self._pdf_path.stem,
                snippet=snippet,
                score=1.0,
                section_ref="document",
            ))

        return hits

    def get_section_title(self, ref: str) -> str | None:
        """获取章节标题。"""
        if ref == "document":
            return self._pdf_path.stem
        return None

    @classmethod
    def supports(cls, source: Path) -> bool:
        """判断是否支持处理该文件。"""
        return source.suffix.lower() == ".pdf"

    @classmethod
    def get_parser_version(cls) -> str:
        """返回解析器版本。"""
        return cls.PARSER_VERSION
