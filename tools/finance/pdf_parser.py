"""
PDF Parser - 统一解析接口

根据市场类型自动选择解析器:
- 美股(us): DoclingParser (原生 HTML 解析，质量最高)
- A股(cn)/港股(hk): MinerUParser (CJK 最强，中文财报支持最好)
"""

import logging
from pathlib import Path
from typing import Literal, Optional

from .parsers.base import BaseParser, ParsedFiling
from .parsers.docling_parser import DoclingParser
from .parsers.mineru_parser import MinerUParser

logger = logging.getLogger(__name__)

# 全局解析器实例缓存
_parsers: dict[str, BaseParser] = {}


def get_parser(market: Literal["us", "cn", "hk"]) -> BaseParser:
    """根据市场类型获取解析器实例

    Args:
        market: 市场类型 (us/cn/hk)

    Returns:
        对应市场的解析器实例
    """
    if market not in _parsers:
        if market == "us":
            _parsers[market] = DoclingParser()
        else:
            _parsers[market] = MinerUParser()

    return _parsers[market]


def parse_filing(
    pdf_path: Path,
    ticker: str,
    form_type: str,
    market: Literal["us", "cn", "hk"] = "us",
) -> ParsedFiling:
    """解析财报 PDF

    Args:
        pdf_path: PDF 文件路径
        ticker: 股票代码
        form_type: 表单类型 (如 10-K, 20-F, 年报)
        market: 市场类型

    Returns:
        ParsedFiling 对象，包含 markdown 和 metadata
    """
    parser = get_parser(market)
    parsed = parser.parse(pdf_path, ticker, form_type)
    logger.info(
        f"解析完成: {ticker} {form_type}, "
        f"markdown 长度={len(parsed.markdown)}, "
        f"表格数={len(parsed.tables)}"
    )
    return parsed
