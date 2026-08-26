"""
估值数据契约（v10 新建，HeavySkill K8 审查 P0-1）。

所有估值输入必须通过此契约传递，禁止 dict[str, Any] 直传。
对标 CFA Standard V-A：所有估值输入必须有合理来源、可追溯。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Financials:
    """估值输入数据契约（不可变，必填字段无默认值）。

    CFA V-A 要求：每个字段必须可追溯到原始数据源（Wind API/年报）。
    """

    # === 损益表 ===
    revenue: float                    # 营业收入（亿元）
    operating_profit: float           # 营业利润（亿元）
    net_profit_parent: float          # 归母净利润（亿元）

    # === 资产负债表 ===
    total_assets: float               # 总资产（亿元）
    total_liabilities: float          # 总负债（亿元）
    equity_parent: float              # 归母净资产（亿元）

    # === 现金流量表 ===
    operating_cashflow: float         # 经营现金流（亿元）

    # === 市场数据 ===
    shares: float                     # 总股本（亿股）
    current_price: float              # 当前股价（元或港元）

    # === 可选字段（必须在必填字段之后）===
    gross_profit: float | None = None # 毛利润（亿元）
    cash: float | None = None         # 货币资金（亿元）
    interest_bearing_debt: float | None = None  # 有息负债（亿元）
    capex: float | None = None        # 资本开支（亿元）
    currency: Literal["CNY", "HKD", "USD"] = "CNY"

    # === 元数据（CFA V-A 可追溯性）===
    ticker: str = ""
    company_name: str = ""
    fiscal_year: int = 0
    source: str = "Wind"
    report_date: str = ""
    unit: str = "亿元"

    @property
    def net_debt(self) -> float:
        """净债务 = 有息负债 - 货币资金。"""
        return (self.interest_bearing_debt or 0.0) - (self.cash or 0.0)

    @property
    def enterprise_value(self) -> float:
        """企业价值 EV = 市值 + 净债务。"""
        return self.shares * self.current_price + self.net_debt

    @property
    def ebit_margin(self) -> float:
        """EBIT 利润率 = 营业利润 / 营业收入。"""
        return self.operating_profit / self.revenue if self.revenue > 0 else 0.0

    @property
    def is_loss_company(self) -> bool:
        """是否亏损公司。"""
        return self.net_profit_parent < 0

    @property
    def has_positive_ocf(self) -> bool:
        """经营现金流是否为正（亏损但 OCF 正 = 有扭亏路径）。"""
        return self.operating_cashflow > 0

    @property
    def leverage(self) -> float:
        """资产负债率。"""
        return self.total_liabilities / self.total_assets if self.total_assets > 0 else 0.0

    def to_wind_dict(self) -> dict:
        """转换为 Wind financials dict 格式（向后兼容旧代码）。"""
        return {
            "income": {
                "年营业总收入": [self.revenue],
                "年营业利润": [self.operating_profit],
                "年净利润": [self.net_profit_parent],
            },
            "balance": {
                "总资产": [self.total_assets],
                "年负债合计": [self.total_liabilities],
                "年所有者权益合计": [self.equity_parent],
            },
            "cashflow": {
                "经营活动现金流量净额": [self.operating_cashflow],
            },
        }
