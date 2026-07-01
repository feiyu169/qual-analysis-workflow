"""
quality/interfaces.py — 接口定义模块

定义推理引擎的核心接口：
- ScoreDimensionCalculator: 评分维度计算器
- ScoringEngine: 评分引擎
- ReasoningChain: 推理链
- ColdStartPolicy: 冷启动策略
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .types import (
    DimensionScore,
    EvidenceBundle,
    QualityContext,
    ReasoningResult,
    ScenarioConfig,
    ScoreReport,
)
from .budget import ReasoningBudget


class ScoreDimensionCalculator(ABC):
    """评分维度计算器接口
    
    每个实现负责计算一个维度的得分
    """
    
    @abstractmethod
    def calculate(self, reasoning_result: ReasoningResult, context: QualityContext) -> DimensionScore:
        """计算该维度得分
        
        Args:
            reasoning_result: 推理链输出
            context: 质量上下文
            
        Returns:
            DimensionScore: 维度评分结果
            
        Raises:
            CalculationError: 计算失败
        """
        ...
    
    @abstractmethod
    def get_max_score(self) -> float:
        """返回该维度满分"""
        ...
    
    @abstractmethod
    def get_weight(self) -> float:
        """返回该维度权重（0-1）"""
        ...
    
    @abstractmethod
    def get_dimension_id(self) -> str:
        """返回维度标识"""
        ...
    
    def explain(self, reasoning_result: ReasoningResult, context: QualityContext) -> str:
        """返回评分理由（可选覆盖）"""
        score = self.calculate(reasoning_result, context)
        return score.explanation


class ScoringEngine(ABC):
    """评分引擎接口
    
    负责聚合多个维度的评分，生成最终评分报告
    """
    
    @abstractmethod
    def score(self, reasoning_result: ReasoningResult, context: QualityContext) -> ScoreReport:
        """执行评分
        
        Args:
            reasoning_result: 推理链输出
            context: 质量上下文
            
        Returns:
            ScoreReport: 评分报告
            
        Raises:
            CalculationError: 计算失败
        """
        ...
    
    @abstractmethod
    def register_dimension(self, calculator: ScoreDimensionCalculator) -> None:
        """注册评分维度"""
        ...


class ReasoningChain(ABC):
    """推理链接口
    
    负责执行因果推理和情景分析
    """
    
    @abstractmethod
    def run(self, evidence: EvidenceBundle, config: ScenarioConfig, budget: ReasoningBudget) -> ReasoningResult:
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
        ...


class ColdStartPolicy(ABC):
    """冷启动策略协议
    
    定义系统在数据不足时的降级行为
    """
    
    @abstractmethod
    def get_seed_data(self) -> EvidenceBundle:
        """获取种子数据"""
        ...
    
    @abstractmethod
    def get_min_data_threshold(self) -> dict[str, int]:
        """获取最小数据量阈值
        
        Returns:
            dict: 如 {"financial_periods": 3, "news_count": 5}
        """
        ...
    
    @abstractmethod
    def get_fallback_output(self) -> ReasoningResult:
        """获取降级输出"""
        ...
    
    @abstractmethod
    def is_cold_start(self, evidence: EvidenceBundle) -> bool:
        """判断是否冷启动
        
        Args:
            evidence: 证据包
            
        Returns:
            bool: 是否需要冷启动
        """
        ...
