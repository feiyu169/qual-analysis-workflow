"""
quality/formulas.py — 标准化计算公式库

定义投资分析中的标准计算公式，避免计算错误。

原则：
1. 每个公式有明确的定义和说明
2. 每个公式有输入验证
3. 每个公式有输出校验
4. 每个公式有数据来源要求
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class FormulaResult:
    """公式计算结果"""
    value: float
    formula: str
    inputs: dict
    unit: str
    source: str
    confidence: float = 1.0
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class Formulas:
    """标准化计算公式库"""
    
    # ─────────────────────────────────────────────────
    # 估值公式
    # ─────────────────────────────────────────────────
    
    @staticmethod
    def pe_ratio(
        market_cap: float,
        net_income: float,
        net_income_type: str = "GAAP",
        currency: str = "CNY"
    ) -> FormulaResult:
        """计算PE（市盈率）
        
        Args:
            market_cap: 市值（亿元）
            net_income: 净利润（亿元）
            net_income_type: 净利润口径
                - "GAAP": 归母净利润（IFRS/CAS）
                - "adjusted": 经调整净利润（Non-IFRS）
                - "core": 核心盈利（港股常用）
            currency: 币种
                - "CNY": 人民币
                - "HKD": 港币
                - "USD": 美元
        
        Returns:
            FormulaResult: 计算结果
        """
        # 输入验证
        if market_cap <= 0:
            return FormulaResult(
                value=0, formula="PE = 市值 / 净利润",
                inputs={"market_cap": market_cap, "net_income": net_income},
                unit="倍", source="calculated",
                warnings=["市值必须大于0"]
            )
        
        if net_income <= 0:
            return FormulaResult(
                value=float('inf'), formula="PE = 市值 / 净利润",
                inputs={"market_cap": market_cap, "net_income": net_income},
                unit="倍", source="calculated",
                warnings=["净利润为负，PE无意义"]
            )
        
        # 计算
        pe = market_cap / net_income
        
        return FormulaResult(
            value=pe,
            formula=f"PE({net_income_type}) = {market_cap:.2f}亿 / {net_income:.2f}亿",
            inputs={
                "market_cap": market_cap,
                "net_income": net_income,
                "net_income_type": net_income_type,
                "currency": currency
            },
            unit="倍",
            source="calculated",
            warnings=[]
        )
    
    @staticmethod
    def pb_ratio(
        market_cap: float,
        equity_attributable_to_parent: float,
        currency: str = "CNY"
    ) -> FormulaResult:
        """计算PB（市净率）
        
        ⚠️ 关键：必须使用归母净资产，而非总权益
        
        Args:
            market_cap: 市值（亿元）
            equity_attributable_to_parent: 归母净资产（亿元）
            currency: 币种
        
        Returns:
            FormulaResult: 计算结果
        """
        # 输入验证
        if market_cap <= 0:
            return FormulaResult(
                value=0, formula="PB = 市值 / 归母净资产",
                inputs={"market_cap": market_cap, "equity": equity_attributable_to_parent},
                unit="倍", source="calculated",
                warnings=["市值必须大于0"]
            )
        
        if equity_attributable_to_parent <= 0:
            return FormulaResult(
                value=float('inf'), formula="PB = 市值 / 归母净资产",
                inputs={"market_cap": market_cap, "equity": equity_attributable_to_parent},
                unit="倍", source="calculated",
                warnings=["归母净资产为负，PB无意义"]
            )
        
        # 计算
        pb = market_cap / equity_attributable_to_parent
        
        return FormulaResult(
            value=pb,
            formula=f"PB = {market_cap:.2f}亿 / {equity_attributable_to_parent:.2f}亿",
            inputs={
                "market_cap": market_cap,
                "equity_attributable_to_parent": equity_attributable_to_parent,
                "currency": currency
            },
            unit="倍",
            source="calculated",
            warnings=[]
        )
    
    @staticmethod
    def ps_ratio(
        market_cap: float,
        revenue: float,
        currency: str = "CNY"
    ) -> FormulaResult:
        """计算PS（市销率）
        
        Args:
            market_cap: 市值（亿元）
            revenue: 营业收入（亿元）
            currency: 币种
        
        Returns:
            FormulaResult: 计算结果
        """
        if market_cap <= 0 or revenue <= 0:
            return FormulaResult(
                value=0, formula="PS = 市值 / 营业收入",
                inputs={"market_cap": market_cap, "revenue": revenue},
                unit="倍", source="calculated",
                warnings=["市值和营收必须大于0"]
            )
        
        ps = market_cap / revenue
        
        return FormulaResult(
            value=ps,
            formula=f"PS = {market_cap:.2f}亿 / {revenue:.2f}亿",
            inputs={"market_cap": market_cap, "revenue": revenue, "currency": currency},
            unit="倍",
            source="calculated",
            warnings=[]
        )
    
    @staticmethod
    def market_cap(
        share_price: float,
        total_shares: float,
        currency: str = "CNY"
    ) -> FormulaResult:
        """计算市值
        
        ⚠️ 关键：total_shares单位必须是亿股
        
        Args:
            share_price: 股价（元/港元/美元）
            total_shares: 总股本（亿股）
            currency: 币种
        
        Returns:
            FormulaResult: 计算结果（亿元）
        """
        # 输入验证
        if share_price <= 0:
            return FormulaResult(
                value=0, formula="市值 = 股价 × 总股本",
                inputs={"share_price": share_price, "total_shares": total_shares},
                unit="亿元", source="calculated",
                warnings=["股价必须大于0"]
            )
        
        if total_shares <= 0:
            return FormulaResult(
                value=0, formula="市值 = 股价 × 总股本",
                inputs={"share_price": share_price, "total_shares": total_shares},
                unit="亿元", source="calculated",
                warnings=["总股本必须大于0"]
            )
        
        # 单位检查：如果total_shares < 1，可能是单位错误
        warnings = []
        if total_shares < 1:
            warnings.append(f"总股本={total_shares}亿股，小于1亿股，请确认单位是否正确")
        
        # 计算
        cap = share_price * total_shares
        
        return FormulaResult(
            value=cap,
            formula=f"市值 = {share_price:.2f} × {total_shares:.2f}亿股",
            inputs={
                "share_price": share_price,
                "total_shares": total_shares,
                "currency": currency
            },
            unit="亿元",
            source="calculated",
            warnings=warnings
        )
    
    # ─────────────────────────────────────────────────
    # 盈利能力公式
    # ─────────────────────────────────────────────────
    
    @staticmethod
    def gross_margin(
        revenue: float,
        cost_of_goods_sold: float
    ) -> FormulaResult:
        """计算毛利率
        
        Args:
            revenue: 营业收入（亿元）
            cost_of_goods_sold: 营业成本（亿元）
        
        Returns:
            FormulaResult: 计算结果（%）
        """
        if revenue <= 0:
            return FormulaResult(
                value=0, formula="毛利率 = (营收 - 营业成本) / 营收",
                inputs={"revenue": revenue, "cogs": cost_of_goods_sold},
                unit="%", source="calculated",
                warnings=["营收必须大于0"]
            )
        
        margin = (revenue - cost_of_goods_sold) / revenue * 100
        
        return FormulaResult(
            value=margin,
            formula=f"毛利率 = ({revenue:.2f} - {cost_of_goods_sold:.2f}) / {revenue:.2f} × 100%",
            inputs={"revenue": revenue, "cogs": cost_of_goods_sold},
            unit="%",
            source="calculated",
            warnings=[]
        )
    
    @staticmethod
    def net_margin(
        net_income: float,
        revenue: float
    ) -> FormulaResult:
        """计算净利率
        
        Args:
            net_income: 净利润（亿元）
            revenue: 营业收入（亿元）
        
        Returns:
            FormulaResult: 计算结果（%）
        """
        if revenue <= 0:
            return FormulaResult(
                value=0, formula="净利率 = 净利润 / 营收",
                inputs={"net_income": net_income, "revenue": revenue},
                unit="%", source="calculated",
                warnings=["营收必须大于0"]
            )
        
        margin = net_income / revenue * 100
        
        return FormulaResult(
            value=margin,
            formula=f"净利率 = {net_income:.2f} / {revenue:.2f} × 100%",
            inputs={"net_income": net_income, "revenue": revenue},
            unit="%",
            source="calculated",
            warnings=[]
        )
    
    @staticmethod
    def roe(
        net_income: float,
        equity_attributable_to_parent: float,
        period: str = "annual"
    ) -> FormulaResult:
        """计算ROE（净资产收益率）
        
        ⚠️ 关键：必须使用归母净利润和归母净资产
        
        Args:
            net_income: 归母净利润（亿元）
            equity_attributable_to_parent: 归母净资产（亿元）
            period: 期间
                - "annual": 年化
                - "quarterly": 季度（需年化）
        
        Returns:
            FormulaResult: 计算结果（%）
        """
        if equity_attributable_to_parent <= 0:
            return FormulaResult(
                value=0, formula="ROE = 归母净利润 / 归母净资产",
                inputs={"net_income": net_income, "equity": equity_attributable_to_parent},
                unit="%", source="calculated",
                warnings=["归母净资产必须大于0"]
            )
        
        roe = net_income / equity_attributable_to_parent * 100
        
        return FormulaResult(
            value=roe,
            formula=f"ROE = {net_income:.2f}亿 / {equity_attributable_to_parent:.2f}亿 × 100%",
            inputs={
                "net_income": net_income,
                "equity": equity_attributable_to_parent,
                "period": period
            },
            unit="%",
            source="calculated",
            warnings=[]
        )
    
    # ─────────────────────────────────────────────────
    # 增长率公式
    # ─────────────────────────────────────────────────
    
    @staticmethod
    def growth_rate(
        current: float,
        previous: float,
        label: str = ""
    ) -> FormulaResult:
        """计算增长率
        
        Args:
            current: 当期值
            previous: 上期值
            label: 标签（如"营收"、"净利润"）
        
        Returns:
            FormulaResult: 计算结果（%）
        """
        if previous == 0:
            return FormulaResult(
                value=0, formula="增长率 = (当期 - 上期) / |上期|",
                inputs={"current": current, "previous": previous},
                unit="%", source="calculated",
                warnings=["上期值为0，无法计算增长率"]
            )
        
        growth = (current - previous) / abs(previous) * 100
        
        return FormulaResult(
            value=growth,
            formula=f"{label}增长率 = ({current:.2f} - {previous:.2f}) / |{previous:.2f}| × 100%",
            inputs={"current": current, "previous": previous, "label": label},
            unit="%",
            source="calculated",
            warnings=[]
        )
    
    @staticmethod
    def cagr(
        begin: float,
        end: float,
        years: int,
        label: str = ""
    ) -> FormulaResult:
        """计算CAGR（复合年增长率）
        
        Args:
            begin: 起始值
            end: 终止值
            years: 年数
            label: 标签
        
        Returns:
            FormulaResult: 计算结果（%）
        """
        if begin <= 0 or end <= 0 or years <= 0:
            return FormulaResult(
                value=0, formula="CAGR = (终止值/起始值)^(1/年数) - 1",
                inputs={"begin": begin, "end": end, "years": years},
                unit="%", source="calculated",
                warnings=["起始值、终止值和年数必须大于0"]
            )
        
        cagr = ((end / begin) ** (1 / years) - 1) * 100
        
        return FormulaResult(
            value=cagr,
            formula=f"CAGR = ({end:.2f}/{begin:.2f})^(1/{years}) - 1 = {cagr:.2f}%",
            inputs={"begin": begin, "end": end, "years": years, "label": label},
            unit="%",
            source="calculated",
            warnings=[]
        )
    
    # ─────────────────────────────────────────────────
    # 财务健康公式
    # ─────────────────────────────────────────────────
    
    @staticmethod
    def debt_to_equity(
        total_debt: float,
        total_equity: float
    ) -> FormulaResult:
        """计算资产负债率
        
        Args:
            total_debt: 总负债（亿元）
            total_equity: 总权益（亿元）
        
        Returns:
            FormulaResult: 计算结果（%）
        """
        total_assets = total_debt + total_equity
        if total_assets <= 0:
            return FormulaResult(
                value=0, formula="资产负债率 = 总负债 / 总资产",
                inputs={"total_debt": total_debt, "total_equity": total_equity},
                unit="%", source="calculated",
                warnings=["总资产必须大于0"]
            )
        
        ratio = total_debt / total_assets * 100
        
        return FormulaResult(
            value=ratio,
            formula=f"资产负债率 = {total_debt:.2f}亿 / {total_assets:.2f}亿 × 100%",
            inputs={"total_debt": total_debt, "total_equity": total_equity},
            unit="%",
            source="calculated",
            warnings=[]
        )
    
    @staticmethod
    def current_ratio(
        current_assets: float,
        current_liabilities: float
    ) -> FormulaResult:
        """计算流动比率
        
        Args:
            current_assets: 流动资产（亿元）
            current_liabilities: 流动负债（亿元）
        
        Returns:
            FormulaResult: 计算结果
        """
        if current_liabilities <= 0:
            return FormulaResult(
                value=float('inf'), formula="流动比率 = 流动资产 / 流动负债",
                inputs={"current_assets": current_assets, "current_liabilities": current_liabilities},
                unit="倍", source="calculated",
                warnings=["流动负债必须大于0"]
            )
        
        ratio = current_assets / current_liabilities
        
        return FormulaResult(
            value=ratio,
            formula=f"流动比率 = {current_assets:.2f}亿 / {current_liabilities:.2f}亿",
            inputs={"current_assets": current_assets, "current_liabilities": current_liabilities},
            unit="倍",
            source="calculated",
            warnings=[]
        )
    
    # ─────────────────────────────────────────────────
    # 现金流公式
    # ─────────────────────────────────────────────────
    
    @staticmethod
    def fcf(
        operating_cashflow: float,
        capex: float
    ) -> FormulaResult:
        """计算自由现金流（FCF）
        
        Args:
            operating_cashflow: 经营活动现金流（亿元）
            capex: 资本开支（亿元，取绝对值）
        
        Returns:
            FormulaResult: 计算结果（亿元）
        """
        fcf = operating_cashflow - capex
        
        return FormulaResult(
            value=fcf,
            formula=f"FCF = {operating_cashflow:.2f}亿 - {capex:.2f}亿",
            inputs={"operating_cashflow": operating_cashflow, "capex": capex},
            unit="亿元",
            source="calculated",
            warnings=[]
        )
    
    @staticmethod
    def cash_conversion_ratio(
        operating_cashflow: float,
        net_income: float
    ) -> FormulaResult:
        """计算现金流转化率
        
        Args:
            operating_cashflow: 经营活动现金流（亿元）
            net_income: 净利润（亿元）
        
        Returns:
            FormulaResult: 计算结果（%）
        """
        if net_income <= 0:
            return FormulaResult(
                value=0, formula="现金流转化率 = 经营现金流 / 净利润",
                inputs={"operating_cashflow": operating_cashflow, "net_income": net_income},
                unit="%", source="calculated",
                warnings=["净利润为负，转化率无意义"]
            )
        
        ratio = operating_cashflow / net_income * 100
        
        return FormulaResult(
            value=ratio,
            formula=f"现金流转化率 = {operating_cashflow:.2f}亿 / {net_income:.2f}亿 × 100%",
            inputs={"operating_cashflow": operating_cashflow, "net_income": net_income},
            unit="%",
            source="calculated",
            warnings=[]
        )
