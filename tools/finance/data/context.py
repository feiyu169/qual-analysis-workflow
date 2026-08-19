"""
数据上下文（统一口径+口径校验）

功能：
1. 统一数据访问
2. 口径校验
3. 币种管理
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class DataContext:
    """
    数据上下文
    
    统一管理财务数据、口径、币种等
    """
    
    # 财务数据
    financials: dict = field(default_factory=dict)
    
    # 市场
    market: str = "hk"
    
    # 币种
    _currency: str = None
    
    # 净利润口径
    _net_income: Optional[float] = None
    _net_income_parent: Optional[float] = None
    
    # 口径声明
    _declared_basis: str = "parent"  # 默认使用归母
    
    # 数据来源
    _data_sources: Dict[str, str] = field(default_factory=dict)
    
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
    
    @property
    def net_income(self) -> float:
        """获取净利润（含少数股东）"""
        if self._net_income is None:
            self._net_income = self._get_field_value("净利润")
        return self._net_income
    
    @property
    def net_income_parent(self) -> float:
        """获取归母净利润"""
        if self._net_income_parent is None:
            self._net_income_parent = self._get_field_value("归母净利润")
        return self._net_income_parent
    
    def get_net_income(self, basis: str = None) -> float:
        """获取净利润（指定口径）"""
        if basis is None:
            basis = self._declared_basis
        
        # 口径校验
        self._validate_basis(basis)
        
        if basis == "parent":
            return self.net_income_parent
        elif basis == "consolidated":
            return self.net_income
        else:
            raise ValueError(f"未知口径: {basis}")
    
    def _validate_basis(self, basis: str):
        """口径校验"""
        valid_bases = ["parent", "consolidated"]
        if basis not in valid_bases:
            raise ValueError(f"无效口径: {basis}，有效值: {valid_bases}")
    
    def _get_field_value(self, field_name: str) -> float:
        """获取字段值"""
        # 直接查找
        if field_name in self.financials:
            value = self.financials[field_name]
            if isinstance(value, list):
                return value[-1] if value else 0
            return value
        
        # 查找别名
        from .mapping import DataMappingRegistry
        value = DataMappingRegistry.get_field_value(self.financials, field_name)
        if value is not None:
            if isinstance(value, list):
                return value[-1] if value else 0
            return value
        
        return 0
    
    def format_net_income(self, basis: str = None) -> str:
        """格式化净利润（带口径标注）"""
        if basis is None:
            basis = self._declared_basis
        
        value = self.get_net_income(basis)
        if basis == "parent":
            return f"{value:.2f}亿元（归母）"
        else:
            return f"{value:.2f}亿元（含少数股东）"
    
    def format_price(self, price: float) -> str:
        """格式化价格（带币种）"""
        return f"{price:.2f} {self.currency}"
    
    def convert_currency(self, amount: float, from_currency: str, 
                        to_currency: str, rate: float) -> float:
        """货币转换"""
        if from_currency == to_currency:
            return amount
        return amount * rate
    
    def set_data_source(self, field_name: str, source: str):
        """设置数据来源"""
        self._data_sources[field_name] = source
    
    def get_data_source(self, field_name: str) -> Optional[str]:
        """获取数据来源"""
        return self._data_sources.get(field_name)
    
    def validate_data_sources(self) -> List[str]:
        """验证数据来源"""
        errors = []
        
        # 检查关键字段是否有数据来源
        required_sources = ["营业总收入", "净利润", "营业利润"]
        for field in required_sources:
            if field not in self._data_sources:
                errors.append(f"字段'{field}'缺少数据来源标注")
        
        return errors
