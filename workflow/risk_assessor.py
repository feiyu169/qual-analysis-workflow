"""
风险评估器 - V5 方案实现
英文键 + 映射表 + 中文关键词 + 安全护栏
"""

from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


@dataclass
class RiskAssessmentResult:
    """风险评估结果"""

    risk: str  # low, medium, high
    score: int
    matched_factors: list[str]
    combination_bonus: int
    reduction_applied: bool


class RiskAssessorError(Exception):
    """风险评估错误"""


class RiskAssessor:
    """风险评估器"""

    # 风险因素（英文键）
    RISK_FACTORS = {
        # 安全类（权重 3）
        "security": 3,
        "auth": 3,
        "authentication": 3,
        "authorization": 3,
        "payment": 3,
        "billing": 3,
        "privacy": 3,
        "crypto": 3,
        "encryption": 3,
        # 数据类（权重 2-3）
        "database": 2,
        "migration": 3,
        "concurrency": 2,
        "transaction": 2,
        # 依赖类（权重 2）
        "external_api": 2,
        "third_party": 2,
        "config": 2,
        # 接口类（权重 3）
        "breaking_change": 3,
        "core_algorithm": 3,
        "public_library": 3,
        "core": 3,
        "kernel": 3,
        # 业务类（权重 2）
        "user_impact": 2,
        "business": 2,
        "performance": 2,
        "compliance": 2,
        # 其他风险因素
        "command_execution": 3,
        "file_operation": 2,
        "log_sensitive": 2,
        "serialization": 2,
        "xss": 3,
        "injection": 3,
        "rate_limiting": 2,
        "date_time": 1,
    }

    # 高风险因子列表（安全护栏）
    HIGH_RISK_FACTORS = [
        "security",
        "auth",
        "authentication",
        "authorization",
        "payment",
        "billing",
        "crypto",
        "encryption",
        "injection",
        "xss",
        "command_execution",
    ]

    # 映射表（目录名/模块名 → 风险因素）
    RISK_MAPPING = {
        # 认证相关
        "auth": "auth",
        "authentication": "authentication",
        "authorization": "authorization",
        "login": "auth",
        "signup": "auth",
        "register": "auth",
        "oauth": "auth",
        "sso": "auth",
        "jwt": "auth",
        "session": "auth",
        "cookie": "auth",
        # 支付相关
        "payment": "payment",
        "billing": "billing",
        "checkout": "payment",
        "invoice": "billing",
        "subscription": "billing",
        "stripe": "payment",
        "paypal": "payment",
        # 数据相关
        "database": "database",
        "db": "database",
        "migration": "migration",
        "schema": "database",
        "sql": "database",
        "mongo": "database",
        "redis": "database",
        # 安全相关
        "security": "security",
        "crypto": "crypto",
        "encryption": "encryption",
        "hash": "crypto",
        "password": "security",
        "secret": "security",
        "token": "security",
        "cors": "security",
        "csrf": "security",
        "xss": "xss",
        # 核心相关
        "core": "core",
        "kernel": "kernel",
        "engine": "core",
        "framework": "core",
        # API 相关
        "api": "external_api",
        "webhook": "external_api",
        "integration": "external_api",
        "rest": "external_api",
        "graphql": "external_api",
        # 配置相关
        "config": "config",
        "settings": "config",
        "env": "config",
        "dotenv": "config",
        # 用户相关
        "user": "user_impact",
        "admin": "user_impact",
        "profile": "user_impact",
        "account": "user_impact",
        # 订单相关
        "order": "business",
        "cart": "business",
        "product": "business",
        "inventory": "business",
        "business": "user_impact",
        # 性能相关
        "performance": "performance",
        "cache": "performance",
        "optimization": "performance",
        # 隐私相关
        "privacy": "privacy",
        "gdpr": "privacy",
        "pii": "privacy",
        "personal": "privacy",
    }

    # 中文关键词映射
    KEYWORD_MAPPING = {
        # 支付相关
        "支付": "payment",
        "付款": "payment",
        "账单": "billing",
        "转账": "payment",
        # 认证相关
        "鉴权": "auth",
        "认证": "authentication",
        "授权": "authorization",
        "登录": "auth",
        "注册": "auth",
        "越权": "auth",
        # 数据相关
        "数据库": "database",
        "迁移": "migration",
        "数据": "database",
        # 安全相关
        "安全": "security",
        "加密": "encryption",
        "密码": "security",
        "密钥": "crypto",
        "漏洞": "security",
        "注入": "injection",
        # 隐私相关
        "隐私": "privacy",
        "个人": "privacy",
        "敏感": "privacy",
        # 性能相关
        "性能": "performance",
        "缓存": "performance",
        # 配置相关
        "配置": "config",
        "设置": "config",
        # 用户相关
        "用户": "user_impact",
        "管理员": "user_impact",
        # 业务相关
        "订单": "business",
        "商品": "business",
        "库存": "business",
        # API 相关
        "接口": "external_api",
        "webhook": "external_api",
    }

    # 组合加成规则
    COMBINATION_RULES = [
        (["auth", "payment"], 3),
        (["privacy", "external_api"], 2),
        (["crypto", "database"], 2),
        (["security", "auth"], 2),
        (["payment", "external_api"], 2),
        (["auth", "database"], 2),
        (["security", "database"], 2),
        (["injection", "database"], 2),
    ]

    # 风险降低关键词
    REDUCTION_KEYWORDS = {
        "fix": -1,
        "patch": -1,
        "refactor": -1,
        "rename": -1,
        "format": -2,
        "style": -2,
        "typo": -2,
        "comment": -2,
        "readme": -2,
    }

    # 风险阈值
    RISK_THRESHOLDS = {
        "low": 3,
        "medium": 5,
        "high": 8,
    }

    def __init__(self, config: dict = None):
        """初始化风险评估器"""
        if config:
            self.RISK_FACTORS.update(config.get("risk_factors", {}))
            self.RISK_MAPPING.update(config.get("risk_mapping", {}))
            self.KEYWORD_MAPPING.update(config.get("keyword_mapping", {}))
            self.HIGH_RISK_FACTORS = config.get(
                "high_risk_factors", self.HIGH_RISK_FACTORS
            )
            self.COMBINATION_RULES = config.get(
                "combination_rules", self.COMBINATION_RULES
            )
            self.RISK_THRESHOLDS = config.get("risk_thresholds", self.RISK_THRESHOLDS)

    def assess_risk(
        self, affected_areas: list[str], description: str = ""
    ) -> RiskAssessmentResult:
        """
        风险评估

        Args:
            affected_areas: 影响区域列表
            description: 任务描述（用于风险降低规则）

        Returns:
            RiskAssessmentResult: 风险评估结果

        Raises:
            RiskAssessorError: 评估失败
        """
        try:
            risk_score = 0
            matched_factors = []
            combination_bonus = 0
            reduction_applied = False

            # 1. 映射到风险因素
            for area in affected_areas:
                area_lower = area.lower()

                # 直接匹配
                if area_lower in self.RISK_FACTORS:
                    risk_score += self.RISK_FACTORS[area_lower]
                    matched_factors.append(area_lower)
                # 目录/模块名映射
                elif area_lower in self.RISK_MAPPING:
                    mapped_factor = self.RISK_MAPPING[area_lower]
                    if mapped_factor in self.RISK_FACTORS:
                        risk_score += self.RISK_FACTORS[mapped_factor]
                        matched_factors.append(mapped_factor)
                # 中文/英文关键词映射（影响区域本身可能是中文，如 "支付"）
                elif area_lower in self.KEYWORD_MAPPING:
                    mapped_factor = self.KEYWORD_MAPPING[area_lower]
                    if mapped_factor in self.RISK_FACTORS:
                        risk_score += self.RISK_FACTORS[mapped_factor]
                        matched_factors.append(mapped_factor)

            # 1b. 描述关键词映射（中文/英文：登录→auth、支付→payment、漏洞→security…）
            # V3.1 修复：此前 KEYWORD_MAPPING 定义后从未被使用（P31 教训：映射未接线）
            if description:
                description_lower = description.lower()
                for keyword, factor in self.KEYWORD_MAPPING.items():
                    kw_lower = keyword.lower()
                    if (
                        kw_lower
                        and kw_lower in description_lower
                        and factor in self.RISK_FACTORS
                        and factor not in matched_factors
                    ):
                        risk_score += self.RISK_FACTORS[factor]
                        matched_factors.append(factor)

            # 2. 组合加成规则（每个 factor 只参与一次组合加成）
            used_in_combination = set()
            for factors, bonus in self.COMBINATION_RULES:
                if all(f in matched_factors for f in factors) and not any(
                    f in used_in_combination for f in factors
                ):
                    risk_score += bonus
                    combination_bonus += bonus
                    used_in_combination.update(factors)
                    logger.info("combination_bonus", factors=factors, bonus=bonus)

            # 3. 安全护栏：已命中高权重因子时不降级
            has_high_risk = any(f in matched_factors for f in self.HIGH_RISK_FACTORS)

            if not has_high_risk and description:
                # 4. 风险降低规则
                description_lower = description.lower()
                for keyword, reduction in self.REDUCTION_KEYWORDS.items():
                    if keyword in description_lower:
                        risk_score += reduction
                        reduction_applied = True
                        logger.info(
                            "risk_reduction", keyword=keyword, reduction=reduction
                        )

            # 5. 分数下限保护
            risk_score = max(risk_score, 0)

            # 6. 风险等级判定
            if risk_score >= self.RISK_THRESHOLDS["high"]:
                risk = "high"
            elif risk_score >= self.RISK_THRESHOLDS["medium"]:
                risk = "medium"
            else:
                risk = "low"

            logger.info(
                "risk_assessed",
                risk=risk,
                score=risk_score,
                matched_factors=matched_factors,
                combination_bonus=combination_bonus,
                reduction_applied=reduction_applied,
                has_high_risk=has_high_risk,
            )

            return RiskAssessmentResult(
                risk=risk,
                score=risk_score,
                matched_factors=matched_factors,
                combination_bonus=combination_bonus,
                reduction_applied=reduction_applied,
            )

        except Exception as e:
            logger.error("risk_assessment_failed", error=str(e))
            raise RiskAssessorError(f"风险评估失败: {e!s}")

    def get_affected_areas(
        self,
        files: list[str],
        description: str = "",
        labels: list[str] = None,
        commit_messages: list[str] = None,
    ) -> list[str]:
        """
        获取影响区域

        Args:
            files: 文件列表
            description: 任务描述
            labels: PR 标签
            commit_messages: commit 消息

        Returns:
            List[str]: 影响区域列表
        """
        affected_areas = []

        # 文件过滤规则
        ignore_patterns = [
            "vendor/",
            "node_modules/",
            "*.pb.go",
            "tests/",
            "test/",
            "__tests__/",
            "spec/",
        ]

        # 1. 从文件路径提取（最后两级目录 + 文件名）
        for file in files:
            # 过滤无关文件
            if any(pattern in file for pattern in ignore_patterns):
                continue

            # 取最后两级目录
            parts = file.split("/")
            for part in parts[-2:]:
                part_lower = part.lower()
                if part_lower in self.RISK_MAPPING:
                    affected_areas.append(self.RISK_MAPPING[part_lower])

            # 也检查文件名（去掉扩展名）
            filename = parts[-1].split(".")[0].lower() if parts else ""
            if filename and filename in self.RISK_MAPPING:
                affected_areas.append(self.RISK_MAPPING[filename])

        # 2. 从任务描述提取（中英文）
        if description:
            description_lower = description.lower()
            for keyword, risk in self.KEYWORD_MAPPING.items():
                if keyword in description_lower:
                    affected_areas.append(risk)

        # 3. 从 PR 标签提取
        if labels:
            for label in labels:
                label_lower = label.lower()
                if label_lower in self.RISK_MAPPING:
                    affected_areas.append(self.RISK_MAPPING[label_lower])

        # 4. 从 commit message 提取
        if commit_messages:
            for msg in commit_messages:
                msg_lower = msg.lower()
                for keyword, risk in self.KEYWORD_MAPPING.items():
                    if keyword in msg_lower:
                        affected_areas.append(risk)

        # 去重
        return list(set(affected_areas))
