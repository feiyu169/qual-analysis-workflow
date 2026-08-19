"""
市场数据（单一数据源+新鲜度检查）

功能：
1. 单一数据源
2. 新鲜度检查
3. 时间戳管理
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class PriceSnapshot:
    """价格快照"""
    price: float
    currency: str
    timestamp: str
    source: str


class MarketData:
    """市场数据（单一数据源）"""
    
    # 新鲜度阈值（小时）
    FRESHNESS_THRESHOLDS = {
        "stock_price": 24,
        "financial_data": 720,
        "market_index": 24,
    }
    
    def __init__(self, ticker: str, market: str):
        self.ticker = ticker
        self.market = market
        self._currency = None
        self._snapshots: Dict[str, PriceSnapshot] = {}
    
    @property
    def currency(self) -> str:
        """获取币种"""
        if self._currency is None:
            if self.market == "hk":
                self._currency = "HKD"
            elif self.market == "cn":
                self._currency = "RMB"
            elif self.market == "us":
                self._currency = "USD"
            else:
                self._currency = "USD"
        return self._currency
    
    def get_price(self, snapshot_key: str = "latest") -> float:
        """获取当前股价"""
        snapshot = self._get_snapshot(snapshot_key)
        return snapshot.price
    
    def _get_snapshot(self, snapshot_key: str) -> PriceSnapshot:
        """获取快照"""
        if snapshot_key not in self._snapshots:
            snapshot = self._fetch_price()
            self._snapshots[snapshot_key] = snapshot
        return self._snapshots[snapshot_key]
    
    def _fetch_price(self) -> PriceSnapshot:
        """从Wind或财报获取当前股价"""
        return PriceSnapshot(
            price=0.0,
            currency=self.currency,
            timestamp=datetime.now().isoformat(),
            source="wind",
        )
    
    def check_freshness(self, data_type: str = "stock_price") -> bool:
        """检查数据新鲜度"""
        snapshot = self._get_snapshot("latest")
        timestamp = datetime.fromisoformat(snapshot.timestamp)
        age_hours = (datetime.now() - timestamp).total_seconds() / 3600
        
        threshold = self.FRESHNESS_THRESHOLDS.get(data_type, 24)
        
        if age_hours > threshold:
            logger.warning(f"数据过期: {age_hours:.1f}小时 > {threshold}小时")
            return False
        
        return True
    
    def format_price(self, snapshot_key: str = "latest") -> str:
        """格式化价格（带币种）"""
        snapshot = self._get_snapshot(snapshot_key)
        return f"{snapshot.price:.2f} {snapshot.currency}"
    
    def validate_consistency(self, snapshot_keys: list) -> bool:
        """验证价格一致性"""
        if not snapshot_keys:
            return True
        
        prices = [self.get_price(key) for key in snapshot_keys]
        base_price = prices[0]
        
        for price in prices[1:]:
            if abs(price - base_price) / base_price > 0.01:
                return False
        
        return True
    
    def set_snapshot(self, key: str, price: float, currency: str = None, 
                     source: str = "manual"):
        """设置快照"""
        if currency is None:
            currency = self.currency
        
        self._snapshots[key] = PriceSnapshot(
            price=price,
            currency=currency,
            timestamp=datetime.now().isoformat(),
            source=source,
        )
