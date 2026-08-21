"""
quality/catalyst_calendar.py — 催化剂日历模块（T18修复）

跟踪投资催化剂的时间节点，驱动买卖决策。

设计原则：
1. 每个催化剂有明确的时间窗口
2. 每个催化剂有预期影响和验证方法
3. 支持按时间排序和过滤
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class Catalyst:
    """单个催化剂"""
    name: str                          # 催化剂名称
    date: str                          # 预期日期 (YYYY-MM-DD 或 YYYY-QN)
    catalyst_type: str                 # 类型: earnings/dividend/event/policy/data
    expected_impact: str               # 预期影响
    verification_method: str           # 验证方法
    priority: str = "medium"           # high/medium/low
    status: str = "pending"            # pending/occurred/cancelled


@dataclass
class CatalystCalendar:
    """催化剂日历"""
    ticker: str
    company_name: str
    catalysts: list[Catalyst] = field(default_factory=list)

    def upcoming(self, days: int = 90) -> list[Catalyst]:
        """获取未来N天内的催化剂"""
        today = datetime.now()
        cutoff = today + timedelta(days=days)

        upcoming = []
        for c in self.catalysts:
            try:
                # 解析日期（支持YYYY-MM-DD和YYYY-QN格式）
                if "-Q" in c.date:
                    year, quarter = c.date.split("-Q")
                    month = int(quarter) * 3
                    cat_date = datetime(int(year), month, 28)
                else:
                    cat_date = datetime.strptime(c.date, "%Y-%m-%d")

                if today <= cat_date <= cutoff:
                    upcoming.append(c)
            except (ValueError, IndexError):
                # 日期解析失败，跳过
                pass

        # 按日期排序
        upcoming.sort(key=lambda c: c.date)
        return upcoming


def create_sf_express_calendar() -> CatalystCalendar:
    """创建顺丰控股催化剂日历（示例）"""
    return CatalystCalendar(
        ticker="002352.SZ",
        company_name="顺丰控股",
        catalysts=[
            Catalyst(
                name="2025年年报发布",
                date="2026-03-30",
                catalyst_type="earnings",
                expected_impact="验证全年营收/利润是否符合预期",
                verification_method="对比ANCH中的key_argument",
                priority="high",
            ),
            Catalyst(
                name="2026年一季报发布",
                date="2026-04-30",
                catalyst_type="earnings",
                expected_impact="验证Q1时效件单价和国际业务盈利",
                verification_method="对比证伪指标阈值",
                priority="high",
            ),
            Catalyst(
                name="鄂州机场产能利用率公告",
                date="2026-06-30",
                catalyst_type="data",
                expected_impact="验证鄂州机场规模效应释放",
                verification_method="产能利用率是否>50%",
                priority="medium",
            ),
            Catalyst(
                name="分红除权日",
                date="2026-07-15",
                catalyst_type="dividend",
                expected_impact="股息率约2.8%，对长期投资者有吸引力",
                verification_method="实际分红金额",
                priority="low",
            ),
            Catalyst(
                name="快递行业价格监管政策",
                date="2026-09-30",
                catalyst_type="policy",
                expected_impact="若监管介入价格战，利好顺丰利润率",
                verification_method="政策文件发布",
                priority="medium",
            ),
        ]
    )


def format_catalyst_report(calendar: CatalystCalendar, days: int = 90) -> str:
    """格式化催化剂日历报告

    Args:
        calendar: 催化剂日历
        days: 显示未来N天内的催化剂

    Returns:
        Markdown格式报告
    """
    upcoming = calendar.upcoming(days)

    lines = []
    lines.append(f"## 催化剂日历（未来{days}天）")
    lines.append("")

    if not upcoming:
        lines.append("暂无近期催化剂。")
        return "\n".join(lines)

    lines.append("| 日期 | 催化剂 | 类型 | 优先级 | 预期影响 | 验证方法 |")
    lines.append("|------|--------|------|--------|----------|----------|")

    for c in upcoming:
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(c.priority, "⚪")
        lines.append(
            f"| {c.date} | {c.name} | {c.catalyst_type} | {priority_emoji} "
            f"| {c.expected_impact[:30]}... | {c.verification_method[:20]}... |"
        )

    lines.append("")
    return "\n".join(lines)
