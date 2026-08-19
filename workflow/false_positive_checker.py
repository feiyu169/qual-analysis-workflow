"""
误报处理工具 - V3.0 方案
检查是否为已知误报或豁免
"""

from dataclasses import dataclass
from datetime import datetime

import structlog
import yaml

logger = structlog.get_logger()


@dataclass
class FalsePositive:
    """误报"""

    id: str
    rule: str
    file: str
    reason: str
    approved_by: str
    expiry: str | None
    permanent: bool


@dataclass
class Exemption:
    """豁免"""

    id: str
    type: str
    description: str
    scope: str
    approved_by: str
    expiry: str | None
    conditions: list[str]


class FalsePositiveChecker:
    """误报检查器"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            import os

            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "config",
                "exceptions.yaml",
            )
        self.config_path = config_path
        self.config = self._load_config()
        self.false_positives = self._parse_false_positives()
        self.exemptions = self._parse_exemptions()

    def _load_config(self) -> dict:
        """加载配置"""
        try:
            import os

            expanded_path = os.path.expanduser(self.config_path)
            with open(expanded_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning("exceptions_config_not_found", path=self.config_path)
            return {}

    def _parse_false_positives(self) -> list[FalsePositive]:
        """解析误报配置"""
        fps = []
        for fp in self.config.get("known_false_positives", []):
            fps.append(
                FalsePositive(
                    id=fp["id"],
                    rule=fp["rule"],
                    file=fp["file"],
                    reason=fp["reason"],
                    approved_by=fp["approved_by"],
                    expiry=fp.get("expiry"),
                    permanent=fp.get("permanent", False),
                )
            )
        return fps

    def _parse_exemptions(self) -> list[Exemption]:
        """解析豁免配置"""
        exemptions = []
        for ex in self.config.get("exemptions", []):
            exemptions.append(
                Exemption(
                    id=ex["id"],
                    type=ex["type"],
                    description=ex["description"],
                    scope=ex["scope"],
                    approved_by=ex["approved_by"],
                    expiry=ex.get("expiry"),
                    conditions=ex.get("conditions", []),
                )
            )
        return exemptions

    def is_false_positive(self, rule: str, file: str) -> bool:
        """
        检查是否为已知误报

        Args:
            rule: 门禁规则
            file: 文件路径

        Returns:
            bool: 是否为误报
        """
        for fp in self.false_positives:
            if fp.rule == rule and fp.file == file:
                # 永久误报
                if fp.permanent:
                    logger.info("false_positive_matched", fp_id=fp.id, permanent=True)
                    return True

                # 检查是否过期
                if fp.expiry:
                    expiry_date = datetime.fromisoformat(fp.expiry)
                    if expiry_date > datetime.now():
                        logger.info(
                            "false_positive_matched", fp_id=fp.id, expiry=fp.expiry
                        )
                        return True
                    else:
                        logger.info(
                            "false_positive_expired", fp_id=fp.id, expiry=fp.expiry
                        )

        return False

    def has_exemption(self, exemption_type: str, context: dict = None) -> bool:
        """
        检查是否有豁免

        Args:
            exemption_type: 豁免类型
            context: 上下文信息

        Returns:
            bool: 是否有豁免
        """
        for ex in self.exemptions:
            if ex.type == exemption_type:
                # 检查是否过期
                if ex.expiry:
                    expiry_date = datetime.fromisoformat(ex.expiry)
                    if expiry_date < datetime.now():
                        logger.info("exemption_expired", ex_id=ex.id, expiry=ex.expiry)
                        continue

                # 检查条件
                if context and ex.conditions:
                    conditions_met = self._check_conditions(ex.conditions, context)
                    if conditions_met:
                        logger.info("exemption_matched", ex_id=ex.id, type=ex.type)
                        return True
                else:
                    logger.info("exemption_matched", ex_id=ex.id, type=ex.type)
                    return True

        return False

    def _check_conditions(self, conditions: list[str], context: dict) -> bool:
        """检查条件"""
        # 简化实现：检查上下文中是否有对应的标记
        for condition in conditions:
            # 将条件转换为检查键
            check_key = condition.replace("不涉及", "no_").replace("涉及", "has_")
            check_key = check_key.replace(" ", "_").lower()

            if check_key not in context:
                return False

        return True

    def get_false_positive(self, rule: str, file: str) -> FalsePositive | None:
        """获取误报详情"""
        for fp in self.false_positives:
            if fp.rule == rule and fp.file == file:
                return fp
        return None

    def get_exemption(self, exemption_type: str) -> Exemption | None:
        """获取豁免详情"""
        for ex in self.exemptions:
            if ex.type == exemption_type:
                return ex
        return None

    def list_false_positives(self) -> list[FalsePositive]:
        """列出所有误报"""
        return self.false_positives

    def list_exemptions(self) -> list[Exemption]:
        """列出所有豁免"""
        return self.exemptions

    def is_expired(self, fp: FalsePositive) -> bool:
        """检查误报是否过期"""
        if fp.permanent:
            return False
        if fp.expiry:
            expiry_date = datetime.fromisoformat(fp.expiry)
            return expiry_date < datetime.now()
        return True


# 全局实例
false_positive_checker = FalsePositiveChecker()


def is_false_positive(rule: str, file: str) -> bool:
    """检查是否为误报（对外接口）"""
    return false_positive_checker.is_false_positive(rule, file)


def has_exemption(exemption_type: str, context: dict = None) -> bool:
    """检查是否有豁免（对外接口）"""
    return false_positive_checker.has_exemption(exemption_type, context)
