"""
Filing Service - 财报查询服务

实现 Gate 2.14:
- list_available_filings(): 列出可用财报
- get_filing_section(): 获取指定章节
- search_filing_sections(): 搜索章节内容
- get_filing_table(): 获取指定表格
- download_with_cache(): 带缓存的下载

整合下载器、解析器、处理器的统一入口。
"""

import logging
from pathlib import Path
from typing import Literal

from .downloaders.base import FilingInfo
from .filing_downloader import list_filings as _list_filings
from .parsers.base import ParsedFiling
from .pdf_parser import parse_filing as _parse_filing
from .processors.base import BaseProcessor
from .processors.cn_sections import CNSectionsProcessor
from .processors.hk_sections import HKSectionsProcessor
from .processors.section_identifier import SectionIdentifier
from .processors.table_extractor import FinancialTableExtractor
from .processors.us_8k_sections import US8KSectionsProcessor
from .processors.us_10k_sections import US10KSectionsProcessor
from .processors.us_10q_sections import US10QSectionsProcessor
from .processors.us_20f_sections import US20FSectionsProcessor

logger = logging.getLogger(__name__)

# 处理器缓存
_processor_cache: dict[str, BaseProcessor] = {}


def _get_processor(market: str, form_type: str) -> BaseProcessor:
    """根据市场和表单类型获取处理器

    Args:
        market: 市场类型 (us/cn/hk)
        form_type: 表单类型

    Returns:
        对应的处理器实例
    """
    cache_key = f"{market}_{form_type}"
    if cache_key in _processor_cache:
        return _processor_cache[cache_key]

    processor = None

    if market == "cn":
        processor = CNSectionsProcessor()
    elif market == "hk":
        processor = HKSectionsProcessor()
    elif market == "us":
        ft = form_type.upper()
        if ft in ("10-K", "10-K/A"):
            processor = US10KSectionsProcessor()
        elif ft in ("10-Q", "10-Q/A"):
            processor = US10QSectionsProcessor()
        elif ft in ("20-F", "20-F/A"):
            processor = US20FSectionsProcessor()
        elif ft in ("8-K", "8-K/A"):
            processor = US8KSectionsProcessor()
        else:
            processor = SectionIdentifier()
    else:
        processor = SectionIdentifier()

    _processor_cache[cache_key] = processor
    return processor


class FilingService:
    """财报查询服务

    提供统一的财报查询、下载、解析、章节提取接口。
    整合了下载器、解析器和处理器的功能。
    """

    def __init__(self, cache_base_dir: Path | None = None):
        """
        Args:
            cache_base_dir: 缓存基础目录
        """
        if cache_base_dir is None:
            cache_base_dir = Path.home() / ".hermes" / "workspace" / "filings"
        self.cache_base_dir = Path(cache_base_dir)
        self.cache_base_dir.mkdir(parents=True, exist_ok=True)

        # 解析结果缓存
        self._parsed_cache: dict[str, ParsedFiling] = {}

    def list_available_filings(
        self,
        ticker: str,
        market: Literal["us", "cn", "hk"],
        form_types: list[str] | None = None,
        limit: int = 10,
    ) -> list[FilingInfo]:
        """列出可用的财报文件

        Args:
            ticker: 股票代码
            market: 市场类型
            form_types: 过滤的表单类型列表
            limit: 最大返回数量

        Returns:
            FilingInfo 列表
        """
        return _list_filings(ticker, market, form_types, limit)

    def download_with_cache(
        self,
        ticker: str,
        filing: FilingInfo,
    ) -> Path:
        """带缓存的下载（HGF 遗留①：改用真实下载器 download_filing）

        Args:
            ticker: 股票代码
            filing: FilingInfo 对象

        Returns:
            PDF 文件路径
        """
        from .filing_downloader import _create_downloader

        cache_dir = self.cache_base_dir / ticker
        cache_dir.mkdir(parents=True, exist_ok=True)
        # 优先用缓存
        if filing.cache_filename():
            cached = cache_dir / filing.cache_filename()
            if cached.exists():
                logger.info(f"使用缓存财报: {cached}")
                return cached
        try:
            downloader = _create_downloader(filing.market)
            pdf_path = downloader.download_filing(filing)
            if pdf_path:
                return Path(pdf_path)
        except Exception as e:
            logger.error(f"下载财报失败: {e}")
        return cache_dir / (filing.cache_filename() or "unknown.pdf")

    def _get_or_parse(
        self,
        ticker: str,
        form_type: str,
        market: Literal["us", "cn", "hk"],
        pdf_path: Path | None = None,
        filing: FilingInfo | None = None,
    ) -> ParsedFiling:
        """获取解析结果（带缓存）

        Args:
            ticker: 股票代码
            form_type: 表单类型
            market: 市场类型
            pdf_path: PDF 文件路径
            filing: FilingInfo 对象

        Returns:
            ParsedFiling 对象
        """
        cache_key = f"{ticker}_{form_type}_{market}"

        if cache_key in self._parsed_cache:
            logger.debug(f"解析缓存命中: {cache_key}")
            return self._parsed_cache[cache_key]

        # 如果没有 PDF 路径，先下载
        if pdf_path is None:
            if filing is None:
                filings = self.list_available_filings(ticker, market, [form_type], limit=1)
                if not filings:
                    raise FileNotFoundError(f"未找到 {ticker} 的 {form_type} 财报")
                filing = filings[0]
            pdf_path = self.download_with_cache(ticker, filing)

        # 解析
        parsed = _parse_filing(pdf_path, ticker, form_type, market)
        self._parsed_cache[cache_key] = parsed
        return parsed

    def get_filing_section(
        self,
        ticker: str,
        form_type: str,
        section_name: str,
        market: Literal["us", "cn", "hk"] = "us",
        pdf_path: Path | None = None,
    ) -> str | None:
        """获取财报的指定章节

        Args:
            ticker: 股票代码
            form_type: 表单类型
            section_name: 章节名称
            market: 市场类型
            pdf_path: PDF 文件路径（可选）

        Returns:
            章节内容文本，未找到返回 None
        """
        try:
            parsed = self._get_or_parse(ticker, form_type, market, pdf_path)
            processor = _get_processor(market, form_type)
            sections = processor.extract_sections(parsed.markdown)

            # 精确匹配
            if section_name in sections:
                return sections[section_name]

            # 模糊匹配
            section_lower = section_name.lower()
            for name, content in sections.items():
                if section_lower in name.lower() or name.lower() in section_lower:
                    return content

            logger.warning(f"未找到章节: {section_name} (可用: {list(sections.keys())})")
            return None

        except Exception as e:
            logger.error(f"获取章节失败: {e}")
            return None

    def search_filing_sections(
        self,
        ticker: str,
        form_type: str,
        query: str,
        market: Literal["us", "cn", "hk"] = "us",
        pdf_path: Path | None = None,
        max_results: int = 5,
    ) -> list[dict]:
        """搜索章节内容

        Args:
            ticker: 股票代码
            form_type: 表单类型
            query: 搜索关键词
            market: 市场类型
            pdf_path: PDF 文件路径（可选）
            max_results: 最大返回数量

        Returns:
            匹配结果列表，每个包含 section_name, snippet, relevance
        """
        results = []

        try:
            parsed = self._get_or_parse(ticker, form_type, market, pdf_path)
            processor = _get_processor(market, form_type)
            sections = processor.extract_sections(parsed.markdown)

            query_lower = query.lower()

            for section_name, content in sections.items():
                content_lower = content.lower()
                if query_lower in content_lower:
                    # 找到关键词位置，提取片段
                    idx = content_lower.index(query_lower)
                    start = max(0, idx - 200)
                    end = min(len(content), idx + len(query) + 200)
                    snippet = content[start:end]

                    # 计算相关度（基于出现次数）
                    count = content_lower.count(query_lower)
                    relevance = min(count / 10.0, 1.0)

                    results.append({
                        "section_name": section_name,
                        "snippet": snippet,
                        "occurrences": count,
                        "relevance": relevance,
                    })

            # 按相关度排序
            results.sort(key=lambda x: x["relevance"], reverse=True)
            results = results[:max_results]

        except Exception as e:
            logger.error(f"搜索章节失败: {e}")

        return results

    def get_filing_table(
        self,
        ticker: str,
        form_type: str,
        table_type: str,
        market: Literal["us", "cn", "hk"] = "us",
        pdf_path: Path | None = None,
    ) -> dict | None:
        """获取财报的指定表格

        Args:
            ticker: 股票代码
            form_type: 表单类型
            table_type: 表格类型 (income_statement/balance_sheet/cash_flow/segment)
            market: 市场类型
            pdf_path: PDF 文件路径（可选）

        Returns:
            表格数据字典，未找到返回 None
        """
        try:
            parsed = self._get_or_parse(ticker, form_type, market, pdf_path)

            # 先用专用处理器
            processor = _get_processor(market, form_type)
            tables = processor.extract_tables(parsed.markdown)

            # 查找匹配的表格
            for table in tables:
                if table.get("type") == table_type:
                    return table

            # 如果专用处理器没找到，用通用表格提取器
            extractor = FinancialTableExtractor()
            general_tables = extractor.extract_tables(parsed.markdown)

            for table in general_tables:
                if table.get("type") == table_type:
                    return table

            logger.warning(f"未找到表格: {table_type}")
            return None

        except Exception as e:
            logger.error(f"获取表格失败: {e}")
            return None

    def clear_cache(self):
        """清除解析结果缓存"""
        self._parsed_cache.clear()
        logger.info("解析缓存已清除")
