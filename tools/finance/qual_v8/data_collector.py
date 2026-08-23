"""
数据收集模块（v9 Phase 4：从 workflow.py 拆出）。

负责 Wind 数据解析、财报原文处理、搜索结果收集、DataContext 组装。
属于 Service 层的"数据准备"职责。

设计参照：dayu services/startup_preparation.py（启动期数据准备）
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def collect_data(
    ticker: str,
    company_name: str,
    market: str,
    facets: Any,
    wind_data: dict | None = None,
    filing_data: dict | None = None,
    search_results: list[dict] | None = None,
) -> Any:
    """数据收集：组装 DataContext（从 workflow.py _collect_data 提取）。

    Args:
        ticker: 股票代码
        company_name: 公司名称
        market: 市场类型
        facets: 类型推断结果
        wind_data: Wind MCP 数据（可选）
        filing_data: 财报原文数据（可选）
        search_results: 搜索结果（可选）

    Returns:
        DataContext
    """
    logger.info("数据收集: 开始")

    # ---- 处理 Wind 数据 ----
    wind = None
    wind_source: str = "unavailable"

    if wind_data:
        try:
            from ..workflow import WindData
            wind = WindData(
                quote=wind_data.get("quote"),
                valuation=wind_data.get("valuation"),
                income=wind_data.get("income"),
                balance=wind_data.get("balance"),
                cashflow=wind_data.get("cashflow"),
                news=wind_data.get("news"),
                industry=wind_data.get("industry"),
                _year_labels=wind_data.get("_year_labels"),
            )
            wind_source = "wind"
            logger.info("数据收集: Wind 数据已加载")
        except Exception as e:
            logger.warning(f"数据收集: Wind 数据解析失败: {e}")
            wind_source = "fallback"

    # ---- 处理财报原文数据 ----
    filing = None
    filing_source: str = "unavailable"

    if filing_data:
        try:
            sections, tables = process_filing(filing_data, market)
            from ..workflow import FilingData
            filing = FilingData(
                sections=sections,
                tables=tables,
                metadata=filing_data.get("metadata", {}),
                source="filing",
            )
            filing_source = "filing"
            logger.info(f"数据收集: 财报已处理 {len(sections)} 章节, {len(tables)} 表格")
        except Exception as e:
            logger.warning(f"数据收集: 财报处理失败: {e}")
            filing_source = "fallback"

    # ---- 处理搜索结果 ----
    sr_list = []
    if search_results:
        from ..workflow import SearchResult
        for sr in search_results:
            if isinstance(sr, dict):
                sr_list.append(SearchResult(
                    query=sr.get("query", ""),
                    results=sr.get("results", []),
                    source=sr.get("source", "anysearch"),
                ))
            elif hasattr(sr, 'query'):
                sr_list.append(sr)

    # ---- 组装 DataContext ----
    from ..workflow import DataContext
    ctx = DataContext(
        ticker=ticker,
        company_name=company_name,
        market=market,
        filing=filing,
        wind=wind,
        search_results=sr_list,
        facets=facets,
        filing_source=filing_source,
        wind_source=wind_source,
    )

    logger.info(f"数据收集完成: data_quality={ctx.data_quality}")
    return ctx


def process_filing(
    filing_data: dict,
    market: str,
) -> tuple[dict[str, str], list[dict]]:
    """使用 processors 模块处理财报原文（从 workflow.py _process_filing 提取）。

    Args:
        filing_data: 财报原文数据
        market: 市场类型

    Returns:
        (sections, tables)
    """
    from ..processors import (
        CNSectionsProcessor,
        FinancialTableExtractor,
        HKSectionsProcessor,
        SectionIdentifier,
        US8KSectionsProcessor,
        US10KSectionsProcessor,
    )

    sections = filing_data.get("sections", {})
    tables = []
    metadata = filing_data.get("metadata", {})
    filing_type = metadata.get("filing_type", "")

    if market in ("cn", "hk"):
        processor = CNSectionsProcessor() if market == "cn" else HKSectionsProcessor()
        result = processor.process(sections)
        sections = result.get("sections", sections)
        tables = result.get("tables", [])
    elif market == "us":
        if "10-K" in filing_type:
            result = US10KSectionsProcessor().process(sections)
        elif "8-K" in filing_type:
            result = US8KSectionsProcessor().process(sections)
        else:
            result = US10KSectionsProcessor().process(sections)
        sections = result.get("sections", sections)
        tables = result.get("tables", [])

    # 提取财务表格
    table_extractor = FinancialTableExtractor()
    extracted_tables = table_extractor.extract(sections)
    tables.extend(extracted_tables)

    # 识别章节
    identifier = SectionIdentifier()
    for name, content in sections.items():
        section_type = identifier.identify(content)
        if section_type:
            sections[name] = f"[{section_type}]\n{content}"

    return sections, tables
