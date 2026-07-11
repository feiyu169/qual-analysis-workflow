"""
quality/reasoning/counter_validator.py — 反面论证验证器

作为因果链的对抗校验子模块：
- 角色切换：切换到看空者视角
- 反方论点构建：生成最强反面观点
- 证伪指标设计：设计可观察、可量化的证伪指标
- 触发条件监控：定义监控阈值和频率
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from ..types import (
    CausalGraph,
    CounterResult,
    EvidenceBundle,
    FalsificationIndicator,
    MonitoringPlan,
)

logger = logging.getLogger(__name__)


@dataclass
class CounterArgument:
    """反方论点"""
    argument: str
    evidence: list[str]
    strength: float  # 0-1
    category: str  # "fundamental" | "technical" | "sentiment"


class CounterArgumentValidator:
    """反面论证验证器"""
    
    def validate(self, causal_graph: CausalGraph, evidence: EvidenceBundle) -> CounterResult:
        """执行反面论证验证
        
        Args:
            causal_graph: 因果图
            evidence: 证据包
            
        Returns:
            CounterResult: 反面论证结果
        """
        logger.info("开始反面论证验证")
        
        # Step 1: 角色切换
        counter_perspective = self._switch_perspective(causal_graph, evidence)
        
        # Step 2: 反方论点构建
        counter_arguments = self._build_counter_arguments(counter_perspective, evidence)
        logger.info(f"生成 {len(counter_arguments)} 条反方论点")
        
        # Step 3: 证伪指标设计
        falsification_indicators = self._design_falsification_indicators(counter_arguments, causal_graph)
        logger.info(f"设计 {len(falsification_indicators)} 个证伪指标")
        
        # Step 4: 触发条件监控
        monitoring_plan = self._create_monitoring_plan(falsification_indicators)
        
        # Step 5: 计算置信度调整
        confidence_adjustment = self._calculate_adjustment(counter_arguments)
        
        # 转换为字符串列表
        counter_argument_strings = [ca.argument for ca in counter_arguments]
        counter_strengths = [ca.strength for ca in counter_arguments]
        
        logger.info(f"反面论证完成: 置信度调整={confidence_adjustment:.2f}")
        
        return CounterResult(
            counter_arguments=counter_argument_strings,
            counter_strengths=counter_strengths,
            falsification_indicators=falsification_indicators,
            monitoring_plan=monitoring_plan,
            confidence_adjustment=confidence_adjustment
        )
    
    def _switch_perspective(self, causal_graph: CausalGraph, evidence: EvidenceBundle) -> dict:
        """切换到看空者视角
        
        从因果图中提取关键假设，构建反面视角
        """
        counter_perspective = {
            "challenged_assumptions": [],
            "alternative_explanations": [],
            "risk_factors": []
        }
        
        # 挑战因果图中的假设
        for assumption in causal_graph.assumptions:
            counter_perspective["challenged_assumptions"].append({
                "assumption": assumption,
                "challenge": f"假设'{assumption}'可能不成立"
            })
        
        # 提取替代解释
        for relation in causal_graph.relations:
            counter_perspective["alternative_explanations"].append({
                "original": f"{relation.cause} → {relation.effect}",
                "alternative": f"{relation.effect}可能由其他因素驱动"
            })
        
        # 提取风险因素
        risk_keywords = ["风险", "下降", "减少", "恶化", "不确定"]
        for news in evidence.news_data:
            if isinstance(news, dict):
                title = news.get("title", "")
                for keyword in risk_keywords:
                    if keyword in title:
                        counter_perspective["risk_factors"].append(title)
                        break
        
        return counter_perspective
    
    def _build_counter_arguments(
        self,
        counter_perspective: dict,
        evidence: EvidenceBundle
    ) -> list[CounterArgument]:
        """构建反方论点"""
        arguments = []
        
        # 基于挑战的假设构建论点
        for challenge in counter_perspective.get("challenged_assumptions", []):
            arguments.append(CounterArgument(
                argument=challenge["challenge"],
                evidence=[challenge["assumption"]],
                strength=0.6,
                category="fundamental"
            ))
        
        # 基于替代解释构建论点
        for alt in counter_perspective.get("alternative_explanations", []):
            arguments.append(CounterArgument(
                argument=alt["alternative"],
                evidence=[alt["original"]],
                strength=0.5,
                category="fundamental"
            ))
        
        # 基于风险因素构建论点
        for risk in counter_perspective.get("risk_factors", []):
            arguments.append(CounterArgument(
                argument=f"风险因素: {risk}",
                evidence=[risk],
                strength=0.7,
                category="sentiment"
            ))
        
        # 确保至少有2条反方论点
        if len(arguments) < 2:
            arguments.append(CounterArgument(
                argument="市场预期可能过于乐观",
                evidence=[],
                strength=0.4,
                category="sentiment"
            ))
            arguments.append(CounterArgument(
                argument="存在未被识别的系统性风险",
                evidence=[],
                strength=0.3,
                category="fundamental"
            ))
        
        return arguments
    
    def _design_falsification_indicators(
        self,
        counter_arguments: list[CounterArgument],
        causal_graph: CausalGraph
    ) -> list[FalsificationIndicator]:
        """设计证伪指标"""
        indicators = []
        
        # 基于反方论点设计指标
        for i, arg in enumerate(counter_arguments[:5]):  # 最多5个指标
            indicators.append(FalsificationIndicator(
                name=f"证伪指标_{i+1}",
                description=f"验证'{arg.argument}'的指标",
                measurement_method="定量监控",
                threshold=0.5,
                current_value=None,
                is_triggered=False
            ))
        
        # 基于因果关系设计指标
        for i, relation in enumerate(causal_graph.relations[:3]):
            indicators.append(FalsificationIndicator(
                name=f"因果关系_{relation.cause}_{relation.effect}",
                description=f"验证'{relation.cause}→{relation.effect}'的指标",
                measurement_method="Granger检验p值",
                threshold=0.1,
                current_value=relation.granger_pvalue,
                is_triggered=relation.granger_pvalue is not None and relation.granger_pvalue > 0.1
            ))
        
        return indicators
    
    def _create_monitoring_plan(
        self,
        indicators: list[FalsificationIndicator]
    ) -> MonitoringPlan:
        """创建监控计划"""
        triggers = []
        
        for indicator in indicators:
            triggers.append({
                "indicator": indicator.name,
                "threshold": indicator.threshold,
                "action": "触发降级" if indicator.is_triggered else "继续监控",
                "frequency": "daily"
            })
        
        return MonitoringPlan(
            triggers=triggers,
            frequency="daily",
            alert_threshold=0.8
        )
    
    def _calculate_adjustment(self, counter_arguments: list[CounterArgument]) -> float:
        """计算置信度调整
        
        反方论点越强，置信度调整越大（负值）
        """
        if not counter_arguments:
            return 0.0
        
        # 计算平均强度
        avg_strength = sum(ca.strength for ca in counter_arguments) / len(counter_arguments)
        
        # 调整量：强度越高，调整越大
        adjustment = -avg_strength * 0.2  # 最大调整 -20%
        
        return max(adjustment, -0.3)  # 限制最大调整为 -30%
