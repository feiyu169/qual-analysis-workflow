"""
Data Collector - 数据收集器

负责收集投资分析所需的数据。
注意：Wind MCP 和搜索工具只能通过 Agent 层调用，
本模块接受预收集的数据并组装 DataContext。
"""

import logging

from .data_context import (
    DataContext,
    FacetResult,
    FilingData,
    SearchResult,
    WindData,
)

logger = logging.getLogger(__name__)


def collect_data(
    ticker: str,
    company_name: str,
    market: str,
    facets: FacetResult | None = None,
    wind_data: dict | None = None,
    filing_data: dict | None = None,
    search_results: list[dict] | None = None,
) -> DataContext:
    """收集投资分析所需的数据

    注意：此函数接受预收集的数据，不直接调用 MCP 工具。
    Agent 层负责调用 MCP 工具并将结果传递给此函数。

    Args:
        ticker: 股票代码
        company_name: 公司名称
        market: 市场类型 (us/cn/hk)
        facets: 类型推断结果（可选）
        wind_data: Wind MCP 数据（可选）
            {
                "quote": {...},
                "valuation": {...},
                "income": {...},
                "balance": {...},
                "cashflow": {...},
                "news": [...]
            }
        filing_data: 财报原文数据（可选）
            {
                "sections": {"章节名": "内容", ...},
                "tables": [...],
                "metadata": {...}
            }
        search_results: 搜索结果（可选）
            [{"query": "...", "results": [...], "source": "..."}]

    Returns:
        DataContext 对象

    Raises:
        DataCollectionError: 数据收集失败时抛出
    """
    logger.info(f"开始收集 {ticker} ({company_name}) 的数据")

    # 构建 WindData
    wind = None
    wind_source = "unavailable"
    if wind_data:
        wind = WindData(
            quote=wind_data.get("quote"),
            valuation=wind_data.get("valuation"),
            income=wind_data.get("income"),
            balance=wind_data.get("balance"),
            cashflow=wind_data.get("cashflow"),
            news=wind_data.get("news"),
        )
        wind_source = "wind"
        logger.info("Wind 数据已提供")
    else:
        logger.warning("未提供 Wind 数据")

    # 构建 FilingData
    filing = None
    filing_source = "unavailable"
    if filing_data:
        filing = FilingData(
            sections=filing_data.get("sections", {}),
            tables=filing_data.get("tables", []),
            metadata=filing_data.get("metadata", {}),
            source="filing",
        )
        filing_source = "filing"
        logger.info(f"财报数据已提供: {len(filing.sections)} 个章节")
    else:
        logger.warning("未提供财报数据")

    # 构建搜索结果
    search = []
    if search_results:
        for sr in search_results:
            search.append(SearchResult(
                query=sr.get("query", ""),
                results=sr.get("results", []),
                source=sr.get("source", "anysearch"),
            ))
        logger.info(f"搜索结果已提供: {len(search)} 条查询")

    # 构建 DataContext
    ctx = DataContext(
        ticker=ticker,
        company_name=company_name,
        market=market,
        facets=facets,
        wind=wind,
        filing=filing,
        search_results=search,
        wind_source=wind_source,
        filing_source=filing_source,
    )

    logger.info(
        f"数据收集完成: ticker={ticker}, "
        f"market={market}, "
        f"data_quality={ctx.data_quality}, "
        f"filing_source={filing_source}, "
        f"wind_source={wind_source}"
    )

    return ctx


def validate_data_context(ctx: DataContext) -> list[str]:
    """验证 DataContext 的完整性

    Args:
        ctx: DataContext 对象

    Returns:
        问题列表（空列表表示完全通过）
    """
    issues = []

    # 检查基本字段
    if not ctx.ticker:
        issues.append("缺少 ticker")
    if not ctx.company_name:
        issues.append("缺少 company_name")
    if not ctx.market:
        issues.append("缺少 market")

    # 检查数据质量
    if ctx.data_quality == "low":
        issues.append("数据质量为 low，缺少 Wind 和财报数据")

    # 检查 Wind 数据
    if ctx.wind is None:
        issues.append("缺少 Wind 数据")

    # 检查财报数据
    if ctx.filing is None:
        issues.append("缺少财报数据")
    elif not ctx.filing.sections:
        issues.append("财报数据中没有章节内容")

    return issues


def collect_wind_data_from_mcp_results(
    quote_result: dict,
    valuation_result: dict,
    income_result: dict | None = None,
    balance_result: dict | None = None,
    cashflow_result: dict | None = None,
    news_result: list | None = None,
) -> dict:
    """从 MCP 工具返回结果组装 Wind 数据

    此函数用于 Agent 层，将 MCP 工具的返回结果转换为
    collect_data 函数接受的格式。

    Args:
        quote_result: wind_stock_quote 返回结果
        valuation_result: wind_valuation 返回结果
        income_result: wind_financial_data(income) 返回结果（可选）
        balance_result: wind_financial_data(balance) 返回结果（可选）
        cashflow_result: wind_financial_data(cashflow) 返回结果（可选）
        news_result: wind_financial_news 返回结果（可选）

    Returns:
        Wind 数据字典，可直接传递给 collect_data 的 wind_data 参数
    """
    wind_data = {
        "quote": quote_result,
        "valuation": valuation_result,
        "income": income_result,
        "balance": balance_result,
        "cashflow": cashflow_result,
        "news": news_result,
    }

    # 过滤 None 值
    return {k: v for k, v in wind_data.items() if v is not None}
