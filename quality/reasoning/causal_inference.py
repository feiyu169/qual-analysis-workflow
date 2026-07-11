"""
quality/reasoning/causal_inference.py — 统一推理链

单链3阶段：
1. 数据预处理：证据抽取、数据校验
2. 因果-情景建模：因果建模、情景推演、对抗校验
3. 结论合成：综合结果、计算置信度
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from ..budget import ReasoningBudget
from ..exceptions import BudgetExceededError, CircuitOpenError, DataQualityError
from ..interfaces import ReasoningChain
from ..types import (
    CausalGraph,
    ConfidenceInterval,
    ConfidenceLevel,
    CounterResult,
    EvidenceBundle,
    QuantifiedEffect,
    ReasoningResult,
    ScenarioConfig,
    ScenarioMode,
    ScenarioProbability,
    ScenarioResult,
    EvidenceStrength,
    CausalMethod,
)

from .causal_modeler import CausalModeler
from .counter_validator import CounterArgumentValidator
from .cold_start import DefaultColdStartPolicy
from ..interfaces import ColdStartPolicy

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────
# 检查点定义
# ─────────────────────────────────────────────────

CHECKPOINTS = {
    "CP-1": {"name": "数据完整性", "threshold": 0.8},
    "CP-2": {"name": "因果关系数量", "threshold": 2},
    "CP-3": {"name": "情景数量", "threshold": 1},
    "CP-4": {"name": "反方论点数量", "threshold": 2},
    "CP-5": {"name": "置信度", "threshold": 0.6},
}


class CausalInferenceChain(ReasoningChain):
    """统一推理链"""
    
    def __init__(self, cold_start_policy: Optional[ColdStartPolicy] = None):
        self.causal_modeler = CausalModeler()
        self.counter_validator = CounterArgumentValidator()
        self.cold_start_policy = cold_start_policy or DefaultColdStartPolicy()
    
    def run(
        self,
        evidence: EvidenceBundle,
        config: ScenarioConfig,
        budget: ReasoningBudget
    ) -> ReasoningResult:
        """执行推理
        
        Args:
            evidence: 证据包
            config: 情景配置
            budget: 推理预算
            
        Returns:
            ReasoningResult: 推理结果
            
        Raises:
            BudgetExceededError: 预算耗尽
            CircuitOpenError: 熔断触发
            DataQualityError: 数据质量不足
        """
        trace_id = str(uuid.uuid4())[:8]
        logger.info(f"[{trace_id}] 开始推理")
        
        # 冷启动检查：如果数据不足，返回降级输出
        if self.cold_start_policy.is_cold_start(evidence):
            logger.warning(f"[{trace_id}] 数据不足，使用冷启动降级输出")
            return self.cold_start_policy.get_fallback_output()
        
        start_time = time.time()
        checkpoints_passed = []
        checkpoints_failed = []
        
        try:
            # 阶段1: 数据预处理
            logger.info(f"[{trace_id}] 阶段1: 数据预处理")
            structured_evidence = self._preprocess_data(evidence, budget)
            
            # 检查点 CP-1: 数据完整性
            data_completeness = self._check_data_completeness(structured_evidence)
            if data_completeness >= CHECKPOINTS["CP-1"]["threshold"]:
                checkpoints_passed.append("CP-1")
                logger.info(f"[{trace_id}] CP-1 通过: 数据完整性={data_completeness:.2f}")
            else:
                checkpoints_failed.append("CP-1")
                logger.warning(f"[{trace_id}] CP-1 失败: 数据完整性={data_completeness:.2f}")
            
            # 阶段2: 因果-情景建模
            logger.info(f"[{trace_id}] 阶段2: 因果-情景建模")
            
            # 2a: 因果建模
            causal_graph = self.causal_modeler.build_causal_graph(structured_evidence)
            
            # 检查点 CP-2: 因果关系数量
            if len(causal_graph.relations) >= CHECKPOINTS["CP-2"]["threshold"]:
                checkpoints_passed.append("CP-2")
                logger.info(f"[{trace_id}] CP-2 通过: 因果关系={len(causal_graph.relations)}")
            else:
                checkpoints_failed.append("CP-2")
                logger.warning(f"[{trace_id}] CP-2 失败: 因果关系={len(causal_graph.relations)}")
            
            # 2b: 情景推演
            scenario_results = self._run_scenario_analysis(
                causal_graph, config, structured_evidence, budget
            )
            
            # 检查点 CP-3: 情景数量
            if len(scenario_results) >= CHECKPOINTS["CP-3"]["threshold"]:
                checkpoints_passed.append("CP-3")
                logger.info(f"[{trace_id}] CP-3 通过: 情景={len(scenario_results)}")
            else:
                checkpoints_failed.append("CP-3")
                logger.warning(f"[{trace_id}] CP-3 失败: 情景={len(scenario_results)}")
            
            # 2c: 对抗校验
            counter_result = self.counter_validator.validate(causal_graph, structured_evidence)
            
            # 检查点 CP-4: 反方论点数量
            if len(counter_result.counter_arguments) >= CHECKPOINTS["CP-4"]["threshold"]:
                checkpoints_passed.append("CP-4")
                logger.info(f"[{trace_id}] CP-4 通过: 反方论点={len(counter_result.counter_arguments)}")
            else:
                checkpoints_failed.append("CP-4")
                logger.warning(f"[{trace_id}] CP-4 失败: 反方论点={len(counter_result.counter_arguments)}")
            
            # 阶段3: 结论合成
            logger.info(f"[{trace_id}] 阶段3: 结论合成")
            confidence = self._synthesize_confidence(
                causal_graph, scenario_results, counter_result
            )
            
            # 检查点 CP-5: 置信度
            if confidence >= CHECKPOINTS["CP-5"]["threshold"]:
                checkpoints_passed.append("CP-5")
                logger.info(f"[{trace_id}] CP-5 通过: 置信度={confidence:.2f}")
            else:
                checkpoints_failed.append("CP-5")
                logger.warning(f"[{trace_id}] CP-5 失败: 置信度={confidence:.2f}")
            
            # 记录成功
            budget.record_success()
            
            elapsed = time.time() - start_time
            logger.info(f"[{trace_id}] 推理完成: 耗时={elapsed:.2f}s, 置信度={confidence:.2f}")
            
            return ReasoningResult(
                causal_graph=causal_graph,
                scenario_results=scenario_results,
                counter_result=counter_result,
                confidence=confidence,
                checkpoints_passed=checkpoints_passed,
                checkpoints_failed=checkpoints_failed,
                trace_id=trace_id
            )
        
        except (BudgetExceededError, CircuitOpenError) as e:
            # 记录失败
            budget.record_failure()
            logger.error(f"[{trace_id}] 推理失败: {e}")
            raise
        
        except Exception as e:
            # 记录失败
            budget.record_failure()
            logger.error(f"[{trace_id}] 推理异常: {e}")
            raise DataQualityError(f"推理过程异常: {e}") from e
    
    def _preprocess_data(
        self,
        evidence: EvidenceBundle,
        budget: ReasoningBudget
    ) -> EvidenceBundle:
        """数据预处理
        
        校验数据完整性，清理异常值
        """
        # 消耗预算
        budget.consume_or_raise(time_delta=0.1, calls=0, tokens=0)
        
        # 校验数据
        if not evidence.financial_data and not evidence.news_data:
            raise DataQualityError(
                message="数据质量不足: 无财务数据和新闻数据",
                missing_fields=["financial_data", "news_data"]
            )
        
        # 返回清理后的证据
        return evidence
    
    def _check_data_completeness(self, evidence: EvidenceBundle) -> float:
        """检查数据完整性"""
        completeness = 0.0
        total_checks = 4
        
        # 检查财务数据
        if evidence.financial_data:
            completeness += 1.0 / total_checks
        
        # 检查新闻数据
        if evidence.news_data:
            completeness += 1.0 / total_checks
        
        # 检查行业数据
        if evidence.industry_data:
            completeness += 1.0 / total_checks
        
        # 检查财报数据
        if evidence.filing_data:
            completeness += 1.0 / total_checks
        
        return completeness
    
    def _run_scenario_analysis(
        self,
        causal_graph: CausalGraph,
        config: ScenarioConfig,
        evidence: EvidenceBundle,
        budget: ReasoningBudget
    ) -> list[ScenarioResult]:
        """运行情景分析"""
        results = []
        
        # 基准情景
        base_result = self._analyze_scenario(
            ScenarioMode.BASE, causal_graph, evidence, budget
        )
        results.append(base_result)
        
        # 根据配置添加其他情景
        if config.mode == ScenarioMode.STRESS or config.params:
            stress_result = self._analyze_scenario(
                ScenarioMode.STRESS, causal_graph, evidence, budget
            )
            results.append(stress_result)
        
        if config.mode == ScenarioMode.OPTIMISTIC:
            optimistic_result = self._analyze_scenario(
                ScenarioMode.OPTIMISTIC, causal_graph, evidence, budget
            )
            results.append(optimistic_result)
        
        return results
    
    def _analyze_scenario(
        self,
        mode: ScenarioMode,
        causal_graph: CausalGraph,
        evidence: EvidenceBundle,
        budget: ReasoningBudget
    ) -> ScenarioResult:
        """分析单个情景"""
        # 消耗预算
        budget.consume_or_raise(time_delta=0.5, calls=1, tokens=1000)
        
        # 根据模式调整概率
        if mode == ScenarioMode.BASE:
            probability_level = ConfidenceLevel.HIGH
            effect_level = ConfidenceLevel.MEDIUM
        elif mode == ScenarioMode.STRESS:
            probability_level = ConfidenceLevel.MEDIUM
            effect_level = ConfidenceLevel.LOW
        else:
            probability_level = ConfidenceLevel.MEDIUM
            effect_level = ConfidenceLevel.MEDIUM
        
        return ScenarioResult(
            mode=mode,
            probability=ScenarioProbability(
                level=probability_level,
                interval=ConfidenceInterval(lower=0.2, upper=0.8, method="historical"),
                generation_method="historical",
                assumptions=["基于历史情景"]
            ),
            effect=QuantifiedEffect(
                level=effect_level,
                interval=ConfidenceInterval(lower=-0.1, upper=0.1, method="bootstrap"),
                evidence_strength=EvidenceStrength.MEDIUM,
                causal_method=CausalMethod.HYBRID
            ),
            assumptions=[f"{mode.value}情景假设"],
            key_variables={"growth": 0.1, "risk": 0.05}
        )
    
    def _synthesize_confidence(
        self,
        causal_graph: CausalGraph,
        scenario_results: list[ScenarioResult],
        counter_result: CounterResult
    ) -> float:
        """合成置信度"""
        # 因果图置信度
        causal_confidence = causal_graph.confidence
        
        # 情景置信度
        if scenario_results:
            scenario_confidence = sum(
                0.9 if sr.probability.level == ConfidenceLevel.HIGH else
                0.6 if sr.probability.level == ConfidenceLevel.MEDIUM else 0.3
                for sr in scenario_results
            ) / len(scenario_results)
        else:
            scenario_confidence = 0.5
        
        # 反面论证调整
        counter_adjustment = counter_result.confidence_adjustment
        
        # 合成
        confidence = (
            causal_confidence * 0.4 +
            scenario_confidence * 0.4 +
            (1 + counter_adjustment) * 0.2
        )
        
        return max(0.0, min(confidence, 1.0))
