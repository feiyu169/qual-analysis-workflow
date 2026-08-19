"""
quality/falsification.py — 证伪指标模块（T14修复）

定义投资论点的可量化证伪条件，让投资判断可被市场检验。

设计原则：
1. 每个证伪指标有明确的阈值
2. 每个证伪指标有数据来源和披露时间
3. 证伪后有明确的影响评估
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FalsificationMetric:
    """单个证伪指标"""
    name: str                          # 指标名称
    current_value: float               # 当前值
    falsification_threshold: float     # 证伪阈值
    direction: str                     # "below" 或 "above"
    data_source: str                   # 数据来源（如"月度经营简报"）
    disclosure_frequency: str          # 披露频率（如"每月"）
    impact_if_falsified: str           # 证伪后的影响
    is_falsified: bool = False         # 是否已被证伪


@dataclass
class FalsificationResult:
    """证伪分析结果"""
    metrics: list[FalsificationMetric] = field(default_factory=list)
    falsified_count: int = 0
    pending_count: int = 0
    overall_status: str = "pending"    # "valid" | "partially_falsified" | "falsified"
    summary: str = ""


# 顺丰控股特有证伪指标
SF_EXPRESS_METRICS = [
    {
        "name": "时效件单票收入",
        "current_value": 16.0,
        "falsification_threshold": 15.0,
        "direction": "below",
        "data_source": "月度经营简报",
        "disclosure_frequency": "每月15日前",
        "impact_if_falsified": "定价权丧失，目标价下调30%",
    },
    {
        "name": "国际业务季度净利润",
        "current_value": 1.9,
        "falsification_threshold": -3.0,
        "direction": "below",
        "data_source": "季报",
        "disclosure_frequency": "季报后30日",
        "impact_if_falsified": "第二曲线证伪，目标价下调20%",
    },
    {
        "name": "毛利率",
        "current_value": 13.32,
        "falsification_threshold": 12.5,
        "direction": "below",
        "data_source": "季报",
        "disclosure_frequency": "季报后30日",
        "impact_if_falsified": "盈利能力恶化，目标价下调15%",
    },
    {
        "name": "现金流/净利润比",
        "current_value": 2.48,
        "falsification_threshold": 1.5,
        "direction": "below",
        "data_source": "年报/季报",
        "disclosure_frequency": "季报后30日",
        "impact_if_falsified": "现金流质量下降，目标价下调10%",
    },
    {
        "name": "整体单票收入同比变化",
        "current_value": 0.0,
        "falsification_threshold": -15.0,
        "direction": "below",
        "data_source": "月度经营简报",
        "disclosure_frequency": "每月",
        "impact_if_falsified": "价格战加剧，目标价下调25%",
    },
]


def create_falsification_metrics(
    custom_metrics: Optional[list[dict]] = None,
) -> list[FalsificationMetric]:
    """创建证伪指标列表
    
    Args:
        custom_metrics: 自定义指标列表，格式同SF_EXPRESS_METRICS
    
    Returns:
        证伪指标列表
    """
    metrics_data = custom_metrics or SF_EXPRESS_METRICS
    metrics = []
    
    for m in metrics_data:
        metrics.append(FalsificationMetric(
            name=m["name"],
            current_value=m["current_value"],
            falsification_threshold=m["falsification_threshold"],
            direction=m["direction"],
            data_source=m["data_source"],
            disclosure_frequency=m["disclosure_frequency"],
            impact_if_falsified=m["impact_if_falsified"],
        ))
    
    return metrics


def evaluate_falsification(
    metrics: list[FalsificationMetric],
    current_data: Optional[dict] = None,
) -> FalsificationResult:
    """评估证伪状态
    
    Args:
        metrics: 证伪指标列表
        current_data: 当前数据 {"指标名": 值}
    
    Returns:
        证伪分析结果
    """
    if current_data:
        for metric in metrics:
            if metric.name in current_data:
                metric.current_value = current_data[metric.name]
    
    falsified_count = 0
    pending_count = 0
    
    for metric in metrics:
        if metric.direction == "below":
            metric.is_falsified = metric.current_value < metric.falsification_threshold
        elif metric.direction == "above":
            metric.is_falsified = metric.current_value > metric.falsification_threshold
        
        if metric.is_falsified:
            falsified_count += 1
        else:
            pending_count += 1
    
    # 整体状态
    if falsified_count == 0:
        overall_status = "valid"
        summary = "所有证伪指标均未触发，投资论点有效"
    elif falsified_count >= len(metrics) * 0.5:
        overall_status = "falsified"
        summary = f"超过半数证伪指标触发（{falsified_count}/{len(metrics)}），投资论点已被证伪"
    else:
        overall_status = "partially_falsified"
        summary = f"部分证伪指标触发（{falsified_count}/{len(metrics)}），需重新评估"
    
    return FalsificationResult(
        metrics=metrics,
        falsified_count=falsified_count,
        pending_count=pending_count,
        overall_status=overall_status,
        summary=summary,
    )


def format_falsification_report(result: FalsificationResult) -> str:
    """格式化证伪分析报告
    
    Args:
        result: 证伪分析结果
    
    Returns:
        Markdown格式报告
    """
    lines = []
    lines.append("## 证伪指标监控")
    lines.append("")
    lines.append(f"**整体状态**: {result.summary}")
    lines.append("")
    
    lines.append("| 指标 | 当前值 | 证伪阈值 | 状态 | 数据来源 | 披露频率 | 证伪影响 |")
    lines.append("|------|--------|----------|------|----------|----------|----------|")
    
    for m in result.metrics:
        status = "❌ 已证伪" if m.is_falsified else "✅ 有效"
        threshold = f"{'<' if m.direction == 'below' else '>'}{m.falsification_threshold}"
        lines.append(
            f"| {m.name} | {m.current_value} | {threshold} | {status} "
            f"| {m.data_source} | {m.disclosure_frequency} | {m.impact_if_falsified[:20]}... |"
        )
    
    lines.append("")
    return "\n".join(lines)
