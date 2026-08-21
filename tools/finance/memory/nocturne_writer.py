"""
nocturne Writer - 将投资分析结果写入 nocturne 实体记忆
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..data_context import DataContext

logger = logging.getLogger(__name__)


def write_to_nocturne(ctx: "DataContext", report: str) -> bool:
    """将投资分析结果写入 nocturne 实体记忆

    Args:
        ctx: DataContext 实例
        report: 完整分析报告

    Returns:
        写入信息字典，如果失败返回 None
    """
    try:
        uri = f"core://{ctx.ticker}-analysis"
        content = _build_nocturne_content(ctx, report)
        title = f"{ctx.ticker}-analysis"
        disclosure = f"When discussing {ctx.ticker} or {ctx.company_name}"

        logger.info(f"准备写入 nocturne: {uri}")

        # 返回写入信息，由 Agent 层调用 MCP 工具
        return {
            "action": "nocturne_create_memory",
            "parent_uri": "core://",
            "content": content,
            "title": title,
            "disclosure": disclosure,
            "priority": 2,
            "check_existing": True,  # 需要先检查是否存在
        }

    except Exception as e:
        logger.error(f"nocturne 写入准备失败: {e}")
        return None


def _build_nocturne_content(ctx: "DataContext", report: str) -> str:
    """构建 nocturne 记忆内容"""

    # 提取关键指标
    key_metrics = ""
    if ctx.wind and ctx.wind.quote:
        key_metrics += f"- 股价: {ctx.wind.quote.get('price', 'N/A')}\n"
    if ctx.wind and ctx.wind.valuation:
        key_metrics += f"- PE: {ctx.wind.valuation.get('pe_ttm', 'N/A')}\n"
        key_metrics += f"- PB: {ctx.wind.valuation.get('pb', 'N/A')}\n"

    # 提取业务模型
    business_model = ""
    if ctx.facets and ctx.facets.business_model:
        business_model = ", ".join(ctx.facets.business_model)

    return f"""{ctx.company_name}（{ctx.ticker}）投资分析

**市场**: {ctx.market.upper()}
**业务模型**: {business_model}
**数据质量**: {ctx.data_quality}

**关键指标**:
{key_metrics}

**分析摘要**:
{report[:1500]}

**数据来源**:
- 财报: {ctx.filing_source}
- Wind: {ctx.wind_source}
"""
