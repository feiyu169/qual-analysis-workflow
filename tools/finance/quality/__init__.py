"""
quality — 质量保障模块包（HGF P0-① 修复 2026-08-22：补全顶层 re-export）。

组件代次：COMPONENT_GEN = "v3"（质量组件层整体换代用；独立于包版本 finance.__version__ 与
         架构代次 qual_v8.ARCH_GEN——三刻度分离，见 docs/qual-version-architecture.md）

导出 workflow.py 依赖的顶层符号：
- structural_check / semantic_audit / repair_chapter（审计修复循环）
- CheckpointManager（断点持久化）
- 历史测试契约符号（v3 时代顶层 API——平铺模块 re-export，兼容 quality/tests/ 旧测试）
"""
# 组件代次（三刻度之一）
COMPONENT_GEN = "v3"

from .auditor import semantic_audit
from .budget import ReasoningBudget
from .causal_inference import CausalInferenceChain
from .checkpoint import CheckpointManager
from .cold_start import DefaultColdStartPolicy
from .dimensions import (
    ActionabilityCalculator,
    AnalysisDepthCalculator,
    ConclusionReliabilityCalculator,
    DataCompletenessCalculator,
    LogicConsistencyCalculator,
)

# ====================================================================
# HGF P0-①：历史测试契约顶层符号 re-export（v3 时代 API——平铺模块实现）
# ====================================================================
from .engine import StandardScoringEngine
from .formulas import Formulas
from .market_adjuster import (
    CNMarketAdjuster,
    HKMarketAdjuster,
    MarketScorerRegistry,
)
from .repairer import repair_chapter
from .structural_check import structural_check
from .types import (
    DataSourceQuality,
    DegradationLevel,  # types.DegradationLevel（L0-L4）——优先于 pipeline 的内部枚举
    DepthQuality,
    EvidenceBundle,
    QualityContext,
    ReasoningQuality,
    ScenarioConfig,
    ScenarioMode,
)
from .validators import Validators

__all__ = [
    "COMPONENT_GEN",
    "ActionabilityCalculator",
    "AnalysisDepthCalculator",
    "CNMarketAdjuster",
    "CausalInferenceChain",
    "CheckpointManager",
    "ConclusionReliabilityCalculator",
    "DataCompletenessCalculator",
    "DataSourceQuality",
    "DefaultColdStartPolicy",
    "DegradationLevel",
    "DepthQuality",
    "EvidenceBundle",
    "Formulas",
    "HKMarketAdjuster",
    "LogicConsistencyCalculator",
    "MarketScorerRegistry",
    "QualityContext",
    "ReasoningBudget",
    "ReasoningQuality",
    "ScenarioConfig",
    "ScenarioMode",
    "StandardScoringEngine",
    "Validators",
    "repair_chapter",
    "semantic_audit",
    "structural_check",
]
