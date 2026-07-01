"""
quality/scoring/__init__.py — 评分器模块

包含：
- StandardScoringEngine: 标准评分引擎
- 5维度评分器: DataCompleteness/LogicConsistency/AnalysisDepth/ConclusionReliability/Actionability
- 证伪得分计算: calculate_falsification_score
- 强制降级规则: apply_falsification_rule
- 市场调整器: CNMarketAdjuster/HKMarketAdjuster/MarketScorerRegistry
"""

from .engine import StandardScoringEngine, calculate_falsification_score, apply_falsification_rule
from ..validators import Validators, ReportValidator, ValidationResult, CheckResult
from .dimensions import (
    DataCompletenessCalculator,
    LogicConsistencyCalculator,
    AnalysisDepthCalculator,
    ConclusionReliabilityCalculator,
    ActionabilityCalculator,
)
from .market_adjuster import (
    MarketScoreAdjuster,
    CNMarketAdjuster,
    HKMarketAdjuster,
    MarketScorerRegistry,
    get_default_registry,
)

__all__ = [
    # 引擎
    "StandardScoringEngine",
    "calculate_falsification_score",
    "apply_falsification_rule",
    # 维度
    "DataCompletenessCalculator",
    "LogicConsistencyCalculator",
    "AnalysisDepthCalculator",
    "ConclusionReliabilityCalculator",
    "ActionabilityCalculator",
    # 市场调整器
    "MarketScoreAdjuster",
    "CNMarketAdjuster",
    "HKMarketAdjuster",
    "MarketScorerRegistry",
    "get_default_registry",
]
