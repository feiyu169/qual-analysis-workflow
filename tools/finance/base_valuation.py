"""
base_valuation.py — Layer 1.5: 基础估值模块

功能：
1. PE/PB/PS自动计算：调用Wind MCP valuation API
2. 当前估值水平快照
3. 输出：BaseValuation对象，供辩论机制使用
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ====================================================================
# 数据结构
# ====================================================================

@dataclass
class BaseValuation:
    """基础估值快照"""
    ticker: str
    company_name: str

    # 估值倍数
    pe_ttm: float | None = None      # 滚动PE
    pe_forward: float | None = None   # 远期PE
    pb: float | None = None           # PB
    ps_ttm: float | None = None       # PS

    # 市值
    market_cap: float | None = None   # 总市值（亿港元）
    market_cap_cny: float | None = None  # 总市值（亿人民币）

    # 股价
    price: float | None = None        # 当前股价（港元）
    shares: float | None = None       # 总股本（亿股）

    # 财务数据（用于计算）
    net_profit: float | None = None   # 净利润（亿人民币）
    revenue: float | None = None      # 营收（亿人民币）
    book_value: float | None = None   # 净资产（亿人民币）

    # 历史对比
    pe_history_avg: float | None = None  # 历史PE中枢
    pe_percentile: float | None = None   # PE所处历史分位

    # 数据来源
    source: str = "Wind MCP"
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """是否有足够的估值数据"""
        return self.pe_ttm is not None or self.pb is not None

    @property
    def pe_discount(self) -> float | None:
        """PE相对历史中枢的折价"""
        if self.pe_ttm and self.pe_history_avg:
            return (self.pe_history_avg - self.pe_ttm) / self.pe_history_avg
        return None

    def summary(self) -> str:
        """生成估值摘要（供辩论使用）"""
        lines = [f"## {self.company_name} ({self.ticker}) 当前估值水平"]
        lines.append("")

        if self.price:
            lines.append(f"- 当前股价: {self.price} HKD")
        if self.market_cap:
            lines.append(f"- 总市值: {self.market_cap:.0f} 亿港元")
        if self.pe_ttm:
            lines.append(f"- PE(TTM): {self.pe_ttm:.1f}x")
        if self.pb:
            lines.append(f"- PB: {self.pb:.1f}x")
        if self.ps_ttm:
            lines.append(f"- PS(TTM): {self.ps_ttm:.1f}x")

        if self.pe_history_avg:
            lines.append(f"- 历史PE中枢: {self.pe_history_avg:.1f}x")
            if self.pe_discount:
                discount_pct = self.pe_discount * 100
                direction = "折价" if discount_pct > 0 else "溢价"
                lines.append(f"- 相对历史中枢: {direction} {abs(discount_pct):.1f}%")

        if self.warnings:
            lines.append("")
            lines.append("### 警告")
            for w in self.warnings:
                lines.append(f"- {w}")

        return "\n".join(lines)


# ====================================================================
# 估值计算
# ====================================================================

def compute_base_valuation(
    ticker: str,
    company_name: str,
    wind_valuation: dict | None = None,
    wind_financials: dict | None = None,
    shares: float | None = None,
    exchange_rate: float | None = None,  # HKD/CNY（双专家 P2：None=未提供，默认 0.92 并标注）
) -> BaseValuation:
    """
    计算基础估值。

    Args:
        ticker: 股票代码
        company_name: 公司名称
        wind_valuation: Wind估值API返回的数据
        wind_financials: Wind财务数据
        shares: 总股本（亿股）
        exchange_rate: HKD/CNY汇率（None=调用方未提供，用默认 0.92 并显式标注——
                       双专家 P2：硬编码 0.92 对港股目标价系统性偏差 8-10%，应传实时汇率）

    Returns:
        BaseValuation 估值快照
    """
    bv = BaseValuation(ticker=ticker, company_name=company_name)

    # 双专家 P2：汇率未提供 → 显式标注默认假设（不静默）
    if exchange_rate is None:
        exchange_rate = 0.92
        bv.warnings.append("⚠️ 汇率未提供，使用默认假设 HKD/CNY=0.92——"
                           "对港股估值存在 ±8-10% 系统性偏差，应传入实时汇率")

    # === 从Wind估值API获取数据 ===
    if wind_valuation and isinstance(wind_valuation, dict):
        bv.pe_ttm = wind_valuation.get('pe_ttm') or wind_valuation.get('pe')
        bv.pb = wind_valuation.get('pb')
        bv.ps_ttm = wind_valuation.get('ps_ttm') or wind_valuation.get('ps')
        bv.price = wind_valuation.get('price') or wind_valuation.get('last')
        bv.market_cap = wind_valuation.get('market_cap')

        if bv.price and shares:
            bv.shares = shares
            bv.market_cap = bv.price * shares  # 亿港元

    # === 从Wind财务数据获取净利润/营收 ===
    if wind_financials and isinstance(wind_financials, dict):
        income = wind_financials.get('income', {})

        # 净利润
        np_list = income.get('年净利润') or income.get('年归属母公司股东的净利润')
        if isinstance(np_list, list) and np_list:
            bv.net_profit = np_list[-1]  # 最新年份

        # 营收
        rev_list = income.get('年营业总收入')
        if isinstance(rev_list, list) and rev_list:
            bv.revenue = rev_list[-1]

        # 净资产（从资产负债表）
        balance = wind_financials.get('balance', {})
        equity_list = balance.get('最近3年每年所有者权益合计')
        if isinstance(equity_list, list) and equity_list:
            bv.book_value = equity_list[-1]

    # === 自动计算缺失的估值倍数 ===
    if bv.market_cap and bv.net_profit and not bv.pe_ttm:
        # 市值(港元) / 净利润(人民币) = PE
        market_cap_cny = bv.market_cap * exchange_rate
        bv.pe_ttm = market_cap_cny / bv.net_profit
        bv.warnings.append(f"PE由市值/净利润计算: {bv.pe_ttm:.1f}x")

    if bv.market_cap and bv.revenue and not bv.ps_ttm:
        market_cap_cny = bv.market_cap * exchange_rate
        bv.ps_ttm = market_cap_cny / bv.revenue
        bv.warnings.append(f"PS由市值/营收计算: {bv.ps_ttm:.1f}x")

    if bv.market_cap and bv.book_value and not bv.pb:
        market_cap_cny = bv.market_cap * exchange_rate
        bv.pb = market_cap_cny / bv.book_value
        bv.warnings.append(f"PB由市值/净资产计算: {bv.pb:.1f}x")

    # === 计算人民币市值 ===
    if bv.market_cap:
        bv.market_cap_cny = bv.market_cap * exchange_rate

    # === 估算历史PE中枢（简化：使用3年平均） ===
    if wind_financials:
        income = wind_financials.get('income', {})
        np_list = income.get('年净利润') or income.get('年归属母公司股东的净利润')
        if isinstance(np_list, list) and len(np_list) >= 3 and bv.market_cap:
            market_cap_cny = bv.market_cap * exchange_rate
            # 3年平均PE
            avg_np = sum(np_list) / len(np_list)
            if avg_np > 0:
                bv.pe_history_avg = market_cap_cny / avg_np
                bv.warnings.append(f"历史PE中枢(3年平均): {bv.pe_history_avg:.1f}x")

    if bv.market_cap:
        logger.info(
            f"基础估值完成: PE={bv.pe_ttm}, PB={bv.pb}, PS={bv.ps_ttm}, "
            f"市值={bv.market_cap:.0f}亿港元"
        )
    else:
        logger.info(
            f"基础估值完成: PE={bv.pe_ttm}, PB={bv.pb}, PS={bv.ps_ttm}"
        )

    return bv


def format_valuation_for_debate(bv: BaseValuation) -> str:
    """
    将基础估值格式化为辩论输入。

    Args:
        bv: BaseValuation对象

    Returns:
        格式化的估值摘要（markdown）
    """
    return bv.summary()
