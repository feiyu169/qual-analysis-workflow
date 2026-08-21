"""
洞察审计器（禁用自动满分+动态扣分）

功能：
1. 禁用自动满分
2. 动态扣分规则
3. 定期校准
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class DeductionRule:
    """扣分规则"""
    pattern: str
    deduction: int
    description: str
    category: str
    last_calibrated: str = ""


@dataclass
class InsightIssue:
    """洞察问题"""
    issue_id: str
    description: str
    severity: str  # fatal, important, suggestion
    location: str
    fix_status: str = "pending"


@dataclass
class InsightAuditResult:
    """洞察审计结果"""
    chapter_num: int
    chapter_title: str
    issues: list[InsightIssue] = field(default_factory=list)
    score: int = 100
    deduction_details: list[dict] = field(default_factory=list)

    @property
    def fatal_count(self):
        return len([i for i in self.issues if i.severity == "fatal"])

    @property
    def important_count(self):
        return len([i for i in self.issues if i.severity == "important"])


class InsightAuditor:
    """洞察审计器"""

    # 动态扣分规则
    DEDUCTION_RULES: list[DeductionRule] = [
        DeductionRule(
            pattern="placeholder",
            deduction=30,
            description="包含占位符",
            category="完整性",
        ),
        DeductionRule(
            pattern="xx",
            deduction=25,
            description="包含XX占位",
            category="完整性",
        ),
        DeductionRule(
            pattern="数据不足",
            deduction=20,
            description="数据不足声明",
            category="数据质量",
        ),
        DeductionRule(
            pattern="具体数据待核实",
            deduction=20,
            description="数据待核实",
            category="数据质量",
        ),
        DeductionRule(
            pattern="需要配置",
            deduction=25,
            description="需要配置提示",
            category="完整性",
        ),
    ]

    # 致命问题扣分
    FATAL_DEDUCTION = 30
    IMPORTANT_DEDUCTION = 15
    SUGGESTION_DEDUCTION = 5

    def __init__(self):
        self.calibration_history: list[dict] = []

    def audit(self, chapters: dict, review_result=None) -> list[InsightAuditResult]:
        """审计每章的洞察深度"""
        audits = []

        for ch_num, content in chapters.items():
            audit = InsightAuditResult(
                chapter_num=ch_num,
                chapter_title=self._extract_title(content),
                score=100,
            )

            # 应用动态扣分规则
            for rule in self.DEDUCTION_RULES:
                if rule.pattern in content.lower():
                    audit.score -= rule.deduction
                    audit.deduction_details.append({
                        "rule": rule.pattern,
                        "deduction": rule.deduction,
                        "description": rule.description,
                        "category": rule.category,
                    })

            # 从审查结果中提取该章问题
            if review_result:
                for issue in review_result.fatal_issues:
                    if f"第{ch_num}章" in issue.location:
                        audit.issues.append(InsightIssue(
                            issue_id=issue.issue_id,
                            description=issue.description,
                            severity="fatal",
                            location=issue.location,
                        ))
                        audit.score -= self.FATAL_DEDUCTION

                for issue in review_result.important_issues:
                    if f"第{ch_num}章" in issue.location:
                        audit.issues.append(InsightIssue(
                            issue_id=issue.issue_id,
                            description=issue.description,
                            severity="important",
                            location=issue.location,
                        ))
                        audit.score -= self.IMPORTANT_DEDUCTION

            # 确保分数不低于0
            audit.score = max(0, audit.score)

            audits.append(audit)

        return audits

    def calibrate_rules(self, historical_data: list[dict]):
        """校准扣分规则"""
        calibration_record = {
            "timestamp": datetime.now().isoformat(),
            "rules_before": len(self.DEDUCTION_RULES),
            "adjustments": [],
        }

        self.calibration_history.append(calibration_record)

        return calibration_record

    def _extract_title(self, content: str) -> str:
        """提取章节标题"""
        import re
        match = re.search(r'###?\s*第\d+章[：:]\s*(.+)', content)
        if match:
            return match.group(1).strip()
        return ""

    def get_audit_summary(self, audits: list[InsightAuditResult]) -> str:
        """获取审计摘要"""
        summary = "# 洞察审计摘要\n\n"

        total_score = 0
        total_fatal = 0
        total_important = 0

        for audit in audits:
            total_score += audit.score
            total_fatal += audit.fatal_count
            total_important += audit.important_count

            summary += f"## 第{audit.chapter_num}章: {audit.chapter_title}\n"
            summary += f"- 分数: {audit.score}/100\n"
            summary += f"- 致命问题: {audit.fatal_count}\n"
            summary += f"- 重要问题: {audit.important_count}\n"

            if audit.deduction_details:
                summary += "- 扣分明细:\n"
                for detail in audit.deduction_details:
                    summary += f"  - {detail['description']}: -{detail['deduction']}分\n"

            summary += "\n"

        avg_score = total_score / len(audits) if audits else 0

        summary += "## 总体统计\n"
        summary += f"- 平均分数: {avg_score:.1f}/100\n"
        summary += f"- 总致命问题: {total_fatal}\n"
        summary += f"- 总重要问题: {total_important}\n"

        return summary
