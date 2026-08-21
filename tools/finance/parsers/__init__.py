"""Hermes 解析器模块。

支持：
- DoclingParser（美股，支持多种格式）
- MinerUParser（A股/港股，FastAPI服务，支持token认证）
- FallbackParser（降级方案）

使用方法：
    from hermes_tools.finance.parsers import DoclingParser, MinerUParser, FallbackParser
    from hermes_tools.finance.parsers import DocumentStore, SectionSummary, TableSummary
    from hermes_tools.finance.parsers import create_parser, MinerUConfig

配置token认证：
    config = MinerUConfig(
        api_url="http://localhost:8080",
        token="your_jwt_token_here",
    )
    parser = create_parser(pdf_path, config=config)
"""

from .docling_parser import DoclingParser
from .document_store import (
    # 抽象基类
    DocumentStore,
    SearchHit,
    SectionContent,
    # 数据类
    SectionSummary,
    TableContent,
    TableSummary,
)
from .fallback_parser import FallbackParser
from .financial_enhancer import relabel_table_content, relabel_tables
from .mineru_parser import MinerUConfig, MinerUParser
from .parser_router import check_mineru_health, create_parser, get_parser_info

__all__ = [
    # 抽象基类
    "DocumentStore",

    # 数据类
    "SectionSummary",
    "TableSummary",
    "SectionContent",
    "TableContent",
    "SearchHit",

    # 解析器
    "DoclingParser",
    "MinerUParser",
    "FallbackParser",

    # 配置
    "MinerUConfig",

    # 金融标注
    "relabel_tables",
    "relabel_table_content",

    # 路由
    "create_parser",
    "check_mineru_health",
    "get_parser_info",
]
