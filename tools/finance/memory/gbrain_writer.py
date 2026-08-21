"""
GBrain Writer - 将投资分析结果写入 GBrain 知识图谱
"""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..data_context import DataContext

logger = logging.getLogger(__name__)


def write_to_gbrain(ctx: "DataContext", report: str) -> bool:
    """将投资分析结果写入 GBrain 知识图谱

    调用 GBrain MCP 的 put_page() 创建/更新页面。
    页面 slug 格式: investment/{ticker}-{date}

    Args:
        ctx: DataContext 实例
        report: 完整分析报告

    Returns:
        True 如果写入成功，False 如果失败
    """
    try:
        today = datetime.now(UTC).strftime("%Y%m%d")
        slug = f"investment/{ctx.ticker.lower()}-{today}"

        content = _build_gbrain_content(ctx, report)
        sector = _infer_sector(ctx)

        logger.info(f"写入 GBrain: slug={slug}")

        # 返回写入信息，由 Agent 层调用 MCP 工具
        return {
            "action": "gbrain_put_page",
            "slug": slug,
            "content": content,
            "tags": ["investment", ctx.ticker, sector],
        }

    except Exception as e:
        logger.error(f"GBrain 写入准备失败: {e}")
        return None


def _build_gbrain_content(ctx: "DataContext", report: str) -> str:
    """构建 GBrain 页面内容"""

    # 提取关键指标
    key_metrics = ""
    if ctx.wind and ctx.wind.quote:
        key_metrics = f"""
## 关键指标
- 股价: {ctx.wind.quote.get('price', 'N/A')}
- 成交量: {ctx.wind.quote.get('volume', 'N/A')}
"""

    if ctx.wind and ctx.wind.valuation:
        key_metrics += f"""
- PE(TTM): {ctx.wind.valuation.get('pe_ttm', 'N/A')}
- PB: {ctx.wind.valuation.get('pb', 'N/A')}
"""

    return f"""---
type: investment-analysis
ticker: {ctx.ticker}
company: {ctx.company_name}
market: {ctx.market}
date: {datetime.now(UTC).strftime('%Y-%m-%d')}
---

# {ctx.company_name} ({ctx.ticker}) 投资分析

{key_metrics}

## 分析摘要
{report[:2000]}

## 数据来源
- 财报来源: {ctx.filing_source}
- Wind 来源: {ctx.wind_source}
- 数据质量: {ctx.data_quality}
"""


def _infer_sector(ctx: "DataContext") -> str:
    """推断行业分类"""
    if ctx.facets and ctx.facets.business_model:
        models = ctx.facets.business_model
        if any("tech" in m for m in models):
            return "technology"
        elif any("finance" in m for m in models):
            return "finance"
        elif any("consumer" in m for m in models):
            return "consumer"
    return "other"
