"""
事实表（结构化事实表+溯源+人工抽检）

功能：
1. 结构化事实存储
2. 溯源追踪
3. 人工抽检
"""

import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Fact:
    """事实"""
    key: str
    value: float
    unit: str
    source: str
    year: int
    trend: str  # up, down, stable
    source_text: str = ""
    verified: bool = False
    verified_by: str = ""
    verified_at: str = ""


class FactTable:
    """事实表"""

    def __init__(self):
        self.facts: dict[str, Fact] = {}
        self.audit_log: list[dict] = []

    def add_fact(self, key: str, value: float, unit: str,
                 source: str, year: int, trend: str, source_text: str = ""):
        """添加事实"""
        self.facts[key] = Fact(
            key=key,
            value=value,
            unit=unit,
            source=source,
            year=year,
            trend=trend,
            source_text=source_text,
        )

        self.audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": "add",
            "key": key,
            "value": value,
        })

    def get_fact(self, key: str) -> Fact | None:
        """获取事实"""
        return self.facts.get(key)

    def get_trend(self, key: str) -> str:
        """获取趋势"""
        fact = self.get_fact(key)
        if fact:
            return fact.trend
        return "unknown"

    def verify_fact(self, key: str, verified_by: str):
        """验证事实"""
        fact = self.get_fact(key)
        if fact:
            fact.verified = True
            fact.verified_by = verified_by
            fact.verified_at = datetime.now().isoformat()

            self.audit_log.append({
                "timestamp": datetime.now().isoformat(),
                "action": "verify",
                "key": key,
                "verified_by": verified_by,
            })

    def get_unverified_facts(self) -> list[Fact]:
        """获取未验证的事实"""
        return [f for f in self.facts.values() if not f.verified]

    def validate_consistency(self) -> list[str]:
        """验证一致性"""
        errors = []

        for key, fact in self.facts.items():
            if fact.trend == "up" and fact.value < 0:
                errors.append(f"{key}趋势为up但值为负")
            elif fact.trend == "down" and fact.value > 0:
                errors.append(f"{key}趋势为down但值为正")

        return errors

    def generate_audit_report(self) -> str:
        """生成审计报告"""
        report = "# 事实表审计报告\n\n"

        report += f"总事实数: {len(self.facts)}\n"
        report += f"已验证: {len([f for f in self.facts.values() if f.verified])}\n"
        report += f"未验证: {len(self.get_unverified_facts())}\n\n"

        if self.get_unverified_facts():
            report += "## 未验证事实\n\n"
            for fact in self.get_unverified_facts():
                report += f"- {fact.key}: {fact.value} {fact.unit} (来源: {fact.source})\n"

        return report

    def get_facts_by_year(self, year: int) -> list[Fact]:
        """按年份获取事实"""
        return [f for f in self.facts.values() if f.year == year]

    def get_facts_by_source(self, source: str) -> list[Fact]:
        """按来源获取事实"""
        return [f for f in self.facts.values() if f.source == source]
