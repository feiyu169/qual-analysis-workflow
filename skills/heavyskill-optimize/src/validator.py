"""HeavySkill 优化方案 V3 - 结论校验引擎（包含 P0-5 修复）"""

import logging
from typing import List, Optional, Dict
from dataclasses import dataclass, field
from datetime import datetime

from .models import Severity, Verdict, Issue, RuleResult, ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class PVetoConfig:
    """P0 一票否决配置"""
    enabled: bool = True
    min_count: int = 1  # 最少 P0 问题数才触发否决
    min_confidence: float = 0.8  # P0 问题最低置信度


@dataclass
class ThresholdRuleConfig:
    """阈值规则配置"""
    enabled: bool = True
    thresholds: dict = field(default_factory=lambda: {
        Severity.P0: 1,   # P0 >= 1 触发
        Severity.P1: 3,   # P1 >= 3 触发
        Severity.P2: 10,  # P2 >= 10 触发
    })


@dataclass
class WeightedScoreConfig:
    """加权评分配置"""
    enabled: bool = True
    weights: dict = field(default_factory=lambda: {
        Severity.P0: 10,
        Severity.P1: 5,
        Severity.P2: 2,
        Severity.P3: 1,
    })
    reject_threshold: float = 15.0
    warn_threshold: float = 8.0


@dataclass
class DomainCoverageConfig:
    """领域覆盖率配置"""
    enabled: bool = True
    required_domains: List[str] = field(default_factory=lambda: ["安全", "架构", "性能"])
    min_coverage: float = 0.6  # 最低覆盖率


@dataclass
class ConclusionValidatorConfig:
    """结论校验器配置"""
    # 总开关
    enabled: bool = True
    # 影子模式（只记录不覆盖）
    shadow_mode: bool = False
    # 异常回退
    fallback_to_llm: bool = True
    # 人工确认队列
    human_review_queue: bool = True
    # 置信度阈值
    confidence_threshold: float = 0.8
    # 规则配置
    p0_veto: PVetoConfig = field(default_factory=PVetoConfig)
    threshold_rule: ThresholdRuleConfig = field(default_factory=ThresholdRuleConfig)
    weighted_score: WeightedScoreConfig = field(default_factory=WeightedScoreConfig)
    domain_coverage: DomainCoverageConfig = field(default_factory=DomainCoverageConfig)


class ConclusionValidator:
    """结论校验器 - 确定性规则引擎"""
    
    def __init__(self, config: Optional[ConclusionValidatorConfig] = None):
        self.config = config or ConclusionValidatorConfig()
        self._shadow_log = []
    
    def validate(self, issues: List[Issue], llm_verdict: Optional[Verdict] = None) -> ValidationResult:
        """验证结论"""
        # 总开关检查
        if not self.config.enabled:
            return ValidationResult(
                verdict=llm_verdict or Verdict.PASS,
                rules_applied=[],
                issues=issues,
                confidence=1.0
            )
        
        # 影子模式（P0-5 修复：添加异常保护）
        if self.config.shadow_mode:
            return self._validate_shadow(issues, llm_verdict)
        
        # 正常模式
        try:
            return self._validate_internal(issues, llm_verdict)
        except Exception as e:
            logger.error(f"规则引擎异常: {e}")
            if self.config.fallback_to_llm:
                return ValidationResult(
                    verdict=llm_verdict or Verdict.PASS,
                    rules_applied=[],
                    issues=issues,
                    confidence=0.5,
                    fallback=True
                )
            raise
    
    def _validate_internal(self, issues: List[Issue], llm_verdict: Optional[Verdict]) -> ValidationResult:
        """内部验证逻辑"""
        rules_results = []
        
        # 预处理：置信度过滤（创建副本避免修改原始对象）
        filtered_issues = self._filter_by_confidence(issues)
        
        # 规则 1: P0 一票否决
        r1 = self._eval_p0_veto(filtered_issues)
        rules_results.append(r1)
        if r1.triggered and r1.verdict == Verdict.REJECT:
            return self._build_result(Verdict.REJECT, rules_results, filtered_issues)
        
        # 规则 2: 阈值规则
        r2 = self._eval_threshold_rule(filtered_issues)
        rules_results.append(r2)
        if r2.triggered and r2.verdict == Verdict.REJECT:
            return self._build_result(Verdict.REJECT, rules_results, filtered_issues)
        
        # 规则 3: 加权评分
        r3 = self._eval_weighted_score(filtered_issues)
        rules_results.append(r3)
        if r3.triggered and r3.verdict == Verdict.REJECT:
            return self._build_result(Verdict.REJECT, rules_results, filtered_issues)
        
        # 规则 4: 领域覆盖率
        r4 = self._eval_domain_coverage(filtered_issues)
        rules_results.append(r4)
        if r4.triggered and r4.verdict == Verdict.REJECT:
            return self._build_result(Verdict.REJECT, rules_results, filtered_issues)
        
        # 所有规则都未触发 REJECT
        # 检查是否有警告
        if any(r.triggered and r.verdict == Verdict.CONDITIONAL_PASS for r in rules_results):
            return self._build_result(Verdict.CONDITIONAL_PASS, rules_results, filtered_issues)
        
        return self._build_result(Verdict.PASS, rules_results, filtered_issues)
    
    def _filter_by_confidence(self, issues: List[Issue]) -> List[Issue]:
        """根据置信度过滤问题（创建副本避免修改原始对象）"""
        filtered = []
        for issue in issues:
            # 创建副本
            new_issue = Issue(
                id=issue.id,
                title=issue.title,
                severity=issue.severity,
                domain=issue.domain,
                description=issue.description,
                suggestion=issue.suggestion,
                confidence=issue.confidence,
                source=issue.source,
                location=issue.location,
                evidence=issue.evidence
            )
            
            if new_issue.confidence < self.config.confidence_threshold:
                # 低置信度问题降级
                if new_issue.severity == Severity.P0:
                    new_issue.severity = Severity.P1
                    new_issue.description += f" (降级：置信度 {new_issue.confidence} < {self.config.confidence_threshold})"
            filtered.append(new_issue)
        return filtered
    
    def _eval_p0_veto(self, issues: List[Issue]) -> RuleResult:
        """P0 一票否决规则"""
        if not self.config.p0_veto.enabled:
            return RuleResult("p0_veto", False, Verdict.PASS, "规则已禁用")
        
        # 只统计置信度满足要求的 P0 问题
        p0_issues = [
            i for i in issues 
            if i.severity == Severity.P0 and i.confidence >= self.config.p0_veto.min_confidence
        ]
        
        if len(p0_issues) >= self.config.p0_veto.min_count:
            return RuleResult(
                rule_name="p0_veto",
                triggered=True,
                verdict=Verdict.REJECT,
                reason=f"发现 {len(p0_issues)} 个 P0 问题",
                details={"p0_count": len(p0_issues), "p0_titles": [i.title for i in p0_issues]}
            )
        
        return RuleResult("p0_veto", False, Verdict.PASS, "无 P0 问题")
    
    def _eval_threshold_rule(self, issues: List[Issue]) -> RuleResult:
        """阈值规则"""
        if not self.config.threshold_rule.enabled:
            return RuleResult("threshold_rule", False, Verdict.PASS, "规则已禁用")
        
        for severity, threshold in self.config.threshold_rule.thresholds.items():
            count = len([i for i in issues if i.severity == severity])
            if count >= threshold:
                return RuleResult(
                    rule_name="threshold_rule",
                    triggered=True,
                    verdict=Verdict.REJECT,
                    reason=f"{severity.value} 问题数 {count} >= 阈值 {threshold}",
                    details={"severity": severity.value, "count": count, "threshold": threshold}
                )
        
        return RuleResult("threshold_rule", False, Verdict.PASS, "各级别问题数均未达阈值")
    
    def _eval_weighted_score(self, issues: List[Issue]) -> RuleResult:
        """加权评分规则"""
        if not self.config.weighted_score.enabled:
            return RuleResult("weighted_score", False, Verdict.PASS, "规则已禁用")
        
        total_score = 0
        for issue in issues:
            weight = self.config.weighted_score.weights.get(issue.severity, 1)
            total_score += weight
        
        if total_score >= self.config.weighted_score.reject_threshold:
            return RuleResult(
                rule_name="weighted_score",
                triggered=True,
                verdict=Verdict.REJECT,
                reason=f"加权评分 {total_score} >= 拒绝阈值 {self.config.weighted_score.reject_threshold}",
                details={"score": total_score, "threshold": self.config.weighted_score.reject_threshold}
            )
        
        if total_score >= self.config.weighted_score.warn_threshold:
            return RuleResult(
                rule_name="weighted_score",
                triggered=True,
                verdict=Verdict.CONDITIONAL_PASS,
                reason=f"加权评分 {total_score} >= 警告阈值 {self.config.weighted_score.warn_threshold}",
                details={"score": total_score, "threshold": self.config.weighted_score.warn_threshold}
            )
        
        return RuleResult("weighted_score", False, Verdict.PASS, f"加权评分 {total_score} 正常")
    
    def _eval_domain_coverage(self, issues: List[Issue]) -> RuleResult:
        """领域覆盖率规则"""
        if not self.config.domain_coverage.enabled:
            return RuleResult("domain_coverage", False, Verdict.PASS, "规则已禁用")
        
        required = set(self.config.domain_coverage.required_domains)
        if not required:
            return RuleResult("domain_coverage", False, Verdict.PASS, "无必需要求领域")
        
        # 空 issues 短路保护
        if not issues:
            return RuleResult("domain_coverage", False, Verdict.PASS, "无问题，跳过领域覆盖率检查")
        
        covered_domains = set(i.domain for i in issues)
        coverage = len(covered_domains & required) / len(required)
        
        if coverage < self.config.domain_coverage.min_coverage:
            return RuleResult(
                rule_name="domain_coverage",
                triggered=True,
                verdict=Verdict.REJECT,
                reason=f"领域覆盖率 {coverage:.0%} < 最低要求 {self.config.domain_coverage.min_coverage:.0%}",
                details={"coverage": coverage, "covered": list(covered_domains), "required": list(required)}
            )
        
        return RuleResult("domain_coverage", False, Verdict.PASS, f"领域覆盖率 {coverage:.0%} 正常")
    
    def _validate_shadow(self, issues: List[Issue], llm_verdict: Optional[Verdict]) -> ValidationResult:
        """影子模式验证（P0-5 修复：添加异常保护）"""
        try:
            # 记录但不覆盖
            result = self._validate_internal(issues, llm_verdict)
            
            shadow_record = {
                "timestamp": datetime.now().isoformat(),
                "llm_verdict": llm_verdict.value if llm_verdict else None,
                "rule_verdict": result.verdict.value,
                "rules_applied": [r.rule_name for r in result.rules_applied],
                "issue_count": len(issues),
                "status": "success"
            }
            self._shadow_log.append(shadow_record)
            
            # 返回 LLM 结论（不覆盖）
            return ValidationResult(
                verdict=llm_verdict or Verdict.PASS,
                rules_applied=result.rules_applied,
                issues=issues,
                confidence=1.0,
                shadow_mode=True,
                shadow_log=shadow_record
            )
        
        except Exception as e:
            # P0-5 修复：异常处理
            logger.error(f"影子模式异常: {e}")
            
            shadow_record = {
                "timestamp": datetime.now().isoformat(),
                "llm_verdict": llm_verdict.value if llm_verdict else None,
                "rule_verdict": None,
                "rules_applied": [],
                "issue_count": len(issues),
                "status": "error",
                "error": str(e)
            }
            self._shadow_log.append(shadow_record)
            
            # 返回 LLM 结论（确保不抛异常）
            return ValidationResult(
                verdict=llm_verdict or Verdict.PASS,
                rules_applied=[],
                issues=issues,
                confidence=0.5,  # 降低置信度
                shadow_mode=True,
                shadow_log=shadow_record
            )
    
    def _build_result(self, verdict: Verdict, rules: List[RuleResult], issues: List[Issue]) -> ValidationResult:
        """构建验证结果"""
        # 检查是否需要人工审核
        human_review = (self.config.human_review_queue and 
                       verdict == Verdict.REJECT and
                       any(r.rule_name == "p0_veto" and r.triggered for r in rules))
        
        return ValidationResult(
            verdict=verdict,
            rules_applied=rules,
            issues=issues,
            confidence=1.0,
            human_review_required=human_review
        )
    
    def get_shadow_log(self) -> List[Dict]:
        """获取影子模式日志"""
        return self._shadow_log.copy()
