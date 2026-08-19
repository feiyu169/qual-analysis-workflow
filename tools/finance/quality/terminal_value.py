"""
TerminalValueCalculator模块

功能:
- 双轨方法: 永续增长法 + 退出倍数法
- TV/EV比例验证
- 终值仲裁规则

解决: P0-2 终值计算方法未明确
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TerminalValueConfig:
    """终值计算配置"""
    primary_method: str = "perpetuity_growth"  # perpetuity_growth | exit_multiple | dual_method
    
    # 永续增长法配置
    g: float = 0.025  # 永续增长率
    g_range: tuple = (0.015, 0.035)  # 合理区间
    g_rationale: str = "名义GDP长期增速"
    
    # 退出倍数法配置
    multiple_type: str = "EV_EBITDA"  # EV_EBITDA | EV_Revenue | PE
    multiple_value: float = 12.0
    multiple_source: str = "peer_median"  # peer_median | peer_mean | custom
    
    # 双方法配置
    weight_perpetuity: float = 0.5
    weight_exit_multiple: float = 0.5
    
    # TV占比上限
    tv_as_pct_max: float = 0.75
    projection_years: int = 5


@dataclass
class PerpetuityGrowthResult:
    """永续增长法结果"""
    method: str = "perpetuity_growth"
    fcf_terminal: float = 0.0
    fcf_n1: float = 0.0
    g: float = 0.0
    wacc: float = 0.0
    tv: float = 0.0
    formula: str = ""


@dataclass
class ExitMultipleResult:
    """退出倍数法结果"""
    method: str = "exit_multiple"
    metric: float = 0.0
    multiple: float = 0.0
    multiple_type: str = ""
    tv: float = 0.0
    formula: str = ""


@dataclass
class TerminalValueResult:
    """终值计算结果"""
    method: str = ""
    tv: float = 0.0
    tv_perpetuity: Optional[float] = None
    tv_exit_multiple: Optional[float] = None
    weight_perpetuity: Optional[float] = None
    weight_exit_multiple: Optional[float] = None
    detail: Optional[Dict] = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class TVValidationResult:
    """TV占比验证结果"""
    tv_pct: float = 0.0
    threshold: float = 0.75
    passed: bool = True
    warning: Optional[str] = None


class TerminalValueCalculator:
    """终值计算器"""
    
    def __init__(self, config: Optional[TerminalValueConfig] = None):
        self.config = config or TerminalValueConfig()
    
    def calculate_perpetuity_growth(
        self,
        final_year_fcf: float,
        wacc: float,
        g: Optional[float] = None,
    ) -> PerpetuityGrowthResult:
        """永续增长法（Gordon Growth Model）"""
        g = g or self.config.g
        g_range = self.config.g_range
        
        # 验证 g < WACC
        if g >= wacc:
            raise ValueError(f"永续增长率 g={g:.2%} 必须小于 WACC={wacc:.2%}")
        
        # 验证 g 在合理区间
        warnings = []
        if not (g_range[0] <= g <= g_range[1]):
            warnings.append(f"永续增长率 g={g:.2%} 超出建议区间 {g_range}")
        
        # TV = FCF_{n+1} / (WACC - g)
        fcf_n1 = final_year_fcf * (1 + g)
        tv = fcf_n1 / (wacc - g)
        
        return PerpetuityGrowthResult(
            method="perpetuity_growth",
            fcf_terminal=final_year_fcf,
            fcf_n1=fcf_n1,
            g=g,
            wacc=wacc,
            tv=tv,
            formula=f"TV = {fcf_n1:.1f} / ({wacc:.2%} - {g:.2%}) = {tv:.1f}"
        )
    
    def calculate_exit_multiple(
        self,
        terminal_metric: float,
        peer_multiples: Optional[List[float]] = None,
        custom_multiple: Optional[float] = None,
    ) -> ExitMultipleResult:
        """退出倍数法"""
        # 确定倍数
        if custom_multiple is not None:
            multiple = custom_multiple
        elif peer_multiples and len(peer_multiples) > 0:
            if self.config.multiple_source == "peer_median":
                import statistics
                multiple = statistics.median(peer_multiples)
            else:
                multiple = sum(peer_multiples) / len(peer_multiples)
        else:
            multiple = self.config.multiple_value
        
        # 验证倍数范围
        warnings = []
        if peer_multiples and len(peer_multiples) > 0:
            import statistics
            p25 = statistics.quantiles(peer_multiples, n=4)[0]
            p75 = statistics.quantiles(peer_multiples, n=4)[2]
            if not (p25 <= multiple <= p75):
                warnings.append(f"退出倍数 {multiple:.1f}x 超出可比公司25-75百分位 [{p25:.1f}x, {p75:.1f}x]")
        
        tv = terminal_metric * multiple
        
        return ExitMultipleResult(
            method="exit_multiple",
            metric=terminal_metric,
            multiple=multiple,
            multiple_type=self.config.multiple_type,
            tv=tv,
            formula=f"TV = {terminal_metric:.1f} × {multiple:.1f}x = {tv:.1f}"
        )
    
    def calculate_tv(
        self,
        final_year_fcf: float,
        wacc: float,
        terminal_metric: float,
        peer_multiples: Optional[List[float]] = None,
        custom_multiple: Optional[float] = None,
        g: Optional[float] = None,
    ) -> TerminalValueResult:
        """主计算入口 - 支持双方法"""
        method = self.config.primary_method
        warnings = []
        
        if method == "perpetuity_growth":
            pg = self.calculate_perpetuity_growth(final_year_fcf, wacc, g)
            return TerminalValueResult(
                method="perpetuity_growth",
                tv=pg.tv,
                warnings=warnings,
            )
        
        elif method == "exit_multiple":
            em = self.calculate_exit_multiple(terminal_metric, peer_multiples, custom_multiple)
            return TerminalValueResult(
                method="exit_multiple",
                tv=em.tv,
                warnings=warnings,
            )
        
        elif method == "dual_method":
            pg = self.calculate_perpetuity_growth(final_year_fcf, wacc, g)
            em = self.calculate_exit_multiple(terminal_metric, peer_multiples, custom_multiple)
            
            w_pg = self.config.weight_perpetuity
            w_em = self.config.weight_exit_multiple
            tv = pg.tv * w_pg + em.tv * w_em
            
            return TerminalValueResult(
                method="dual_method",
                tv=tv,
                tv_perpetuity=pg.tv,
                tv_exit_multiple=em.tv,
                weight_perpetuity=w_pg,
                weight_exit_multiple=w_em,
                detail={"perpetuity": pg, "exit_multiple": em},
                warnings=warnings,
            )
        
        else:
            raise ValueError(f"未知方法: {method}")
    
    def validate_tv_pct(
        self,
        tv: float,
        pv_fcf: float,
    ) -> TVValidationResult:
        """TV占企业价值比例验证"""
        ev = pv_fcf + tv
        tv_pct = tv / ev if ev > 0 else 0
        max_pct = self.config.tv_as_pct_max
        
        warning = None
        if tv_pct > max_pct:
            warning = f"终值占比 {tv_pct:.1%} 超过上限 {max_pct:.0%}，需重新审视假设"
        
        return TVValidationResult(
            tv_pct=tv_pct,
            threshold=max_pct,
            passed=tv_pct <= max_pct,
            warning=warning,
        )
    
    def arbitrate(
        self,
        tv_perpetuity: float,
        tv_exit_multiple: float,
    ) -> Dict:
        """终值仲裁"""
        diff = abs(tv_perpetuity - tv_exit_multiple)
        avg_tv = (tv_perpetuity + tv_exit_multiple) / 2
        diff_pct = diff / avg_tv if avg_tv > 0 else 0
        
        if diff_pct < 0.10:
            # 差异<10%: 取均值
            return {
                "method": "dual_average",
                "chosen_tv": avg_tv,
                "difference_pct": diff_pct,
                "confidence": "high",
                "reasoning": f"两种方法差异{diff_pct:.1%}<10%, 取均值"
            }
        
        elif diff_pct < 0.25:
            # 10-25%: 取保守(较低值)
            conservative_tv = min(tv_perpetuity, tv_exit_multiple)
            return {
                "method": "conservative",
                "chosen_tv": conservative_tv,
                "difference_pct": diff_pct,
                "confidence": "medium",
                "reasoning": f"两种方法差异{diff_pct:.1%}在10-25%区间, 取保守值"
            }
        
        elif diff_pct < 0.50:
            # 25-50%: 取保守+强制敏感性分析
            conservative_tv = min(tv_perpetuity, tv_exit_multiple)
            return {
                "method": "conservative_with_sensitivity",
                "chosen_tv": conservative_tv,
                "difference_pct": diff_pct,
                "confidence": "low",
                "reasoning": f"两种方法差异{diff_pct:.1%}在25-50%区间, 取保守值并强制敏感性分析"
            }
        
        else:
            # ≥50%: 阻断
            raise ValueError(
                f"终值差异过大({diff_pct:.1%}≥50%), "
                f"永续增长法={tv_perpetuity:.0f}, 退出倍数法={tv_exit_multiple:.0f}, "
                f"需人工审查假设"
            )
