"""
quality/data_mapping.py — 数据口径映射表

定义投资分析中的数据口径映射，避免口径不一致问题。

原则：
1. 每个指标有明确的口径定义
2. 每个口径有对应的数据源
3. 不同口径之间有转换关系
4. 口径差异有明确的说明
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DataDefinition:
    """数据定义"""
    name: str
    description: str
    unit: str
    source: str
    formula: str
    notes: list[str] = field(default_factory=list)


@dataclass
class DataMapping:
    """数据口径映射"""
    indicator: str
    definitions: dict[str, DataDefinition]
    conversion_rules: dict[str, str] = field(default_factory=dict)


class DataMappingRegistry:
    """数据口径映射注册表"""
    
    def __init__(self):
        self._mappings: dict[str, DataMapping] = {}
        self._register_defaults()
    
    def _register_defaults(self):
        """注册默认映射"""
        
        # ─────────────────────────────────────────────────
        # 净利润口径
        # ─────────────────────────────────────────────────
        self._mappings["net_income"] = DataMapping(
            indicator="净利润",
            definitions={
                "GAAP": DataDefinition(
                    name="归母净利润",
                    description="归属于母公司股东的净利润（IFRS/CAS准则）",
                    unit="亿元",
                    source="Wind财务数据/年报利润表",
                    formula="净利润 - 少数股东损益",
                    notes=[
                        "A股/港股标准口径",
                        "Wind字段: 年归属母公司股东的净利润",
                        "与'扣非净利润'不同"
                    ]
                ),
                "adjusted": DataDefinition(
                    name="经调整净利润",
                    description="Non-IFRS准则下的经调整净利润（剔除股权激励等非经常性项目）",
                    unit="亿元",
                    source="公司公告/财报附注",
                    formula="归母净利润 + 股权激励费用 + 收购相关摊销 + 其他非经常性项目",
                    notes=[
                        "港股互联网公司常用口径",
                        "快手、腾讯、美团等均使用此口径",
                        "与GAAP口径差异通常在10-30%",
                        "⚠️ 必须明确标注使用的是哪种口径"
                    ]
                ),
                "core": DataDefinition(
                    name="核心盈利",
                    description="核心经营利润（剔除非经营性收益）",
                    unit="亿元",
                    source="公司公告/券商研报",
                    formula="经营利润 + 联营公司核心盈利",
                    notes=[
                        "港股地产公司常用口径",
                        "与归母净利润差异较大"
                    ]
                ),
                "deducted": DataDefinition(
                    name="扣非净利润",
                    description="扣除非经常性损益后的净利润",
                    unit="亿元",
                    source="Wind财务数据/年报",
                    formula="净利润 - 非经常性损益",
                    notes=[
                        "A股特有口径",
                        "Wind字段: 年扣除非经常性损益后的净利润",
                        "与'归母净利润'不同"
                    ]
                ),
            },
            conversion_rules={
                "GAAP→adjusted": "需获取Non-IFRS调整项（股权激励、收购摊销等）",
                "GAAP→deducted": "需获取非经常性损益明细",
                "adjusted→GAAP": "减去调整项",
            }
        )
        
        # ─────────────────────────────────────────────────
        # 净资产口径
        # ─────────────────────────────────────────────────
        self._mappings["equity"] = DataMapping(
            indicator="净资产",
            definitions={
                "total": DataDefinition(
                    name="总权益",
                    description="所有者权益合计（含少数股东权益）",
                    unit="亿元",
                    source="Wind财务数据/年报资产负债表",
                    formula="总资产 - 总负债",
                    notes=[
                        "包含少数股东权益",
                        "⚠️ 不能用于PB计算"
                    ]
                ),
                "parent": DataDefinition(
                    name="归母净资产",
                    description="归属于母公司股东的权益",
                    unit="亿元",
                    source="Wind财务数据/年报资产负债表",
                    formula="总权益 - 少数股东权益",
                    notes=[
                        "不包含少数股东权益",
                        "✅ PB计算必须使用此口径"
                    ]
                ),
            },
            conversion_rules={
                "total→parent": "减去少数股东权益",
                "parent→total": "加上少数股东权益",
            }
        )
        
        # ─────────────────────────────────────────────────
        # 股本口径
        # ─────────────────────────────────────────────────
        self._mappings["shares"] = DataMapping(
            indicator="股本",
            definitions={
                "total": DataDefinition(
                    name="总股本",
                    description="公司发行的全部股份总数",
                    unit="亿股",
                    source="Wind股票数据/公司公告",
                    formula="",
                    notes=[
                        "⚠️ 注意单位换算",
                        "Wind可能返回万股，需转换为亿股",
                        "1亿股 = 10000万股"
                    ]
                ),
                "float": DataDefinition(
                    name="流通股本",
                    description="可以在二级市场自由买卖的股份",
                    unit="亿股",
                    source="Wind股票数据",
                    formula="总股本 - 限售股",
                    notes=[
                        "港股通常全流通",
                        "A股有限售股"
                    ]
                ),
                "diluted": DataDefinition(
                    name="稀释股本",
                    description="考虑期权、可转债等稀释效应后的股本",
                    unit="亿股",
                    source="Wind财务数据/年报",
                    formula="总股本 + 期权行权 + 可转债转股",
                    notes=[
                        "PE计算应使用稀释股本",
                        "但通常使用总股本近似"
                    ]
                ),
            }
        )
        
        # ─────────────────────────────────────────────────
        # 估值指标口径
        # ─────────────────────────────────────────────────
        self._mappings["pe"] = DataMapping(
            indicator="PE（市盈率）",
            definitions={
                "ttm_gaap": DataDefinition(
                    name="PE(TTM)-GAAP",
                    description="基于过去12个月GAAP净利润的市盈率",
                    unit="倍",
                    source="Wind估值数据",
                    formula="市值 / 过去12个月归母净利润",
                    notes=[
                        "A股标准PE口径",
                        "Wind直接提供"
                    ]
                ),
                "ttm_adjusted": DataDefinition(
                    name="PE(TTM)-Adjusted",
                    description="基于过去12个月经调整净利润的市盈率",
                    unit="倍",
                    source="手动计算",
                    formula="市值 / 过去12个月经调整净利润",
                    notes=[
                        "港股互联网公司常用口径",
                        "⚠️ 必须明确标注使用的是哪种口径",
                        "快手：市值 / Non-IFRS净利润"
                    ]
                ),
                "forward": DataDefinition(
                    name="PE(Forward)",
                    description="基于未来12个月预期净利润的市盈率",
                    unit="倍",
                    source="Wind一致预期",
                    formula="市值 / 未来12个月预期净利润",
                    notes=[
                        "使用分析师一致预期",
                        "Wind提供一致预期数据"
                    ]
                ),
            }
        )
        
        # ─────────────────────────────────────────────────
        # 增长率口径
        # ─────────────────────────────────────────────────
        self._mappings["growth"] = DataMapping(
            indicator="增长率",
            definitions={
                "yoy": DataDefinition(
                    name="同比增长率",
                    description="与去年同期相比的增长率",
                    unit="%",
                    source="手动计算",
                    formula="(当期 - 去年同期) / |去年同期| × 100%",
                    notes=[
                        "最常用的增长率口径",
                        "注意：如果去年同期为负，计算可能失真"
                    ]
                ),
                "qoq": DataDefinition(
                    name="环比增长率",
                    description="与上个季度相比的增长率",
                    unit="%",
                    source="手动计算",
                    formula="(当期 - 上期) / |上期| × 100%",
                    notes=[
                        "季度数据常用",
                        "注意季节性因素"
                    ]
                ),
                "cagr": DataDefinition(
                    name="复合年增长率",
                    description="多年期的年均增长率",
                    unit="%",
                    source="手动计算",
                    formula="(终止值/起始值)^(1/年数) - 1",
                    notes=[
                        "多年期增长率",
                        "消除单年波动影响"
                    ]
                ),
            }
        )
    
    def get_mapping(self, indicator: str) -> Optional[DataMapping]:
        """获取数据口径映射"""
        return self._mappings.get(indicator)
    
    def get_definition(self, indicator: str,口径: str) -> Optional[DataDefinition]:
        """获取数据定义"""
        mapping = self.get_mapping(indicator)
        if mapping:
            return mapping.definitions.get(口径)
        return None
    
    def list_indicators(self) -> list[str]:
        """列出所有指标"""
        return list(self._mappings.keys())
    
    def list_口径s(self, indicator: str) -> list[str]:
        """列出指标的所有口径"""
        mapping = self.get_mapping(indicator)
        if mapping:
            return list(mapping.definitions.keys())
        return []


# 默认注册表
_default_registry = None


def get_default_mapping_registry() -> DataMappingRegistry:
    """获取默认注册表"""
    global _default_registry
    if _default_registry is None:
        _default_registry = DataMappingRegistry()
    return _default_registry
