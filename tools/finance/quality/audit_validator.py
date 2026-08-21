"""
AuditValidator模块

功能:
- 5种检查模式: known_issues, config_check, module_call, self_audit, cross_validation
- 已知问题模式库
- 评分标准差检查

解决: S05 审计未生效
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AuditIssue:
    """审计问题"""
    pattern: str
    severity: str  # FATAL | ERROR | WARN
    message: str
    suggestion: str = ""


# 已知问题模式库
KNOWN_ISSUES = {
    "wacc_hardcoded": AuditIssue(
        pattern="WACC.*10%",
        severity="ERROR",
        message="WACC硬编码10%，未使用CAPM计算",
        suggestion="使用CAPM公式计算WACC",
    ),
    "dcf_null": AuditIssue(
        pattern="DCF.*null|DCF.*None",
        severity="FATAL",
        message="DCF结果为null，估值计算失败",
        suggestion="检查FCF预测和WACC参数",
    ),
    "year_mismatch": AuditIssue(
        pattern="2024财年.*3082",
        severity="ERROR",
        message="年份错标：3082亿是FY2025数据",
        suggestion="修正年份标注",
    ),
    "fcf_negative": AuditIssue(
        pattern="FCF.*负|FCF.*-",
        severity="WARN",
        message="FCF为负值，可能影响估值",
        suggestion="检查经营现金流和资本支出",
    ),
    "ai_trace": AuditIssue(
        pattern="作为AI|作为语言模型|根据我的分析",
        severity="ERROR",
        message="包含AI痕迹",
        suggestion="移除AI相关表述",
    ),
    "conclusion_contradiction": AuditIssue(
        pattern="买入.*风险|卖出.*机会",
        severity="ERROR",
        message="结论与风险提示矛盾",
        suggestion="统一结论表述",
    ),
    "pe_mismatch": AuditIssue(
        pattern="PE.*25.*PE.*18",
        severity="WARN",
        message="PE口径不一致",
        suggestion="统一使用同一PE口径",
    ),
    "score_stddev": AuditIssue(
        pattern="评分.*标准差",
        severity="WARN",
        message="评分标准差过小，可能过于乐观",
        suggestion="增加评分差异性",
    ),
}


class AuditValidator:
    """审计验证器"""

    def __init__(self, known_issues: dict[str, AuditIssue] | None = None):
        self.known_issues = known_issues or KNOWN_ISSUES

    def check_known_issues(self, content: str) -> list[AuditIssue]:
        """检查已知问题模式"""
        import re
        issues = []

        for pattern_name, issue in self.known_issues.items():
            if re.search(issue.pattern, content, re.IGNORECASE):
                issues.append(issue)

        return issues

    def check_config_consistency(self, config: dict) -> list[AuditIssue]:
        """检查配置一致性"""
        issues = []

        # 检查WACC范围
        wacc = config.get("wacc", 0)
        if wacc < 0.04 or wacc > 0.20:
            issues.append(AuditIssue(
                pattern="wacc_range",
                severity="ERROR",
                message=f"WACC值{wacc:.2%}超出合理区间[4%, 20%]",
                suggestion="检查WACC计算参数",
            ))

        # 检查g < WACC
        g = config.get("g", 0)
        if g >= wacc and wacc > 0:
            issues.append(AuditIssue(
                pattern="g_exceeds_wacc",
                severity="FATAL",
                message=f"永续增长率{g:.2%} >= WACC{wacc:.2%}",
                suggestion="修正永续增长率",
            ))

        return issues

    def check_module_calls(self, module_calls: list[str]) -> list[AuditIssue]:
        """检查模块调用序列"""
        issues = []

        # 检查是否有遗漏的必需模块
        required_modules = ["WACC计算", "DCF估值", "敏感性分析"]
        for module in required_modules:
            if not any(module in call for call in module_calls):
                issues.append(AuditIssue(
                    pattern="missing_module",
                    severity="WARN",
                    message=f"未调用{module}模块",
                    suggestion=f"添加{module}模块调用",
                ))

        return issues

    def check_self_audit(self, audit_results: list[dict]) -> list[AuditIssue]:
        """检查自身审计结果"""
        issues = []

        # 检查评分标准差
        scores = [r.get("score", 0) for r in audit_results if "score" in r]
        if len(scores) >= 3:
            import statistics
            stddev = statistics.stdev(scores)
            if stddev < 2.0:
                issues.append(AuditIssue(
                    pattern="score_stddev",
                    severity="WARN",
                    message=f"评分标准差{stddev:.2f}过小，可能过于乐观",
                    suggestion="增加评分差异性",
                ))

        return issues

    def check_cross_validation(
        self,
        dcf_value: float,
        market_price: float,
        tolerance: float = 0.5,
    ) -> list[AuditIssue]:
        """交叉验证"""
        issues = []

        if market_price > 0:
            diff_ratio = abs(dcf_value - market_price) / market_price
            if diff_ratio > tolerance:
                issues.append(AuditIssue(
                    pattern="dcf_market_diff",
                    severity="WARN",
                    message=f"DCF估值{dcf_value:.2f}与市场价格{market_price:.2f}差异过大({diff_ratio:.1%})",
                    suggestion="检查DCF假设或市场情绪",
                ))

        return issues

    def validate(self, content: str, config: dict | None = None) -> list[AuditIssue]:
        """完整审计验证"""
        issues = []

        # 已知问题检查
        issues.extend(self.check_known_issues(content))

        # 配置一致性检查
        if config:
            issues.extend(self.check_config_consistency(config))

        return issues

    def generate_audit_report(self, issues: list[AuditIssue]) -> str:
        """生成审计报告"""
        if not issues:
            return "## 审计报告\n\n✅ 未发现问题"

        lines = [
            "## 审计报告",
            "",
            f"共发现 {len(issues)} 个问题",
            "",
            "| 严重度 | 问题 | 建议 |",
            "|--------|------|------|",
        ]

        for issue in issues:
            lines.append(f"| {issue.severity} | {issue.message} | {issue.suggestion} |")

        return "\n".join(lines)
