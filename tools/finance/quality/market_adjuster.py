"""
quality/scoring/market_adjuster.py — 市场评分调整器

策略模式实现：
- MarketScoreAdjuster: 市场评分调整器接口
- CNMarketAdjuster: CN市场调整器
- HKMarketAdjuster: HK市场调整器
- MarketScorerRegistry: 市场评分器注册表
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from ..exceptions import MarketNotSupportedError
from ..types import QualityContext

logger = logging.getLogger(__name__)


class MarketScoreAdjuster(ABC):
    """市场评分调整器接口"""
    
    @abstractmethod
    def adjust(self, base_score: float, context: QualityContext) -> float:
        """调整基础评分
        
        Args:
            base_score: 基础评分
            context: 质量上下文
            
        Returns:
            float: 调整后的评分
        """
        ...
    
    @abstractmethod
    def get_market(self) -> str:
        """获取市场标识"""
        ...


class CNMarketAdjuster(MarketScoreAdjuster):
    """CN市场调整器
    
    特化规则：
    - 扣非净利润优先
    - 经营现金流权重高
    - 关联交易/商誉/应收账款特检
    """
    
    def get_market(self) -> str:
        return "CN"
    
    def adjust(self, base_score: float, context: QualityContext) -> float:
        score = base_score
        extra = context.extra_info
        
        # 扣非净利润优先
        if extra.get("deducted_net_income"):
            score += 2.0
            logger.debug("CN调整: 扣非净利润 +2.0")
        
        # 经营现金流权重高
        ocf = extra.get("operating_cashflow", 0)
        ni = extra.get("net_income", 0)
        if ni > 0 and ocf / ni > 0.8:
            score += 3.0
            logger.debug("CN调整: 经营现金流/净利润>80% +3.0")
        
        # 关联交易特检
        related_ratio = extra.get("related_party_ratio", 0)
        if related_ratio > 0.1:
            score -= 5.0
            logger.debug(f"CN调整: 关联交易{related_ratio:.1%} -5.0")
        
        # 商誉特检
        goodwill_ratio = extra.get("goodwill_ratio", 0)
        if goodwill_ratio > 0.2:
            score -= 3.0
            logger.debug(f"CN调整: 商誉{goodwill_ratio:.1%} -3.0")
        
        # 应收账款特检
        ar_ratio = extra.get("accounts_receivable_ratio", 0)
        if ar_ratio > 0.3:
            score -= 2.0
            logger.debug(f"CN调整: 应收账款{ar_ratio:.1%} -2.0")
        
        return max(0, min(score, 100))


class HKMarketAdjuster(MarketScoreAdjuster):
    """HK市场调整器
    
    特化规则：
    - NAV/核心盈利优先
    - 双币种处理
    - HKFRS准则
    - 南下资金/做空风险
    """
    
    def get_market(self) -> str:
        return "HK"
    
    def adjust(self, base_score: float, context: QualityContext) -> float:
        score = base_score
        extra = context.extra_info
        
        # NAV/核心盈利优先
        if extra.get("nav_per_share"):
            score += 2.0
            logger.debug("HK调整: NAV +2.0")
        if extra.get("core_earnings"):
            score += 2.0
            logger.debug("HK调整: 核心盈利 +2.0")
        
        # 双币种处理
        if extra.get("dual_currency"):
            score += 1.0
            logger.debug("HK调整: 双币种 +1.0")
        
        # HKFRS准则
        if extra.get("accounting_standard") == "HKFRS":
            score += 1.0
            logger.debug("HK调整: HKFRS +1.0")
        
        # 南下资金
        if extra.get("southbound_flow"):
            score += 1.0
            logger.debug("HK调整: 南下资金 +1.0")
        
        # 做空风险
        short_ratio = extra.get("short_selling_ratio", 0)
        if short_ratio > 0.1:
            score -= 3.0
            logger.debug(f"HK调整: 做空{short_ratio:.1%} -3.0")
        
        return max(0, min(score, 100))


class MarketScorerRegistry:
    """市场评分器注册表"""
    
    def __init__(self):
        self._adjusters: dict[str, MarketScoreAdjuster] = {}
    
    def register(self, adjuster: MarketScoreAdjuster) -> None:
        """注册市场调整器"""
        market = adjuster.get_market()
        self._adjusters[market] = adjuster
        logger.info(f"注册市场调整器: {market}")
    
    def get_adjuster(self, market: str) -> Optional[MarketScoreAdjuster]:
        """获取市场调整器"""
        return self._adjusters.get(market.upper())
    
    def adjust_score(self, market: str, base_score: float, context: QualityContext) -> float:
        """调整评分
        
        Args:
            market: 市场标识
            base_score: 基础评分
            context: 质量上下文
            
        Returns:
            float: 调整后的评分
            
        Raises:
            MarketNotSupportedError: 市场不支持
        """
        adjuster = self.get_adjuster(market)
        if adjuster is None:
            raise MarketNotSupportedError(
                message=f"市场 {market} 不支持",
                market=market
            )
        
        return adjuster.adjust(base_score, context)
    
    def list_markets(self) -> list[str]:
        """列出支持的市场"""
        return list(self._adjusters.keys())


# 默认注册表
_default_registry = None


def get_default_registry() -> MarketScorerRegistry:
    """获取默认注册表"""
    global _default_registry
    if _default_registry is None:
        _default_registry = MarketScorerRegistry()
        _default_registry.register(CNMarketAdjuster())
        _default_registry.register(HKMarketAdjuster())
    return _default_registry
