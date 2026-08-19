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
from typing import Optional


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
