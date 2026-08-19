"""
quality/scoring/dimensions.py — 5维度评分器

评分维度：
1. 数据完整性（20%）
2. 逻辑一致性（25%）
3. 分析深度（25%）
4. 结论可靠性（20%）
5. 可操作性（10%）
"""

from __future__ import annotations

import logging
from typing import Optional

from ..interfaces import ScoreDimensionCalculator
from ..types import (
    DimensionScore,
    QualityContext,
    ReasoningResult,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────
# 维度1: 数据完整性（20%）
# ─────────────────────────────────────────────────

class DataCompletenessCalculator(ScoreDimensionCalculator):
    """数据完整性评分器
    
    子维度：
    - 数据源覆盖度（40%）
    - 时效性（30%）
    - 交叉验证（30%）
    """
    
    def get_dimension_id(self) -> str:
        return "D1_data_completeness"
    
    def get_max_score(self) -> float:
        return 100.0
    
    def get_weight(self) -> float:
        return 0.20
    
    def calculate(self, reasoning_result: ReasoningResult, context: QualityContext) -> DimensionScore:
        score = 0.0
        evidence = []
        
        # 子维度1: 数据源覆盖度（40%）
        sources = context.data.sources
        source_count = len(sources)
        source_score = min(source_count / 3, 1.0) * 40
        score += source_score
        evidence.append(f"数据源: {source_count}个")
        
        # 子维度2: 时效性（30%）
        # 基于数据质量等级
        if context.data.level.value == "L0":
            timeliness_score = 30
        elif context.data.level.value == "L1":
            timeliness_score = 20
        elif context.data.level.value == "L2":
            timeliness_score = 10
        else:
            timeliness_score = 0
        score += timeliness_score
        evidence.append(f"数据质量: {context.data.level.value}")
        
        # 子维度3: 交叉验证（30%）
        # 基于因果图的敏感性结果
        if reasoning_result.causal_graph.sensitivity_robust_ratio:
            robust = reasoning_result.causal_graph.sensitivity_robust_ratio
            cross_score = robust * 30
        else:
            cross_score = 15  # 默认中等
        score += cross_score
        evidence.append(f"交叉验证: {cross_score:.1f}/30")
        
        return DimensionScore(
            dimension_id=self.get_dimension_id(),
            score=min(score, 100),
            max_score=100,
            evidence=evidence,
            explanation=f"数据完整性评分: {score:.1f}/100",
            confidence=1.0 - len(context.data.missing) * 0.1
        )


# ─────────────────────────────────────────────────
# 维度2: 逻辑一致性（25%）
# ─────────────────────────────────────────────────

class LogicConsistencyCalculator(ScoreDimensionCalculator):
    """逻辑一致性评分器
    
    子维度：
    - 因果链条（40%）
    - 数据-结论距离（30%）
    - 估值一致性（30%）
    """
    
    def get_dimension_id(self) -> str:
        return "D2_logic_consistency"
    
    def get_max_score(self) -> float:
        return 100.0
    
    def get_weight(self) -> float:
        return 0.25
    
    def calculate(self, reasoning_result: ReasoningResult, context: QualityContext) -> DimensionScore:
        score = 0.0
        evidence = []
        
        # 子维度1: 因果链条（40%）
        relations = reasoning_result.causal_graph.relations
        relation_count = len(relations)
        causal_score = min(relation_count / 3, 1.0) * 40
        score += causal_score
        evidence.append(f"因果关系: {relation_count}条")
        
        # 子维度2: 数据-结论距离（30%）
        # 基于因果图置信度
        confidence = reasoning_result.causal_graph.confidence
        distance_score = confidence * 30
        score += distance_score
        evidence.append(f"因果置信度: {confidence:.2f}")
        
        # 子维度3: 估值一致性（30%）
        # 基于检查点通过率
        passed = len(reasoning_result.checkpoints_passed)
        failed = len(reasoning_result.checkpoints_failed)
        total = passed + failed
        if total > 0:
            consistency = passed / total
        else:
            consistency = 0.5
        consistency_score = consistency * 30
        score += consistency_score
        evidence.append(f"检查点通过率: {passed}/{total}")
        
        return DimensionScore(
            dimension_id=self.get_dimension_id(),
            score=min(score, 100),
            max_score=100,
            evidence=evidence,
            explanation=f"逻辑一致性评分: {score:.1f}/100",
            confidence=confidence
        )


# ─────────────────────────────────────────────────
# 维度3: 分析深度（25%）
# ─────────────────────────────────────────────────

class AnalysisDepthCalculator(ScoreDimensionCalculator):
    """分析深度评分器
    
    子维度：
    - 维度覆盖（30%）
    - 横纵对比（30%）
    - 正反论证（40%）
    """
    
    def get_dimension_id(self) -> str:
        return "D3_analysis_depth"
    
    def get_max_score(self) -> float:
        return 100.0
    
    def get_weight(self) -> float:
        return 0.25
    
    def calculate(self, reasoning_result: ReasoningResult, context: QualityContext) -> DimensionScore:
        score = 0.0
        evidence = []
        
        # 子维度1: 维度覆盖（30%）
        # 基于情景结果数量
        scenario_count = len(reasoning_result.scenario_results)
        coverage_score = min(scenario_count / 2, 1.0) * 30
        score += coverage_score
        evidence.append(f"情景覆盖: {scenario_count}个")
        
        # 子维度2: 横纵对比（30%）
        # 基于因果关系的多样性
        relations = reasoning_result.causal_graph.relations
        unique_causes = set(r.cause for r in relations)
        unique_effects = set(r.effect for r in relations)
        diversity = (len(unique_causes) + len(unique_effects)) / max(len(relations) * 2, 1)
        comparison_score = diversity * 30
        score += comparison_score
        evidence.append(f"因果多样性: {diversity:.2f}")
        
        # 子维度3: 正反论证（40%）
        # 基于反方论点数量和证伪指标
        counter_count = len(reasoning_result.counter_result.counter_arguments)
        indicator_count = len(reasoning_result.counter_result.falsification_indicators)
        argument_score = min(counter_count / 3, 1.0) * 20
        indicator_score = min(indicator_count / 3, 1.0) * 20
        score += argument_score + indicator_score
        evidence.append(f"反方论点: {counter_count}条, 证伪指标: {indicator_count}个")
        
        return DimensionScore(
            dimension_id=self.get_dimension_id(),
            score=min(score, 100),
            max_score=100,
            evidence=evidence,
            explanation=f"分析深度评分: {score:.1f}/100",
            confidence=reasoning_result.confidence
        )


# ─────────────────────────────────────────────────
# 维度4: 结论可靠性（20%）
# ─────────────────────────────────────────────────

class ConclusionReliabilityCalculator(ScoreDimensionCalculator):
    """结论可靠性评分器
    
    子维度：
    - 投资建议（40%）
    - 催化剂（30%）
    - 风险矩阵（30%）
    """
    
    def get_dimension_id(self) -> str:
        return "D4_conclusion_reliability"
    
    def get_max_score(self) -> float:
        return 100.0
    
    def get_weight(self) -> float:
        return 0.20
    
    def calculate(self, reasoning_result: ReasoningResult, context: QualityContext) -> DimensionScore:
        score = 0.0
        evidence = []
        
        # 子维度1: 投资建议（40%）
        # 基于置信度
        confidence = reasoning_result.confidence
        advice_score = confidence * 40
        score += advice_score
        evidence.append(f"置信度: {confidence:.2f}")
        
        # 子维度2: 催化剂（30%）
        # 基于情景结果的效应
        if reasoning_result.scenario_results:
            effects = [sr.effect for sr in reasoning_result.scenario_results]
            high_effects = sum(1 for e in effects if e.level.value == "高")
            catalyst_score = min(high_effects / len(effects), 1.0) * 30
        else:
            catalyst_score = 15
        score += catalyst_score
        evidence.append(f"高效应情景: {catalyst_score:.1f}/30")
        
        # 子维度3: 风险矩阵（30%）
        # 基于证伪指标
        indicators = reasoning_result.counter_result.falsification_indicators
        triggered = sum(1 for ind in indicators if ind.is_triggered)
        if indicators:
            risk_score = (1 - triggered / len(indicators)) * 30
        else:
            risk_score = 15
        score += risk_score
        evidence.append(f"触发风险: {triggered}/{len(indicators)}")
        
        return DimensionScore(
            dimension_id=self.get_dimension_id(),
            score=min(score, 100),
            max_score=100,
            evidence=evidence,
            explanation=f"结论可靠性评分: {score:.1f}/100",
            confidence=confidence
        )


# ─────────────────────────────────────────────────
# 维度5: 可操作性（10%）
# ─────────────────────────────────────────────────

class ActionabilityCalculator(ScoreDimensionCalculator):
    """可操作性评分器
    
    子维度：
    - 目标价（40%）
    - 仓位（30%）
    - 止损（30%）
    """
    
    def get_dimension_id(self) -> str:
        return "D5_actionability"
    
    def get_max_score(self) -> float:
        return 100.0
    
    def get_weight(self) -> float:
        return 0.10
    
    def calculate(self, reasoning_result: ReasoningResult, context: QualityContext) -> DimensionScore:
        score = 0.0
        evidence = []
        
        # 子维度1: 目标价（40%）
        # 基于情景结果的置信区间
        if reasoning_result.scenario_results:
            intervals = [sr.effect.interval for sr in reasoning_result.scenario_results]
            has_interval = any(i.lower != i.upper for i in intervals)
            target_score = 40 if has_interval else 20
        else:
            target_score = 0
        score += target_score
        evidence.append(f"目标价区间: {'有' if target_score > 20 else '无'}")
        
        # 子维度2: 仓位（30%）
        # 基于置信度
        confidence = reasoning_result.confidence
        position_score = confidence * 30
        score += position_score
        evidence.append(f"仓位建议置信度: {confidence:.2f}")
        
        # 子维度3: 止损（30%）
        # 基于监控计划
        monitoring = reasoning_result.counter_result.monitoring_plan
        if monitoring and monitoring.triggers:
            stop_loss_score = min(len(monitoring.triggers) / 3, 1.0) * 30
        else:
            stop_loss_score = 0
        score += stop_loss_score
        evidence.append(f"止损触发器: {len(monitoring.triggers) if monitoring else 0}个")
        
        return DimensionScore(
            dimension_id=self.get_dimension_id(),
            score=min(score, 100),
            max_score=100,
            evidence=evidence,
            explanation=f"可操作性评分: {score:.1f}/100",
            confidence=confidence
        )
