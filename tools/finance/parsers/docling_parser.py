"""Docling解析器（美股）。

继承DocumentStore，实现9个核心接口。
使用docling_runtime管理设备和后端。

支持文件类型：pdf, docx, pptx, xlsx, html, htm, md
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from .document_store import (
    DocumentStore,
    SectionSummary,
    TableSummary,
    SectionContent,
    TableContent,
    SearchHit,
)
from .docling_runtime import (
    resolve_docling_device_name,
    run_docling_pdf_conversion,
    convert_pdf_bytes_with_docling,
    DoclingRuntimeInitializationError,
)

logger = logging.getLogger(__name__)

# ============ 支持的文件类型 ============

DOCLING_SUPPORTED_TYPES = {
    ".pdf",           # PDF文件
    ".docx",          # Word文件
    ".pptx",          # PowerPoint文件
    ".xlsx",          # Excel文件
    ".html",          # HTML文件
    ".htm",           # HTML文件
    ".md",            # Markdown文件
}


class DoclingParser(DocumentStore):
    """Docling解析器。
    
    对应Dayu的DoclingProcessor。
    使用docling_runtime管理设备和后端。
    """
    
    PARSER_VERSION = "hermes_docling_parser_v2.5.0"
    
    def __init__(self, pdf_path: Path):
        """初始化解析器。
        
        内部调用：
        - resolve_docling_device_name(): 获取设备名
        - run_docling_pdf_conversion(): 执行PDF转换
        
        Args:
            pdf_path: PDF文件路径
            
        Raises:
            FileNotFoundError: PDF文件不存在
            RuntimeError: Docling解析失败
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")
        
        self._pdf_path = pdf_path
        self._document = None
        self._sections: list[SectionSummary] = []
        self._tables: list[TableSummary] = []
        self._section_map: dict[str, SectionSummary] = {}
        self._table_map: dict[str, TableSummary] = {}
        self._page_count = 0
        
        # 解析文档
        self._parse_document()
    
    def _parse_document(self):
        """解析文档，构建索引。"""
        try:
            # 获取设备配置
            device = resolve_docling_device_name()
            logger.info(f"Docling设备: {device}")
            
            # 执行PDF转换
            result = run_docling_pdf_conversion(str(self._pdf_path))
            self._document = result.document
            
            # 获取页面数
            self._page_count = self._document.num_pages()
            
            # 构建章节索引
            self._build_sections()
            
            # 构建表格索引
            self._build_tables()
            
            logger.info(
                f"文档解析完成: {len(self._sections)} 章节, "
                f"{len(self._tables)} 表格"
            )
            
        except DoclingRuntimeInitializationError as exc:
            raise RuntimeError(f"Docling初始化失败: {exc}") from exc
        except Exception as exc:
            logger.error(f"文档解析失败: {exc}")
            raise RuntimeError(f"Docling解析失败: {exc}") from exc
    
    def _build_sections(self):
        """构建章节索引。"""
        if self._document is None:
            return
        
        from docling.datamodel.document import DocItemLabel
        
        # 从docling文档中提取章节
        # 遍历 texts 列表，按 heading 识别章节
        current_section = None
        section_idx = 0
        
        for item in self._document.texts:
            label = item.label if hasattr(item, 'label') else None
            text = item.text if hasattr(item, 'text') else ''
            
            # 获取页码
            page_no = None
            if hasattr(item, 'prov') and item.prov:
                page_no = item.prov[0].page_no if item.prov else None
            
            # 判断是否为标题
            is_heading = False
            if label in (DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER):
                is_heading = True
            
            if is_heading and text.strip():
                ref = f"section_{section_idx}"
                section = SectionSummary(
                    ref=ref,
                    title=text.strip(),
                    level=0,
                    parent_ref=None,
                    preview=text[:200] if text else "",
                    page_range=[page_no] if page_no else [],
                    internal_ref=None,
                )
                self._sections.append(section)
                self._section_map[ref] = section
                current_section = section
                section_idx += 1
    
    def _build_tables(self):
        """构建表格索引。"""
        if self._document is None:
            return
        
        for idx, table_item in enumerate(self._document.tables):
            table_ref = f"table_{idx}"
            
            # 获取表格数据
            table_data = table_item.data if hasattr(table_item, 'data') else None
            
            # 获取页码
            page_no = None
            if hasattr(table_item, 'prov') and table_item.prov:
                page_no = table_item.prov[0].page_no if table_item.prov else None
            
            # 提取表头
            headers = []
            if table_data and hasattr(table_data, 'table_cells'):
                header_cells = [c for c in table_data.table_cells if c.column_header]
                if header_cells:
                    # 按列排序
                    header_cells.sort(key=lambda c: c.start_col_offset_idx)
                    headers = [c.text for c in header_cells]
            
            table = TableSummary(
                table_ref=table_ref,
                caption=None,
                context_before="",
                row_count=table_data.num_rows if table_data and hasattr(table_data, 'num_rows') else 0,
                col_count=table_data.num_cols if table_data and hasattr(table_data, 'num_cols') else 0,
                table_type="financial" if headers else "unknown",
                headers=headers if headers else None,
                section_ref=None,
                page_no=page_no,
                internal_ref=None,
                is_financial=None,
            )
            self._tables.append(table)
            self._table_map[table_ref] = table
    
    # ============ DocumentStore接口实现 ============
    
    def list_sections(self) -> list[SectionSummary]:
        """读取章节列表。"""
        return self._sections
    
    def list_tables(self) -> list[TableSummary]:
        """读取表格列表。"""
        return self._tables
    
    def read_section(self, ref: str) -> SectionContent:
        """按ref读取章节内容。"""
        section = self._section_map.get(ref)
        if section is None:
            raise KeyError(f"章节不存在: {ref}")
        
        content = self._extract_section_content(ref)
        
        return SectionContent(
            ref=section.ref,
            title=section.title,
            content=content,
            tables=[t.table_ref for t in self._tables if t.section_ref == ref],
            word_count=len(content.split()),
            contains_full_text=True,
            page_range=section.page_range,
            internal_ref=section.internal_ref,
        )
    
    def read_table(self, table_ref: str) -> TableContent:
        """按ref读取表格内容。"""
        table = self._table_map.get(table_ref)
        if table is None:
            raise KeyError(f"表格不存在: {table_ref}")
        
        data, columns = self._extract_table_content(table_ref)
        
        return TableContent(
            table_ref=table.table_ref,
            caption=table.caption,
            data_format="records",
            data=data,
            columns=columns,
            row_count=table.row_count,
            col_count=table.col_count,
            section_ref=table.section_ref,
            table_type=table.table_type,
            page_no=table.page_no,
            internal_ref=table.internal_ref,
        )
    
    def search(self, query: str, within_ref: Optional[str] = None) -> list[SearchHit]:
        """在文档中搜索关键词。"""
        hits = []
        
        if within_ref:
            sections = [s for s in self._sections if s.ref == within_ref]
        else:
            sections = self._sections
        
        for section in sections:
            content = self._extract_section_content(section.ref)
            if query.lower() in content.lower():
                snippet = self._extract_snippet(content, query)
                hits.append(SearchHit(
                    ref=section.ref,
                    title=section.title,
                    snippet=snippet,
                    score=1.0,
                    section_ref=section.ref,
                ))
        
        return hits
    
    def get_section_title(self, ref: str) -> Optional[str]:
        """获取章节标题。"""
        section = self._section_map.get(ref)
        return section.title if section else None
    
    @classmethod
    def supports(cls, source: Path) -> bool:
        """判断是否支持处理该文件。"""
        return source.suffix.lower() in DOCLING_SUPPORTED_TYPES
    
    @classmethod
    def get_parser_version(cls) -> str:
        """返回解析器版本。"""
        return cls.PARSER_VERSION
    
    # ============ 内部方法 ============
    
    def _extract_section_content(self, ref: str) -> str:
        """提取章节内容。"""
        # 实际实现需要从docling文档中提取
        return ""
    
    def _extract_table_content(self, table_ref: str) -> tuple[list[dict], list[str]]:
        """提取表格内容。"""
        # 实际实现需要从docling文档中提取
        return [], []
    
    def _extract_snippet(self, content: str, query: str, context_chars: int = 200) -> str:
        """提取搜索上下文。"""
        idx = content.lower().find(query.lower())
        if idx == -1:
            return ""
        
        start = max(0, idx - context_chars)
        end = min(len(content), idx + len(query) + context_chars)
        return content[start:end]
