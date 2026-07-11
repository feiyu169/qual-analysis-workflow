"""
SOTP (Sum-of-the-Parts) 分部估值模块

支持：
- 多业务分部独立估值
- 分部可比公司选择
- 集团费用和净负债调整
- 币种转换（港元/人民币）
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BusinessSegment:
    """业务分部"""
    name: str                          # 分部名称
    revenue: float                     # 分部收入（亿人民币）
    revenue_growth: float = 0.0        # 收入增速
    ebit_margin: float = 0.0           # EBIT利润率
    ebit: float = 0.0                  # EBIT
    ebitda: float = 0.0                # EBITDA
    comparable_multiple: float = 0.0   # 可比公司乘数
    multiple_type: str = "EV/Revenue"  # 乘数类型
    notes: str = ""


@dataclass
class SOTPResult:
    """SOTP 估值结果"""
    segments: list[BusinessSegment] = field(default_factory=list)
    segment_values: dict[str, float] = field(default_factory=dict)
    total_segment_value: float = 0.0
    corporate_expense: float = 0.0
    corporate_expense_pv: float = 0.0
    net_debt: float = 0.0
    equity_value: float = 0.0
    shares: float = 0.0
    value_per_share: float = 0.0
    value_per_share_hkd: float = 0.0   # 港元每股价值
    upside: float = 0.0
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def compute_sotp_valuation(
    segments: list[BusinessSegment],
    corporate_expense: float = 0.0,
    net_debt: float = 0.0,
    shares: float = 0.0,
    current_price: float = 0.0,
    discount_rate: float = 0.10,
    expense_growth: float = 0.03,
    fx_rate: float = 1.087,            # 港元/人民币汇率
) -> SOTPResult:
    """
    计算 SOTP 分部估值

    Args:
        segments: 业务分部列表
        corporate_expense: 集团费用（亿人民币）
        net_debt: 净负债（亿人民币，负值表示净现金）
        shares: 总股本（亿股）
        current_price: 当前股价（港元）
        discount_rate: 集团费用折现率
        expense_growth: 集团费用增长率
        fx_rate: 港元/人民币汇率

    Returns:
        SOTPResult 估值结果
    """
    result = SOTPResult(
        segments=segments,
        corporate_expense=corporate_expense,
        net_debt=net_debt,
        shares=shares,
    )

    # 1. 计算各分部估值
    for seg in segments:
        if seg.multiple_type == "EV/EBITDA":
            if seg.ebitda <= 0:
                result.warnings.append(f"{seg.name}: EBITDA 为负，无法计算 EV/EBITDA")
                continue
            seg_value = seg.ebitda * seg.comparable_multiple
        elif seg.multiple_type == "EV/Revenue":
            seg_value = seg.revenue * seg.comparable_multiple
        else:
            seg_value = seg.revenue * seg.comparable_multiple
            result.warnings.append(f"未知乘数类型: {seg.multiple_type}")

        result.segment_values[seg.name] = seg_value
        result.total_segment_value += seg_value
        logger.info(f"SOTP 分部 {seg.name}: {seg_value:.1f}亿")

    # 2. 集团费用折现（永续增长模型）
    if corporate_expense > 0:
        if discount_rate > expense_growth:
            result.corporate_expense_pv = corporate_expense / (discount_rate - expense_growth)
        else:
            result.corporate_expense_pv = corporate_expense * 10
            result.warnings.append("折现率 <= 增长率，使用简化处理（10倍费用）")

        result.assumptions.append(
            f"集团费用: {corporate_expense:.1f}亿，折现率: {discount_rate:.0%}，"
            f"增长率: {expense_growth:.0%}，现值: {result.corporate_expense_pv:.1f}亿"
        )

    # 3. 计算股权价值
    result.equity_value = (
        result.total_segment_value
        - result.corporate_expense_pv
        - net_debt
    )

    # 4. 计算每股价值（人民币）
    if shares > 0:
        result.value_per_share = result.equity_value / shares

    # 5. 转换为港元
    result.value_per_share_hkd = result.value_per_share * fx_rate

    # 6. 计算上行空间
    if current_price > 0 and result.value_per_share_hkd > 0:
        result.upside = (result.value_per_share_hkd - current_price) / current_price

    logger.info(
        f"SOTP 估值完成: 分部合计={result.total_segment_value:.1f}亿, "
        f"股权价值={result.equity_value:.1f}亿, "
        f"每股={result.value_per_share:.2f}元, "
        f"港元={result.value_per_share_hkd:.2f}元"
    )

    return result


def format_sotp_for_report(result: SOTPResult) -> str:
    """格式化 SOTP 结果为报告文本"""
    lines = ["## SOTP 分部估值\n"]

    # 分部估值表
    lines.append("| 分部 | 收入 | 乘数 | 估值 |")
    lines.append("|------|------|------|------|")

    for seg in result.segments:
        seg_value = result.segment_values.get(seg.name, 0)
        lines.append(
            f"| {seg.name} | {seg.revenue:.1f}亿 | "
            f"{seg.comparable_multiple:.1f}x {seg.multiple_type} | "
            f"{seg_value:.1f}亿 |"
        )

    lines.append(f"| **合计** | | | **{result.total_segment_value:.1f}亿** |")
    lines.append("")

    # 调整项
    lines.append("### 调整项")
    lines.append(f"- 集团费用现值: -{result.corporate_expense_pv:.1f}亿")
    lines.append(f"- 净负债: {result.net_debt:.1f}亿")
    lines.append(f"- **股权价值: {result.equity_value:.1f}亿**")
    lines.append(f"- **每股价值: {result.value_per_share:.2f}元 (人民币)**")
    lines.append(f"- **每股价值: {result.value_per_share_hkd:.2f}元 (港元)**")

    if result.upside:
        lines.append(f"- **上行空间: {result.upside:.1%}**")

    # 假设说明
    if result.assumptions:
        lines.append("\n### 假设说明")
        for assumption in result.assumptions:
            lines.append(f"- {assumption}")

    # 警告
    if result.warnings:
        lines.append("\n### 警告")
        for warning in result.warnings:
            lines.append(f"- ⚠️ {warning}")

    return "\n".join(lines)
