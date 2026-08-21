"""
CAPMCalculator模块

功能:
- 多因子CAPM计算
- Blume调整Beta
- 规模溢价
- α上限控制

解决: WACC硬编码10%问题

"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CAPMConfig:
    """CAPM 配置（测试契约：HGF P0-① 修复——v3 shim 暴露平铺实现所需）"""
    blume_adjustment: bool = True          # Blume 调整开关
    beta_method: str = "regression"        # regression | blended | bottom_up
    regression_weight: float = 0.67        # blended 时回归权重
    total_alpha_cap: float | None = None  # α 总上限（None=默认 3%）
    size_premium_enabled: bool = False
    size_premium_cap: float = 0.03
    liquidity_premium_enabled: bool = False
    liquidity_premium_value: float = 0.0
    governance_premium_enabled: bool = False
    governance_premium_value: float = 0.0


@dataclass
class CAPMResult:
    """CAPM计算结果"""
    ke: float  # 权益成本
    rf: float  # 无风险利率
    beta: float  # Beta系数
    erp: float  # 股权风险溢价
    size_premium: float  # 规模溢价
    alpha: float  # α调整
    components: dict  # 各组件详情
    # HGF P0-①：测试契约字段（hermes 版 API）
    mrp: float = 0.055     # 市场风险溢价（别名 erp）
    formula: str = ""      # 计算过程公式文本


@dataclass
class BetaResult:
    """Beta 计算结果（calculate_beta 契约）"""
    final_beta: float
    method: str  # regression | bottom_up | blended | default
    raw_beta: float = 0.0


@dataclass
class AlphaResult:
    """Alpha 计算结果（calculate_alpha 契约）"""
    size_premium: float
    total: float
    capped: bool = False


class CAPMCalculator:
    """CAPM计算器

    计算公式:
    Ke = Rf + β × ERP + SizePremium + α

    约束:
    - Ke ∈ [5%, 25%]
    - β ∈ [0.5, 2.5]
    - ERP ∈ [3%, 8%]
    - SizePremium ∈ [0%, 3%]
    - α ∈ [-2%, 2%]
    """

    # 参数范围
    KE_RANGE = (0.05, 0.25)
    BETA_RANGE = (0.5, 2.5)
    ERP_RANGE = (0.03, 0.08)
    SIZE_PREMIUM_RANGE = (0.0, 0.03)
    ALPHA_RANGE = (-0.02, 0.02)

    # 默认值
    DEFAULT_RF = 0.023  # 中国10年期国债
    DEFAULT_ERP = 0.055  # Damodaran新兴市场
    DEFAULT_SIZE_PREMIUM = 0.0  # 无规模溢价
    DEFAULT_ALPHA = 0.0  # 无α调整

    def __init__(self, config: CAPMConfig | None = None):
        """CAPM 计算器（config 可选——测试契约：CAPMConfig 注入）"""
        self.config = config or CAPMConfig()

    def calculate_ke(
        self,
        regression_beta: float = 1.0,
        regression_r_squared: float = 0.5,
        risk_free_rate: float | None = None,
        market_risk_premium: float | None = None,
        **kwargs,
    ) -> CAPMResult:
        """计算 Ke（测试契约：回归 Beta + 可选无风险利率/风险溢价）"""
        rf = risk_free_rate if risk_free_rate is not None else self.DEFAULT_RF
        erp = market_risk_premium if market_risk_premium is not None else self.DEFAULT_ERP
        # Blume 调整（按 config）
        beta = regression_beta
        if self.config.blume_adjustment:
            beta = 0.67 * regression_beta + 0.33 * 1.0
        self._validate_params(rf, beta, erp, 0.0, 0.0)
        ke = rf + beta * erp
        ke = max(self.KE_RANGE[0], min(self.KE_RANGE[1], ke))
        return CAPMResult(
            ke=ke, rf=rf, beta=beta, erp=erp,
            size_premium=0.0, alpha=0.0,
            components={'rf': rf, 'beta_erp': beta * erp,
                        'size_premium': 0.0, 'alpha': 0.0},
            mrp=erp,
            formula=f"Ke = {rf:.4f} + {beta:.4f} × {erp:.4f}",
        )

    def calculate_beta(
        self,
        regression_beta: float = 1.0,
        regression_r_squared: float = 0.5,
        bottom_up_beta: float | None = None,
        **kwargs,
    ) -> BetaResult:
        """计算 Beta（测试契约：Blume 调整 / blended 方法选择）"""
        if regression_r_squared < 0.3 and bottom_up_beta is not None:
            # 回归 R² 低 → 用 bottom_up（测试契约：R²<0.3 → bottom_up，优先于 blended）
            final_beta = bottom_up_beta
            method = "bottom_up"
        elif self.config.beta_method == "blended" and bottom_up_beta is not None:
            w = self.config.regression_weight
            final_beta = w * regression_beta + (1 - w) * bottom_up_beta
            method = "blended"
        elif self.config.blume_adjustment:
            final_beta = 0.67 * regression_beta + 0.33 * 1.0
            method = "regression"
        else:
            final_beta = regression_beta
            method = "regression"
        return BetaResult(final_beta=final_beta, method=method,
                          raw_beta=regression_beta)

    def calculate_alpha(
        self,
        size_premium: float = 0.0,
        liquidity_premium: float = 0.0,
        governance_premium: float = 0.0,
        **kwargs,
    ) -> AlphaResult:
        """计算 α（测试契约：规模溢价单项上限 3%，总上限 config 或 6%）"""
        cap_size = self.config.size_premium_cap if self.config.size_premium_enabled else 0.03
        size = min(size_premium, cap_size)
        liq = liquidity_premium if self.config.liquidity_premium_enabled else 0.0
        gov = governance_premium if self.config.governance_premium_enabled else 0.0
        total = size + liq + gov
        cap = self.config.total_alpha_cap if self.config.total_alpha_cap is not None else 0.06
        capped = total > cap
        if capped:
            total = cap
        return AlphaResult(size_premium=size, total=total, capped=capped)

    def validate_ke(self, ke: float) -> bool:
        """Ke 是否在合理区间（测试契约：validate_ke）"""
        return self.KE_RANGE[0] <= ke <= self.KE_RANGE[1]

    def calculate(
        self,
        rf: float = DEFAULT_RF,
        beta: float = 1.0,
        erp: float = DEFAULT_ERP,
        size_premium: float = DEFAULT_SIZE_PREMIUM,
        alpha: float = DEFAULT_ALPHA,
        market: str = "cn"
    ) -> CAPMResult:
        """计算CAPM"""

        # 参数验证
        self._validate_params(rf, beta, erp, size_premium, alpha)

        # 计算Ke
        ke = rf + beta * erp + size_premium + alpha

        # 约束检查
        ke = max(self.KE_RANGE[0], min(self.KE_RANGE[1], ke))

        return CAPMResult(
            ke=ke,
            rf=rf,
            beta=beta,
            erp=erp,
            size_premium=size_premium,
            alpha=alpha,
            components={
                'rf': rf,
                'beta_erp': beta * erp,
                'size_premium': size_premium,
                'alpha': alpha
            }
        )

    def calculate_with_blume(
        self,
        raw_beta: float,
        rf: float = DEFAULT_RF,
        erp: float = DEFAULT_ERP,
        size_premium: float = DEFAULT_SIZE_PREMIUM,
        alpha: float = DEFAULT_ALPHA,
        market: str = "cn"
    ) -> CAPMResult:
        """使用Blume调整Beta计算CAPM

        Blume调整公式:
        β_adjusted = 0.67 × β_raw + 0.33 × 1.0

        这是为了调整回归Beta的均值回归倾向
        """

        # Blume调整
        beta_adjusted = 0.67 * raw_beta + 0.33 * 1.0

        # 使用调整后的Beta计算
        return self.calculate(
            rf=rf,
            beta=beta_adjusted,
            erp=erp,
            size_premium=size_premium,
            alpha=alpha,
            market=market
        )

    def _validate_params(
        self,
        rf: float,
        beta: float,
        erp: float,
        size_premium: float,
        alpha: float
    ) -> None:
        """验证参数"""

        if rf < 0 or rf > 0.10:
            raise ValueError(f"Rf={rf:.2%}超出合理范围[0%, 10%]")

        if beta < self.BETA_RANGE[0] or beta > self.BETA_RANGE[1]:
            raise ValueError(f"Beta={beta:.2f}超出合理范围[{self.BETA_RANGE[0]}, {self.BETA_RANGE[1]}]")

        if erp < self.ERP_RANGE[0] or erp > self.ERP_RANGE[1]:
            raise ValueError(f"ERP={erp:.2%}超出合理范围[{self.ERP_RANGE[0]:.0%}, {self.ERP_RANGE[1]:.0%}]")

        if size_premium < self.SIZE_PREMIUM_RANGE[0] or size_premium > self.SIZE_PREMIUM_RANGE[1]:
            raise ValueError(f"SizePremium={size_premium:.2%}超出合理范围[{self.SIZE_PREMIUM_RANGE[0]:.0%}, {self.SIZE_PREMIUM_RANGE[1]:.0%}]")

        if alpha < self.ALPHA_RANGE[0] or alpha > self.ALPHA_RANGE[1]:
            raise ValueError(f"α={alpha:.2%}超出合理范围[{self.ALPHA_RANGE[0]:.0%}, {self.ALPHA_RANGE[1]:.0%}]")

    def get_default_params(self, market: str = "cn") -> dict:
        """获取默认参数"""

        defaults = {
            "cn": {
                "rf": 0.023,  # 中国10年期国债
                "erp": 0.055,  # Damodaran新兴市场
                "size_premium": 0.0,
                "alpha": 0.0
            },
            "hk": {
                "rf": 0.035,  # 香港10年期国债
                "erp": 0.055,  # Damodaran新兴市场
                "size_premium": 0.0,
                "alpha": 0.0
            },
            "us": {
                "rf": 0.040,  # 美国10年期国债
                "erp": 0.050,  # Damodaran成熟市场
                "size_premium": 0.0,
                "alpha": 0.0
            }
        }

        return defaults.get(market, defaults["cn"])
