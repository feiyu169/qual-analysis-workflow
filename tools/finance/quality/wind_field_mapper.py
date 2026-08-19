"""
WindFieldMapper模块

功能:
- 三市场映射: A股/港股/美股
- 字段名前缀转换
- 错误字段检测

解决: P84 Wind现金流字段映射错误
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class FieldMapping:
    """字段映射"""
    standard_name: str  # 标准名称
    a_share: str  # A股Wind字段
    hk_share: str  # 港股Wind字段
    us_share: str  # 美股Wind字段
    description: str = ""


# 字段映射表
FIELD_MAPPINGS = {
    "operating_cashflow": FieldMapping(
        standard_name="经营活动产生的现金流量净额",
        a_share="S_FA_OCFL_TTM_510200000",
        hk_share="NET_CASH_OPER_ACT_TTM",
        us_share="OPER_CASH_FLOW_TTM",
        description="经营活动产生的现金流量净额(TTM)",
    ),
    "capex": FieldMapping(
        standard_name="购建固定资产、无形资产和其他长期资产支付的现金",
        a_share="S_FA_CAPEX_TTM_510300000",
        hk_share="PUR_FIX_ASSETS_TTM",
        us_share="CAPITAL_EXPENDITURE_TTM",
        description="购建固定资产、无形资产和其他长期资产支付的现金(TTM)",
    ),
    "net_income": FieldMapping(
        standard_name="归属于母公司所有者的净利润",
        a_share="S_FA_NETPROFIT_TTM_510100000",
        hk_share="NET_PROFIT_TTM",
        us_share="NET_INCOME_TTM",
        description="归属于母公司所有者的净利润(TTM)",
    ),
    "ebit": FieldMapping(
        standard_name="息税前利润",
        a_share="S_FA_EBIT_TTM_510400000",
        hk_share="EBIT_TTM",
        us_share="EBIT_TTM",
        description="息税前利润(TTM)",
    ),
    "depreciation": FieldMapping(
        standard_name="折旧与摊销",
        a_share="S_FA_DA_TTM_510500000",
        hk_share="DEPR_AMORT_TTM",
        us_share="DEPRECIATION_AMORTIZATION_TTM",
        description="折旧与摊销(TTM)",
    ),
    "total_assets": FieldMapping(
        standard_name="资产总计",
        a_share="S_FA_TOTAL_ASSETS",
        hk_share="TOTAL_ASSETS",
        us_share="TOTAL_ASSETS",
        description="资产总计",
    ),
    "total_equity": FieldMapping(
        standard_name="归属于母公司所有者权益",
        a_share="S_FA_EQUITY_TTM",
        hk_share="EQUITY_ATTR_P_TTM",
        us_share="TOTAL_EQUITY_TTM",
        description="归属于母公司所有者权益",
    ),
    "revenue": FieldMapping(
        standard_name="营业总收入",
        a_share="S_FA_REVENUE_TTM",
        hk_share="REVENUE_TTM",
        us_share="TOTAL_REVENUE_TTM",
        description="营业总收入(TTM)",
    ),
}


class WindFieldMapper:
    """Wind字段映射器"""
    
    def __init__(self):
        self.mappings = FIELD_MAPPINGS
    
    def get_field_name(
        self,
        standard_name: str,
        market: str,  # "a_share" | "hk_share" | "us_share"
    ) -> Optional[str]:
        """获取Wind字段名"""
        mapping = self.mappings.get(standard_name)
        if not mapping:
            return None
        
        if market == "a_share":
            return mapping.a_share
        elif market == "hk_share":
            return mapping.hk_share
        elif market == "us_share":
            return mapping.us_share
        else:
            return None
    
    def detect_market(self, windcode: str) -> str:
        """根据股票代码检测市场"""
        if windcode.endswith(".SH") or windcode.endswith(".SZ"):
            return "a_share"
        elif windcode.endswith(".HK"):
            return "hk_share"
        elif windcode.endswith(".OQ") or windcode.endswith(".N"):
            return "us_share"
        else:
            return "a_share"  # 默认A股
    
    def map_financial_data(
        self,
        data: Dict[str, any],
        market: str,
    ) -> Dict[str, any]:
        """映射财务数据字段"""
        mapped = {}
        
        for standard_name, value in data.items():
            wind_field = self.get_field_name(standard_name, market)
            if wind_field:
                mapped[wind_field] = value
            else:
                # 保持原字段名
                mapped[standard_name] = value
        
        return mapped
    
    def validate_field_names(
        self,
        data: Dict[str, any],
        market: str,
    ) -> Tuple[List[str], List[str]]:
        """验证字段名"""
        valid = []
        invalid = []
        
        for field_name in data.keys():
            # 检查是否是已知的标准名称
            if field_name in self.mappings:
                valid.append(field_name)
            else:
                # 检查是否是正确的Wind字段名
                is_valid = False
                for mapping in self.mappings.values():
                    if market == "a_share" and field_name == mapping.a_share:
                        is_valid = True
                        break
                    elif market == "hk_share" and field_name == mapping.hk_share:
                        is_valid = True
                        break
                    elif market == "us_share" and field_name == mapping.us_share:
                        is_valid = True
                        break
                
                if is_valid:
                    valid.append(field_name)
                else:
                    invalid.append(field_name)
        
        return valid, invalid
    
    def get_common_mistakes(self, market: str) -> List[str]:
        """获取常见错误"""
        mistakes = []
        
        if market == "a_share":
            mistakes = [
                "使用港股字段名前缀(NET_CASH_*)",
                "使用美股字段名后缀(*_TTM)",
                "缺少市场前缀(S_FA_*)",
            ]
        elif market == "hk_share":
            mistakes = [
                "使用A股字段名前缀(S_FA_*)",
                "使用美股字段名后缀(*_TTM)",
                "缺少市场前缀",
            ]
        elif market == "us_share":
            mistakes = [
                "使用A股字段名前缀(S_FA_*)",
                "使用港股字段名前缀(NET_CASH_*)",
                "缺少市场后缀(*_TTM)",
            ]
        
        return mistakes
    
    def generate_mapping_report(self, market: str) -> str:
        """生成映射报告"""
        lines = [
            f"## Wind字段映射报告 - {market}",
            "",
            "| 标准名称 | Wind字段 |",
            "|----------|----------|",
        ]
        
        for standard_name, mapping in self.mappings.items():
            wind_field = self.get_field_name(standard_name, market)
            if wind_field:
                lines.append(f"| {mapping.description} | {wind_field} |")
        
        return "\n".join(lines)
