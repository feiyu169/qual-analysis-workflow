"""
quality/peer_comparison.py — 同行对比矩阵模块（T16修复）

系统性对比目标公司与竞对的关键财务和运营指标。

设计原则：
1. 支持A股/港股/美股跨市场对比
2. 关键指标覆盖：规模、盈利、估值、运营
3. 输出结构化对比表格
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PeerCompany:
    """同行公司"""
    name: str
    ticker: str
    market: str                           # cn/hk/us
    # 规模指标
    revenue: float = 0.0                  # 营收（亿元）
    revenue_growth: float = 0.0           # 营收增速（%）
    net_income: float = 0.0               # 净利润（亿元）
    # 盈利指标
    net_margin: float = 0.0               # 净利率（%）
    roe: float = 0.0                      # ROE（%）
    # 估值指标
    pe: float = 0.0                       # PE
    pb: float = 0.0                       # PB
    # 运营指标
    market_share: float = 0.0             # 市场份额（%）
    # 物流特有
    express_volume: float = 0.0           # 快递件量（亿件）
    revenue_per_piece: float = 0.0        # 单票收入（元）


@dataclass
class PeerComparisonResult:
    """同行对比结果"""
    target: PeerCompany
    peers: list[PeerCompany] = field(default_factory=list)
    rankings: dict[str, dict] = field(default_factory=dict)  # {指标: {排名, 分位数}}


def create_express_peers() -> list[PeerCompany]:
    """创建快递行业同行对比数据（B4-6：泛化——原 create_sf_express_peers 公司名硬编码删除）

    注：可比数据为**静态参考**（Wind 无可比公司 API 数据源）；接入报告时须标注"静态可比，
    非实时"；验证不可用时降级"标注不可比"（由调用方决定是否展示）。
    """
    return [
        PeerCompany(
            name="顺丰控股", ticker="002352.SZ", market="cn",
            revenue=3082, revenue_growth=8.4, net_income=111,
            net_margin=3.6, roe=11.5, pe=15.17, pb=1.53,
            market_share=15, express_volume=130, revenue_per_piece=16.0,
        ),
        PeerCompany(
            # B4-6 修复：中通快递美股 ZTO.N（原 002024.SZ 为分众传媒——错误 ticker）
            name="中通快递", ticker="ZTO.N", market="us",
            revenue=430, revenue_growth=12, net_income=85,
            net_margin=19.8, roe=25, pe=14.2, pb=2.5,
            market_share=22, express_volume=300, revenue_per_piece=1.4,
        ),
        PeerCompany(
            name="圆通速递", ticker="600233.SH", market="cn",
            revenue=580, revenue_growth=15, net_income=38,
            net_margin=6.5, roe=15, pe=11.8, pb=1.8,
            market_share=16, express_volume=210, revenue_per_piece=2.8,
        ),
        PeerCompany(
            name="韵达股份", ticker="002120.SZ", market="cn",
            revenue=480, revenue_growth=10, net_income=20,
            net_margin=4.2, roe=12, pe=9.5, pb=1.2,
            market_share=14, express_volume=190, revenue_per_piece=2.5,
        ),
        PeerCompany(
            name="极兔速递", ticker="1519.HK", market="hk",
            revenue=520, revenue_growth=25, net_income=-5,
            net_margin=-1.0, roe=-3, pe=0, pb=1.5,
            market_share=12, express_volume=180, revenue_per_piece=2.9,
        ),
        PeerCompany(
            name="UPS", ticker="UPS.N", market="us",
            revenue=6500, revenue_growth=-3, net_income=500,
            net_margin=7.7, roe=35, pe=18.5, pb=8.2,
            market_share=0, express_volume=0, revenue_per_piece=0,
        ),
        PeerCompany(
            name="FedEx", ticker="FDX.N", market="us",
            revenue=5800, revenue_growth=-2, net_income=350,
            net_margin=6.0, roe=18, pe=12.3, pb=2.1,
            market_share=0, express_volume=0, revenue_per_piece=0,
        ),
    ]


def compute_peer_rankings(
    target: PeerCompany,
    peers: list[PeerCompany],
) -> dict[str, dict]:
    """计算目标公司在同行中的排名

    Returns:
        {指标名: {"排名": int, "总数": int, "分位数": float}}
    """
    all_companies = [target] + peers
    rankings = {}

    # 需要排名的指标
    metrics = [
        ("revenue", "营收", "desc"),
        ("revenue_growth", "营收增速", "desc"),
        ("net_margin", "净利率", "desc"),
        ("roe", "ROE", "desc"),
        ("pe", "PE", "asc"),  # PE越低越好
    ]

    for field_name, display_name, order in metrics:
        values = [(c.name, getattr(c, field_name)) for c in all_companies if getattr(c, field_name) > 0]

        if order == "desc":
            values.sort(key=lambda x: x[1], reverse=True)
        else:
            values.sort(key=lambda x: x[1])

        # 找到目标公司排名
        for rank, (name, value) in enumerate(values, 1):
            if name == target.name:
                rankings[display_name] = {
                    "rank": rank,
                    "total": len(values),
                    "value": value,
                    "percentile": (len(values) - rank) / len(values) * 100,
                }
                break

    return rankings


def format_peer_comparison(
    target: PeerCompany,
    peers: list[PeerCompany],
    rankings: dict[str, dict],
) -> str:
    """格式化同行对比报告"""
    lines = []
    lines.append("## 同行对比矩阵")
    lines.append("")

    # 排名摘要
    lines.append("### 关键指标排名")
    lines.append("")
    for metric, info in rankings.items():
        emoji = "🥇" if info["rank"] == 1 else "🥈" if info["rank"] == 2 else "🥉" if info["rank"] == 3 else "📊"
        lines.append(f"- {emoji} {metric}: 第{info['rank']}/{info['total']} (分位数{info['percentile']:.0f}%)")
    lines.append("")

    # 详细对比表
    all_companies = [target] + [p for p in peers if p.name != target.name]
    lines.append("### 详细对比")
    lines.append("")
    lines.append("| 公司 | 市场 | 营收(亿) | 增速 | 净利率 | ROE | PE | PB |")
    lines.append("|------|------|----------|------|--------|-----|-----|-----|")

    for c in all_companies:
        marker = "⭐" if c.name == target.name else ""
        pe_str = f"{c.pe:.1f}x" if c.pe > 0 else "N/A"
        lines.append(
            f"| {marker}{c.name} | {c.market.upper()} | {c.revenue:.0f} | "
            f"{c.revenue_growth:.1f}% | {c.net_margin:.1f}% | {c.roe:.0f}% | "
            f"{pe_str} | {c.pb:.1f}x |"
        )

    lines.append("")
    return "\n".join(lines)
