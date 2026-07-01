"""
Quality Layer - 投资分析质量保证层

Phase 4: 质量层
- structural_check: 结构化预检 (Gate 4.1)
- auditor: 审计子代理 (Gate 4.2)
- repairer: 修复子代理 (Gate 4.3)
- checkpoint: 断点恢复 (Gate 4.4)

Phase 5: 推理引擎层
- types: 类型定义（QualityContext、量化输出类型、推理结果）
- exceptions: 异常体系
- budget: 预算控制（BudgetController、CircuitBreaker）
- interfaces: 接口定义（ScoreDimensionCalculator、ScoringEngine、ReasoningChain、ColdStartPolicy）
- reasoning: 推理引擎（CausalModeler、CounterArgumentValidator、CausalInferenceChain、DefaultColdStartPolicy）
- scoring: 评分器（StandardScoringEngine、5维度评分器、CN/HK Scorer）

Phase 6: 质量保证层
- formulas: 标准化计算公式库
- data_mapping: 数据口径映射表
- validators: 自动校验机制
"""

# Phase 4: 原有质量层
from .structural_check import structural_check, AuditResult
from .auditor import semantic_audit
from .repairer import repair_chapter
from .checkpoint import CheckpointManager

# Phase 5: 推理引擎层
from .reasoning import (
    CausalModeler,
    TemplateMatcher,
    GrangerTester,
    SensitivityAnalyzer,
    CounterArgumentValidator,
    CausalInferenceChain,
    DefaultColdStartPolicy,
)

from .scoring import (
    StandardScoringEngine,
    calculate_falsification_score,
    apply_falsification_rule,
    DataCompletenessCalculator,
    LogicConsistencyCalculator,
    AnalysisDepthCalculator,
    ConclusionReliabilityCalculator,
    ActionabilityCalculator,
    MarketScoreAdjuster,
    CNMarketAdjuster,
    HKMarketAdjuster,
    MarketScorerRegistry,
    get_default_registry,
)

from .types import (
    # 枚举类型
    DegradationLevel,
    ConfidenceLevel,
    EvidenceStrength,
    CausalMethod,
    ScenarioMode,
    # 量化输出类型
    ConfidenceInterval,
    QuantifiedEffect,
    ScenarioProbability,
    CausalStrength,
    # 推理结果类型
    CausalRelation,
    CausalGraph,
    ScenarioResult,
    FalsificationIndicator,
    MonitoringPlan,
    CounterResult,
    ReasoningResult,
    # 证据包和配置
    EvidenceBundle,
    ScenarioConfig,
    # 质量上下文
    DataSourceQuality,
    ReasoningQuality,
    DepthQuality,
    QualityContext,
    # 评分结果
    DimensionScore,
    ScoreReport,
)

from .exceptions import (
    InferenceError,
    BudgetExceededError,
    CircuitOpenError,
    CalculationError,
    DataQualityError,
    ModelInferenceError,
    MarketNotSupportedError,
)

from .budget import BudgetController, CircuitBreaker, ReasoningBudget

from .interfaces import (
    ScoreDimensionCalculator,
    ScoringEngine,
    ReasoningChain,
    ColdStartPolicy,
)

# Phase 6: Quality assurance layer
from .formulas import Formulas, FormulaResult
from .data_mapping import DataMappingRegistry, get_default_mapping_registry
from .validators import Validators, ReportValidator, ValidationResult, CheckResult
from .risk_quantification import (
    RiskFactor, RiskAssessment, StressTestScenario, StressTestResult,
    RiskQuantifier, format_risk_report, format_stress_test_report
)
from .margin_of_safety import (
    ValuationRange, SafetyMarginResult, MarginOfSafetyAnalyzer,
    format_safety_margin_report
)
from .sensitivity import (
    SensitivityVariable, SensitivityResult, TwoWaySensitivityResult,
    ScenarioAnalysis, ScenarioAnalysisResult, SensitivityAnalyzer,
    format_sensitivity_report
)
from .dcf import DCFInputs, DCFResult, DCFSensitivity, DCFCalculator, format_dcf_report

__all__ = [
    # Phase 4
    "structural_check",
    "semantic_audit",
    "repair_chapter",
    "AuditResult",
    "CheckpointManager",
    # Phase 5 - 推理引擎
    "CausalModeler",
    "TemplateMatcher",
    "GrangerTester",
    "SensitivityAnalyzer",
    "CounterArgumentValidator",
    "CausalInferenceChain",
    "DefaultColdStartPolicy",
    # Phase 5 - 评分器
    "StandardScoringEngine",
    "calculate_falsification_score",
    "apply_falsification_rule",
    "DataCompletenessCalculator",
    "LogicConsistencyCalculator",
    "AnalysisDepthCalculator",
    "ConclusionReliabilityCalculator",
    "ActionabilityCalculator",
    "MarketScoreAdjuster",
    "CNMarketAdjuster",
    "HKMarketAdjuster",
    "MarketScorerRegistry",
    "get_default_registry",
    # Phase 5 - 枚举类型
    "DegradationLevel",
    "ConfidenceLevel",
    "EvidenceStrength",
    "CausalMethod",
    "ScenarioMode",
    # Phase 5 - 量化输出类型
    "ConfidenceInterval",
    "QuantifiedEffect",
    "ScenarioProbability",
    "CausalStrength",
    # Phase 5 - 推理结果类型
    "CausalRelation",
    "CausalGraph",
    "ScenarioResult",
    "FalsificationIndicator",
    "MonitoringPlan",
    "CounterResult",
    "ReasoningResult",
    # Phase 5 - 证据包和配置
    "EvidenceBundle",
    "ScenarioConfig",
    # Phase 5 - 质量上下文
    "DataSourceQuality",
    "ReasoningQuality",
    "DepthQuality",
    "QualityContext",
    # Phase 5 - 评分结果
    "DimensionScore",
    "ScoreReport",
    # Phase 5 - 异常
    "InferenceError",
    "BudgetExceededError",
    "CircuitOpenError",
    "CalculationError",
    "DataQualityError",
    "ModelInferenceError",
    "MarketNotSupportedError",
    # Phase 5 - 预算控制
    "BudgetController",
    "CircuitBreaker",
    "ReasoningBudget",
    # Phase 5 - 接口
    "ScoreDimensionCalculator",
    "ScoringEngine",
    "ReasoningChain",
    "ColdStartPolicy",
    # Phase 6 - 质量保证
    "Formulas",
    "FormulaResult",
    "DataMappingRegistry",
    "get_default_mapping_registry",
    "Validators",
    "ReportValidator",
    "ValidationResult",
    "CheckResult",
]
