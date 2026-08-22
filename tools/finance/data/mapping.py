"""
数据字段映射注册表（版本控制+schema自动校验）

功能：
1. 字段映射管理
2. 版本控制
3. schema自动校验
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FieldMapping:
    """字段映射"""
    canonical_name: str  # 标准名称
    aliases: list[str]  # 别名列表
    source: str  # 数据来源
    口径: str  # 计算口径
    unit: str  # 单位
    version: str = "1.0"
    last_verified: str = ""


class DataMappingRegistry:
    """数据字段映射注册表"""

    # 字段映射配置
    FIELD_MAPPINGS: dict[str, FieldMapping] = {
        # 利润表
        "营业总收入": FieldMapping(
            canonical_name="营业总收入",
            aliases=["年营业总收入", "过去三年每年营业总收入", "营收"],
            source="Wind",
            口径="IFRS",
            unit="亿元",
        ),
        "营业利润": FieldMapping(
            canonical_name="营业利润",
            aliases=["年营业利润", "过去三年每年营业利润"],
            source="Wind",
            口径="IFRS",
            unit="亿元",
        ),
        "净利润": FieldMapping(
            canonical_name="净利润",
            aliases=["年净利润", "过去三年每年净利润"],
            source="Wind",
            口径="含少数股东",
            unit="亿元",
        ),
        "归母净利润": FieldMapping(
            canonical_name="归母净利润",
            aliases=["年归属母公司股东的净利润"],
            source="Wind",
            口径="归母",
            unit="亿元",
        ),

        # 资产负债表
        "负债合计": FieldMapping(
            canonical_name="负债合计",
            aliases=["年负债合计", "最近3年每年负债合计"],
            source="Wind",
            口径="IFRS",
            unit="亿元",
        ),
        "流动资产合计": FieldMapping(
            canonical_name="流动资产合计",
            aliases=["年流动资产合计", "最近3年每年流动资产合计"],
            source="Wind",
            口径="IFRS",
            unit="亿元",
        ),
        "所有者权益合计": FieldMapping(
            canonical_name="所有者权益合计",
            aliases=["年所有者权益合计", "最近3年每年所有者权益合计"],
            source="Wind",
            口径="IFRS",
            unit="亿元",
        ),
        "现金及等价物": FieldMapping(
            canonical_name="现金及等价物",
            aliases=["现金及等价物", "货币资金"],
            source="Wind",
            口径="IFRS",
            unit="亿元",
        ),

        # 现金流量表
        "经营活动现金流": FieldMapping(
            canonical_name="经营活动现金流",
            aliases=["经营活动现金净流量_TTM", "过去三年每年经营活动产生的现金流量净额"],
            source="Wind",
            口径="IFRS",
            unit="亿元",
        ),
        "资本开支": FieldMapping(
            canonical_name="资本开支",
            aliases=["购建固定资产、无形资产和其他长期资产支付的现金"],
            source="Wind",
            口径="IFRS",
            unit="亿元",
        ),
    }

    # 版本历史
    version_history: list[dict] = []

    @classmethod
    def get_canonical_name(cls, alias: str) -> str | None:
        """获取标准名称"""
        for canonical, mapping in cls.FIELD_MAPPINGS.items():
            if alias in mapping.aliases:
                return canonical
        return None

    @classmethod
    def get_field_value(cls, data: dict, field_name: str):
        """获取字段值（支持多种别名）"""
        mapping = cls.FIELD_MAPPINGS.get(field_name)
        if not mapping:
            return None

        for alias in mapping.aliases:
            if alias in data:
                return data[alias]

        return None

    @classmethod
    def validate_consistency(cls, data: dict) -> list[str]:
        """验证数据一致性"""
        errors = []

        # 检查是否存在多口径
        for canonical, mapping in cls.FIELD_MAPPINGS.items():
            values = []
            for alias in mapping.aliases:
                if alias in data:
                    values.append((alias, data[alias]))

            if len(values) > 1:
                # 检查是否一致
                base_value = values[0][1]
                for alias, value in values[1:]:
                    if isinstance(value, (int, float)) and isinstance(base_value, (int, float)):
                        if abs(value - base_value) / abs(base_value) > 0.01:  # 1%容差
                            errors.append(f"{canonical}存在多口径: {values}")

        return errors

    @classmethod
    def validate_schema(cls, data: dict) -> list[str]:
        """验证schema"""
        errors = []

        # 检查必需字段（双专家 P2：用 canonical 键——canonical 化后"营业总收入"已归一为
        # "营业收入"、年净利润→归母净利润，按旧键名校验会永久误报"缺少必需字段"）
        required_fields = ["营业收入", "营业利润", "归母净利润"]
        for field in required_fields:
            if field not in data:
                # 检查别名
                mapping = cls.FIELD_MAPPINGS.get(field)
                if mapping:
                    found = False
                    for alias in mapping.aliases:
                        if alias in data:
                            found = True
                            break
                    if not found:
                        errors.append(f"缺少必需字段: {field}")

        return errors

    @classmethod
    def update_mapping(cls, field_name: str, new_mapping: FieldMapping):
        """更新映射（记录版本历史）"""
        old_mapping = cls.FIELD_MAPPINGS.get(field_name)

        # 记录版本历史
        cls.version_history.append({
            "timestamp": datetime.now().isoformat(),
            "field_name": field_name,
            "old_version": old_mapping.version if old_mapping else None,
            "new_version": new_mapping.version,
            "change_description": f"更新{field_name}映射",
        })

        cls.FIELD_MAPPINGS[field_name] = new_mapping

    @classmethod
    def get_version_history(cls) -> list[dict]:
        """获取版本历史"""
        return cls.version_history.copy()

    @classmethod
    def validate_mappings(cls, data: dict) -> dict[str, Any]:
        """验证字段映射（兼容workflow.py调用）

        Args:
            data: Wind数据字典

        Returns:
            dict: {"success": bool, "warnings": list}
        """
        warnings = []

        # 验证一致性
        consistency_errors = cls.validate_consistency(data)
        warnings.extend(consistency_errors)

        # 验证schema
        schema_errors = cls.validate_schema(data)
        warnings.extend(schema_errors)

        return {
            "success": len(warnings) == 0,
            "warnings": warnings,
        }
