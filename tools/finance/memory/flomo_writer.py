"""
flomo Writer - 将投资分析结果写入 flomo
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..data_context import DataContext

logger = logging.getLogger(__name__)


def write_to_flomo(ctx: "DataContext", report: str) -> bool:
    """将投资分析结果写入 flomo

    Args:
        ctx: DataContext 实例
        report: 完整分析报告

    Returns:
        写入信息字典，如果失败返回 None
    """
    try:
        content = _build_flomo_content(ctx, report)
        tags = ["#hermes/投资研究", f"#{ctx.company_name}"]

        logger.info(f"准备写入 flomo: {ctx.company_name}")

        # 返回写入信息，由 Agent 层调用 MCP 工具
        return {
            "action": "flomo_memo_create",
            "content": content,
            "tags": tags,
        }

    except Exception as e:
        logger.error(f"flomo 写入准备失败: {e}")
        return None


def _build_flomo_content(ctx: "DataContext", report: str) -> str:
    """构建 flomo 笔记内容"""
    
    # 提取关键发现
    key_findings = _extract_key_findings(report)
    
    # 提取投资逻辑
    investment_logic = _extract_investment_logic(report)

    return f"""**{ctx.company_name}（{ctx.ticker}）投资研究**

**市场**: {ctx.market.upper()} | **数据质量**: {ctx.data_quality}

**关键发现**：
{key_findings}

**投资逻辑**：
{investment_logic}

**数据来源**：
- 财报: {ctx.filing_source}
- Wind: {ctx.wind_source}

#hermes/投资研究 #{ctx.company_name}
"""


def _extract_key_findings(report: str) -> str:
    """从报告中提取关键发现"""
    findings = []
    
    # 查找包含数字的关键句子
    lines = report.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 查找包含百分比或金额的行
        if any(char in line for char in ["%", "亿", "万", "+", "-"]):
            if len(line) < 100:  # 排除过长的行
                findings.append(f"- {line}")
    
    # 返回前 5 条
    return "\n".join(findings[:5]) if findings else "暂无关键发现"


def _extract_investment_logic(report: str) -> str:
    """从报告中提取投资逻辑"""
    logic = []
    
    # 查找包含投资相关关键词的行
    keywords = ["核心", "优势", "风险", "增长", "驱动", "战略", "前景"]
    lines = report.split("\n")
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        if any(keyword in line for keyword in keywords):
            if len(line) < 100:
                logic.append(f"- {line}")
    
    return "\n".join(logic[:3]) if logic else "暂无投资逻辑"
