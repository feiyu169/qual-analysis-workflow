"""统一文档模型接口定义。

与dayu-agent的DoclingProcessor完全同构，暴露9个核心接口。
所有接口签名、参数类型、返回值与Dayu 100%一致。

接口对照表：
1. __init__: 简化差异（Path替代Source，功能等价）
2. list_sections: 完全一致
3. list_tables: 完全一致
4. read_section: 完全一致
5. read_table: 完全一致
6. search: 完全一致（含within_ref参数）
7. get_section_title: 完全一致
8. supports: 简化差异（Path替代Source，功能等价）
9. get_parser_version: 完全一致
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ============ 数据类（与Dayu完全一致） ============

@dataclass(frozen=True)
class SectionSummary:
    """章节摘要。
    
    与Dayu的SectionSummary完全一致。
    
    Attributes:
        ref: 章节引用（唯一标识）
        title: 章节标题
        level: 层级（1=一级标题，2=二级标题...）
        parent_ref: 父章节引用
        preview: 预览文本（前200字符）
        page_range: 页码范围
        internal_ref: 内部引用（docling专用）
    """
    ref: str
    title: Optional[str]
    level: int
    parent_ref: Optional[str]
    preview: str
    page_range: Optional[list[int]]
    internal_ref: Optional[str]


@dataclass(frozen=True)
class TableSummary:
    """表格摘要。
    
    与Dayu的TableSummary完全一致。
    
    Attributes:
        table_ref: 表格引用（唯一标识）
        caption: 表格标题
        context_before: 表格前的上下文
        row_count: 行数
        col_count: 列数
        table_type: 表格类型（unknown/balance_sheet/income_statement/cash_flow）
        headers: 表头
        section_ref: 所属章节引用
        page_no: 页码
        internal_ref: 内部引用
        is_financial: 是否是财务表格
    """
    table_ref: str
    caption: Optional[str]
    context_before: str
    row_count: int
    col_count: int
    table_type: str
    headers: Optional[list[str]]
    section_ref: Optional[str]
    page_no: Optional[int]
    internal_ref: Optional[str]
    is_financial: Optional[bool]


@dataclass(frozen=True)
class SectionContent:
    """章节内容。
    
    与Dayu的SectionContent完全一致。
    
    Attributes:
        ref: 章节引用
        title: 章节标题
        content: 章节正文
        tables: 章节内的表格引用列表
        word_count: 字数
        contains_full_text: 是否包含全文
        page_range: 页码范围
        internal_ref: 内部引用
    """
    ref: str
    title: Optional[str]
    content: str
    tables: list[str]
    word_count: int
    contains_full_text: bool
    page_range: Optional[list[int]]
    internal_ref: Optional[str]


@dataclass(frozen=True)
class TableContent:
    """表格内容。
    
    与Dayu的TableContent完全一致。
    
    Attributes:
        table_ref: 表格引用
        caption: 表格标题
        data_format: 数据格式（"records" | "markdown"）
        data: 表格数据（records格式为list[dict]，markdown格式为str）
        columns: 列名
        row_count: 行数
        col_count: 列数
        section_ref: 所属章节引用
        table_type: 表格类型
        page_no: 页码
        internal_ref: 内部引用
    """
    table_ref: str
    caption: Optional[str]
    data_format: str
    data: list[dict] | str
    columns: Optional[list[str]]
    row_count: int
    col_count: int
    section_ref: Optional[str]
    table_type: str
    page_no: Optional[int]
    internal_ref: Optional[str]


@dataclass(frozen=True)
class SearchHit:
    """搜索命中。
    
    与Dayu的SearchHit完全一致。
    
    Attributes:
        ref: 命中位置引用
        title: 章节/表格标题
        snippet: 上下文片段
        score: 相关性得分
        section_ref: 所属章节引用
    """
    ref: str
    title: Optional[str]
    snippet: str
    score: float
    section_ref: Optional[str]


# ============ 抽象基类（9个核心接口，签名与Dayu一致） ============

class DocumentStore(ABC):
    """统一文档模型。
    
    与Dayu的DoclingProcessor完全同构。
    所有接口签名、参数类型、返回值与Dayu 100%一致。
    """
    
    @abstractmethod
    def list_sections(self) -> list[SectionSummary]:
        """读取章节列表。
        
        与Dayu的DoclingProcessor.list_sections()签名一致。
        
        Returns:
            章节摘要列表，按文档顺序排列。
        """
        ...
    
    @abstractmethod
    def list_tables(self) -> list[TableSummary]:
        """读取表格列表。
        
        与Dayu的DoclingProcessor.list_tables()签名一致。
        
        Returns:
            表格摘要列表，按文档顺序排列。
        """
        ...
    
    @abstractmethod
    def read_section(self, ref: str) -> SectionContent:
        """按ref读取章节内容。
        
        与Dayu的DoclingProcessor.read_section(ref)签名一致。
        
        Args:
            ref: 章节引用（来自list_sections返回的SectionSummary.ref）
            
        Returns:
            章节内容，包含正文、内嵌表格、字数等。
            
        Raises:
            KeyError: 章节不存在时抛出。
        """
        ...
    
    @abstractmethod
    def read_table(self, table_ref: str) -> TableContent:
        """按ref读取表格内容。
        
        与Dayu的DoclingProcessor.read_table(table_ref)签名一致。
        
        Args:
            table_ref: 表格引用（来自list_tables返回的TableSummary.table_ref）
            
        Returns:
            表格内容，包含结构化数据、列信息等。
            
        Raises:
            KeyError: 表格不存在时抛出。
        """
        ...
    
    @abstractmethod
    def search(self, query: str, within_ref: Optional[str] = None) -> list[SearchHit]:
        """在文档中搜索关键词。
        
        与Dayu的DoclingProcessor.search(query, within_ref)签名一致。
        
        Args:
            query: 搜索关键词。
            within_ref: 可选，限定在某个章节内搜索（ref来自list_sections）。
                       为None时搜索整个文档。
            
        Returns:
            搜索命中列表，按相关性排序。
        """
        ...
    
    @abstractmethod
    def get_section_title(self, ref: str) -> Optional[str]:
        """获取章节标题。
        
        与Dayu的DoclingProcessor.get_section_title(ref)签名一致。
        
        Args:
            ref: 章节引用。
            
        Returns:
            章节标题；ref不存在时返回None。
        """
        ...
    
    @classmethod
    @abstractmethod
    def supports(cls, source: Path) -> bool:
        """判断是否支持处理该文件。
        
        与Dayu的DoclingProcessor.supports(source)签名一致。
        
        Args:
            source: 文件路径。
            
        Returns:
            是否支持。
        """
        ...
    
    @classmethod
    @abstractmethod
    def get_parser_version(cls) -> str:
        """返回解析器版本。
        
        与Dayu的DoclingProcessor.get_parser_version()签名一致。
        
        Returns:
            版本字符串。
        """
        ...
    
    def get_full_text(self) -> str:
        """获取全文文本。
        
        非Dayu标准接口，为Hermes增强功能。
        
        Returns:
            文档全文文本。
        """
        sections = self.list_sections()
        parts = []
        for section in sections:
            content = self.read_section(section.ref)
            parts.append(content.content)
        return "\n\n".join(parts)
