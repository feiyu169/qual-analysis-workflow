"""金融语义标注。

对应Dayu的FinsDoclingProcessor.relabel_tables()。
提供独立的relabel_tables()方法，可被DocumentStore调用。

功能：
- 识别财务报表类型（资产负债表、利润表、现金流量表）
- 为表格添加金融标签（is_financial、table_type）
"""

from __future__ import annotations

import logging

from .document_store import TableContent, TableSummary

logger = logging.getLogger(__name__)

# ============ 财务报表关键词 ============

BALANCE_SHEET_KEYWORDS = [
    "资产负债表", "balance sheet", "资产总计", "负债合计", "所有者权益",
    "总资产", "总负债", "股东权益", "资产总额", "负债总额",
]

INCOME_STATEMENT_KEYWORDS = [
    "利润表", "income statement", "损益表", "营业利润", "净利润",
    "营业收入", "营业成本", "利润总额", "每股收益",
]

CASH_FLOW_KEYWORDS = [
    "现金流量表", "cash flow", "经营活动", "投资活动", "筹资活动",
    "现金及现金等价物", "期末现金余额",
]


def relabel_tables(tables: list[TableSummary], markdown: str = "") -> list[TableSummary]:
    """为表格添加金融语义标注。

    与Dayu的FinsDoclingProcessor.relabel_tables()签名兼容。

    识别并标注财务报表类型：
    - balance_sheet: 资产负债表
    - income_statement: 利润表
    - cash_flow: 现金流量表

    Args:
        tables: 原始表格摘要列表。
        markdown: 文档全文（可选，用于上下文分析）。

    Returns:
        标注后的表格摘要列表（is_financial和table_type字段已更新）。
    """
    enhanced_tables = []

    for table in tables:
        is_financial = False
        table_type = table.table_type

        # 策略1：检查表格标题
        if table.caption:
            caption_lower = table.caption.lower()

            if any(kw in caption_lower for kw in BALANCE_SHEET_KEYWORDS):
                table_type = "balance_sheet"
                is_financial = True
            elif any(kw in caption_lower for kw in INCOME_STATEMENT_KEYWORDS):
                table_type = "income_statement"
                is_financial = True
            elif any(kw in caption_lower for kw in CASH_FLOW_KEYWORDS):
                table_type = "cash_flow"
                is_financial = True

        # 策略2：检查表头
        if not is_financial and table.headers:
            headers_text = " ".join(table.headers).lower()

            if any(kw in headers_text for kw in BALANCE_SHEET_KEYWORDS):
                table_type = "balance_sheet"
                is_financial = True
            elif any(kw in headers_text for kw in INCOME_STATEMENT_KEYWORDS):
                table_type = "income_statement"
                is_financial = True
            elif any(kw in headers_text for kw in CASH_FLOW_KEYWORDS):
                table_type = "cash_flow"
                is_financial = True

        # 策略3：检查表格前的上下文
        if not is_financial and table.context_before:
            context_lower = table.context_before.lower()

            if any(kw in context_lower for kw in BALANCE_SHEET_KEYWORDS):
                table_type = "balance_sheet"
                is_financial = True
            elif any(kw in context_lower for kw in INCOME_STATEMENT_KEYWORDS):
                table_type = "income_statement"
                is_financial = True
            elif any(kw in context_lower for kw in CASH_FLOW_KEYWORDS):
                table_type = "cash_flow"
                is_financial = True

        # 创建增强后的表格摘要
        enhanced_tables.append(TableSummary(
            table_ref=table.table_ref,
            caption=table.caption,
            context_before=table.context_before,
            row_count=table.row_count,
            col_count=table.col_count,
            table_type=table_type,
            headers=table.headers,
            section_ref=table.section_ref,
            page_no=table.page_no,
            internal_ref=table.internal_ref,
            is_financial=is_financial,
        ))

    logger.info(f"金融标注完成: {sum(1 for t in enhanced_tables if t.is_financial)} 个财务表格")
    return enhanced_tables


def relabel_table_content(table_content: TableContent, markdown: str = "") -> TableContent:
    """为表格内容添加金融语义标注。

    对应Dayu的FinsDoclingProcessor.relabel_tables()的内容级标注。

    Args:
        table_content: 原始表格内容。
        markdown: 文档全文（可选）。

    Returns:
        标注后的表格内容（table_type字段已更新）。
    """
    # 创建临时TableSummary用于标注
    temp_summary = TableSummary(
        table_ref=table_content.table_ref,
        caption=table_content.caption,
        context_before="",
        row_count=table_content.row_count,
        col_count=table_content.col_count,
        table_type=table_content.table_type,
        headers=table_content.columns,
        section_ref=table_content.section_ref,
        page_no=table_content.page_no,
        internal_ref=table_content.internal_ref,
        is_financial=None,
    )

    # 执行标注
    enhanced_summary = relabel_tables([temp_summary], markdown)[0]

    # 返回增强后的表格内容
    return TableContent(
        table_ref=table_content.table_ref,
        caption=table_content.caption,
        data_format=table_content.data_format,
        data=table_content.data,
        columns=table_content.columns,
        row_count=table_content.row_count,
        col_count=table_content.col_count,
        section_ref=table_content.section_ref,
        table_type=enhanced_summary.table_type,
        page_no=table_content.page_no,
        internal_ref=table_content.internal_ref,
    )
