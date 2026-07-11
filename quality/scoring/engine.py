"""
quality/scoring/engine.py — 评分引擎

实现ScoringEngine接口，负责：
- 聚合多个维度的评分
- 计算证伪得分
- 应用强制降级规则
- 生成评分报告
"""

from __future__ import annotations

import logging
from typing import Optional

from ..exceptions import CalculationError
from ..interfaces import ScoreDimensionCalculator, ScoringEngine
from ..types import (
    DimensionScore,
    QualityContext,
    ReasoningResult,
    ScoreReport,
)
from ..validators import ReportValidator, ValidationResult

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────
# 评分等级映射
# ─────────────────────────────────────────────────

GRADE_THRESHOLDS = {
    "S": 90,
    "A": 80,
    "B": 70,
    "C": 60,
    "D": 50,
    "F": 0,
}


def score_to_grade(score: float) -> str:
    """分数转等级"""
    for grade, threshold in GRADE_THRESHOLDS.items():
        if score >= threshold:
            return grade
    return "F"


# ─────────────────────────────────────────────────
# 证伪得分计算
# ─────────────────────────────────────────────────

def calculate_falsification_score(reasoning_result: ReasoningResult) -> float:
    """计算证伪得分（0-100）
    
    公式：
    - 反方论点强度（40%）- 使用strength加权计算
    - 证伪指标可操作性（40%）
    - 监控计划完整性（20%）
    """
    counter_result = reasoning_result.counter_result
    score = 0.0
    
    # 1. 反方论点强度（40%）- 使用strength加权计算
    counter_strengths = counter_result.counter_strengths
    if counter_strengths:
        # 使用strength加权平均，而非简单计数
        avg_strength = sum(counter_strengths) / len(counter_strengths)
        counter_strength = avg_strength * 40
    else:
        # 如果没有strength信息，回退到计数方式
        counter_count = len(counter_result.counter_arguments)
        counter_strength = min(counter_count * 10, 40)
    score += counter_strength
    
    # 2. 证伪指标可操作性（40%）
    indicators = counter_result.falsification_indicators
    if indicators:
        indicator_quality = sum(
            1 for ind in indicators
            if ind.measurement_method and ind.threshold
        ) / len(indicators)
        score += indicator_quality * 40
    else:
        score += 0
    
    # 3. 监控计划完整性（20%）
    monitoring = counter_result.monitoring_plan
    if monitoring and monitoring.triggers:
        score += 20
    
    return min(score, 100)


# ─────────────────────────────────────────────────
# 强制降级规则
# ─────────────────────────────────────────────────

def apply_falsification_rule(report: ScoreReport) -> ScoreReport:
    """应用证伪指标强制降级规则
    
    规则：
    - 证伪<5分 → 强制D级
    - 证伪<10分 → 降级到C级
    """
    falsification_score = report.falsification_score
    
    # 规则：证伪<5分 → 强制D级
    if falsification_score < 5:
        if report.grade != "F":
            report.grade = "D"
            report.warnings.append(f"证伪指标不足({falsification_score:.1f}分)，强制降级到D级")
            logger.warning(f"证伪降级: {falsification_score:.1f}分 → D级")
    
    # 规则：证伪<10分 → 降级到C级
    elif falsification_score < 10:
        if report.grade in ["S", "A", "B"]:
            report.grade = "C"
            report.warnings.append(f"证伪指标不足({falsification_score:.1f}分)，降级到C级")
            logger.warning(f"证伪降级: {falsification_score:.1f}分 → C级")
    
    return report


# ─────────────────────────────────────────────────
# 评分引擎实现
# ─────────────────────────────────────────────────

class StandardScoringEngine(ScoringEngine):
    """标准评分引擎"""
    
    def __init__(self, validator: Optional[ReportValidator] = None):
        self._dimensions: dict[str, ScoreDimensionCalculator] = {}
        self._validator = validator or ReportValidator()
    
    def register_dimension(self, calculator: ScoreDimensionCalculator) -> None:
        """注册评分维度"""
        dim_id = calculator.get_dimension_id()
        self._dimensions[dim_id] = calculator
        logger.info(f"注册评分维度: {dim_id}")
    
    def score(self, reasoning_result: ReasoningResult, context: QualityContext) -> ScoreReport:
        """执行评分
        
        Args:
            reasoning_result: 推理链输出
            context: 质量上下文
            
        Returns:
            ScoreReport: 评分报告
        """
        logger.info("开始评分")
        
        dimension_scores = {}
        total_weighted_score = 0.0
        total_weight = 0.0
        
        # 1. 计算各维度得分
        for dim_id, calculator in self._dimensions.items():
            try:
                dim_score = calculator.calculate(reasoning_result, context)
                dimension_scores[dim_id] = dim_score
                
                # 加权累加
                weight = calculator.get_weight()
                total_weighted_score += dim_score.score * weight
                total_weight += weight
                
                logger.debug(f"维度 {dim_id}: {dim_score.score:.1f}/{dim_score.max_score}")
            
            except Exception as e:
                logger.error(f"维度 {dim_id} 计算失败: {e}")
                raise CalculationError(f"维度 {dim_id} 计算失败: {e}") from e
        
        # 2. 计算总分
        if total_weight > 0:
            total_score = total_weighted_score / total_weight
        else:
            total_score = 0.0
        
        # 3. 计算证伪得分
        falsification_score = calculate_falsification_score(reasoning_result)
        
        # 4. 确定等级
        grade = score_to_grade(total_score)
        
        # 5. 计算置信度
        confidence = min(
            context.confidence_cap,
            reasoning_result.confidence
        )
        
        # 6. 生成警告
        warnings = []
        if context.is_blocked:
            warnings.append("质量上下文阻断")
        if reasoning_result.checkpoints_failed:
            warnings.append(f"检查点失败: {', '.join(reasoning_result.checkpoints_failed)}")
        
        # 6.5 数据校验（使用ReportValidator）
        validation_result = self._validate_data(context)
        if validation_result:
            if not validation_result.is_valid:
                warnings.append(f"数据校验失败: {validation_result.failed_count}项")
            for check in validation_result.checks:
                if not check.passed:
                    warnings.append(f"校验失败: {check.name} - {check.message}")
            for warning in validation_result.warnings:
                warnings.append(f"校验警告: {warning}")
        
        # 7. 构建报告
        report = ScoreReport(
            total_score=total_score,
            grade=grade,
            dimension_scores=dimension_scores,
            falsification_score=falsification_score,
            confidence=confidence,
            warnings=warnings
        )
        
        # 8. 应用证伪强制降级规则
        report = apply_falsification_rule(report)
        
        logger.info(f"评分完成: 总分={total_score:.1f}, 等级={report.grade}, 证伪={falsification_score:.1f}")
        
        return report
    
    def _validate_data(self, context: QualityContext) -> Optional[ValidationResult]:
        """使用ReportValidator校验数据
        
        Args:
            context: 质量上下文
            
        Returns:
            ValidationResult: 校验结果，如果没有数据则返回None
        """
        # 从context.extra_info中获取数据
        extra = context.extra_info
        
        # 检查是否有足够的数据进行校验
        if not extra:
            return None
        
        # 构建校验数据
        report_data = {}
        
        # 市值
        if "market_cap" in extra:
            report_data["market_cap"] = extra["market_cap"]
        
        # 股价和总股本
        if "share_price" in extra and "total_shares" in extra:
            report_data["share_price"] = extra["share_price"]
            report_data["total_shares"] = extra["total_shares"]
        
        # PE
        if "pe" in extra and "net_income" in extra:
            report_data["pe"] = extra["pe"]
            report_data["net_income"] = extra["net_income"]
            report_data["net_income_type"] = extra.get("net_income_type", "GAAP")
        
        # PB
        if "pb" in extra and "equity" in extra:
            report_data["pb"] = extra["pb"]
            report_data["equity"] = extra["equity"]
            report_data["equity_type"] = extra.get("equity_type", "parent")
        
        # 增长率
        if "growth_value" in extra and "growth_current" in extra and "growth_previous" in extra:
            report_data["growth_value"] = extra["growth_value"]
            report_data["growth_current"] = extra["growth_current"]
            report_data["growth_previous"] = extra["growth_previous"]
        
        # 如果没有足够数据，返回None
        if len(report_data) < 2:
            return None
        
        # 执行校验
        try:
            result = self._validator.validate_report(report_data)
            return result
        except Exception as e:
            logger.warning(f"数据校验异常: {e}")
            return None
