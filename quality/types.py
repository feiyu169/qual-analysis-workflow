"""
quality/types.py — 类型定义模块

定义推理引擎的核心数据类型：
- QualityContext: 统一质量上下文
- 量化输出类型: ConfidenceLevel, QuantifiedEffect, ScenarioProbability, CausalStrength
- 推理结果: ReasoningResult, CausalGraph, ScenarioResult, CounterResult
- 证据包: EvidenceBundle, ScenarioConfig
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, NamedTuple, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────
# 枚举类型
# ─────────────────────────────────────────────────

class DegradationLevel(str, Enum):
    """降级等级"""
    L0 = "L0"  # 🟢 FULL
    L1 = "L1"  # 🟡 PARTIAL
    L2 = "L2"  # 🟠 LIMITED
    L3 = "L3"  # 🔴 MINIMAL
    L4 = "L4"  # ⚫ BLOCKED


class ConfidenceLevel(str, Enum):
    """置信水平"""
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class EvidenceStrength(str, Enum):
    """证据强度"""
    STRONG = "强"
    MEDIUM = "中"
    WEAK = "弱"


class CausalMethod(str, Enum):
    """因果推断方法"""
    GRANGER = "granger"
    SENSITIVITY = "sensitivity"
    TEMPLATE = "template"
    HYBRID = "hybrid"


class ScenarioMode(str, Enum):
    """情景模式"""
    BASE = "base"
    STRESS = "stress"
    OPTIMISTIC = "optimistic"
    CUSTOM = "custom"


# ─────────────────────────────────────────────────
# 量化输出类型
# ─────────────────────────────────────────────────

class ConfidenceInterval(NamedTuple):
    """置信区间"""
    lower: float
    upper: float
    method: str  # "bootstrap" | "bayesian" | "historical"


class QuantifiedEffect(BaseModel):
    """量化效应"""
    level: ConfidenceLevel
    interval: ConfidenceInterval
    evidence_strength: EvidenceStrength
    causal_method: CausalMethod


class ScenarioProbability(BaseModel):
    """情景概率"""
    level: ConfidenceLevel
    interval: ConfidenceInterval
    generation_method: Literal["monte_carlo", "historical", "expert"]
    assumptions: list[str] = Field(default_factory=list)


class CausalStrength(BaseModel):
    """因果强度"""
    level: ConfidenceLevel
    evidence_strength: EvidenceStrength
    causal_method: CausalMethod
    assumptions: list[str] = Field(default_factory=list)
    sensitivity_results: dict[str, float] = Field(default_factory=dict)


# ─────────────────────────────────────────────────
# 推理结果类型
# ─────────────────────────────────────────────────

@dataclass
class CausalRelation:
    """因果关系"""
    cause: str
    effect: str
    strength: CausalStrength
    granger_pvalue: Optional[float] = None
    sensitivity_robust: Optional[float] = None


@dataclass
class CausalGraph:
    """因果图"""
    relations: list[CausalRelation]
    confidence: float
    assumptions: list[str] = field(default_factory=list)
    granger_pvalue: Optional[float] = None
    sensitivity_robust_ratio: Optional[float] = None


@dataclass
class ScenarioResult:
    """情景结果"""
    mode: ScenarioMode
    probability: ScenarioProbability
    effect: QuantifiedEffect
    assumptions: list[str] = field(default_factory=list)
    key_variables: dict[str, float] = field(default_factory=dict)


@dataclass
class FalsificationIndicator:
    """证伪指标"""
    name: str
    description: str
    measurement_method: str
    threshold: float
    current_value: Optional[float] = None
    is_triggered: bool = False


@dataclass
class MonitoringPlan:
    """监控计划"""
    triggers: list[dict[str, Any]] = field(default_factory=list)
    frequency: str = "daily"
    alert_threshold: float = 0.8


@dataclass
class CounterResult:
    """反面论证结果"""
    counter_arguments: list[str]
    counter_strengths: list[float] = field(default_factory=list)  # 每个论点的strength (0-1)
    falsification_indicators: list[FalsificationIndicator] = field(default_factory=list)
    monitoring_plan: MonitoringPlan = field(default_factory=MonitoringPlan)
    confidence_adjustment: float = 0.0


@dataclass
class ReasoningResult:
    """推理结果"""
    causal_graph: CausalGraph
    scenario_results: list[ScenarioResult]
    counter_result: CounterResult
    confidence: float
    checkpoints_passed: list[str] = field(default_factory=list)
    checkpoints_failed: list[str] = field(default_factory=list)
    trace_id: str = ""


# ─────────────────────────────────────────────────
# 证据包和配置
# ─────────────────────────────────────────────────

@dataclass
class EvidenceBundle:
    """证据包"""
    financial_data: dict[str, Any] = field(default_factory=dict)
    news_data: list[dict[str, Any]] = field(default_factory=list)
    industry_data: dict[str, Any] = field(default_factory=dict)
    filing_data: dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"
    timestamp: float = 0.0


@dataclass
class ScenarioConfig:
    """情景配置"""
    mode: ScenarioMode = ScenarioMode.BASE
    params: dict[str, float] = field(default_factory=dict)
    confidence_interval: float = 0.95


# ─────────────────────────────────────────────────
# 质量上下文
# ─────────────────────────────────────────────────

class DataSourceQuality(BaseModel):
    """数据源质量"""
    level: DegradationLevel
    sources: dict[str, str] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    confidence_cap: float = 1.0


class ReasoningQuality(BaseModel):
    """推理质量"""
    level: DegradationLevel
    checkpoints_passed: list[str] = Field(default_factory=list)
    checkpoints_failed: list[str] = Field(default_factory=list)
    confidence_cap: float = 1.0


class DepthQuality(BaseModel):
    """深度质量"""
    level: DegradationLevel
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    total_score: float = 0.0
    grade: str = ""


class QualityContext(BaseModel):
    """统一质量上下文"""
    data: DataSourceQuality
    reasoning: ReasoningQuality
    depth: DepthQuality
    version: str = "1.0"
    extra_info: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": False}

    @property
    def overall_level(self) -> DegradationLevel:
        """综合降级等级"""
        levels = [self.data.level, self.reasoning.level, self.depth.level]
        return max(levels, key=lambda x: int(x.value[1]))

    @property
    def is_blocked(self) -> bool:
        """是否阻断"""
        return self.overall_level == DegradationLevel.L4

    @property
    def confidence_cap(self) -> float:
        """置信度上限"""
        return min(self.data.confidence_cap, self.reasoning.confidence_cap)

    def generate_warning(self) -> str:
        """生成用户可见的警告"""
        if self.overall_level == DegradationLevel.L0:
            return ""
        warnings = []
        if self.data.level.value >= "L2":
            warnings.append(f"数据质量: {self.data.level.value}")
        if self.reasoning.level.value >= "L2":
            warnings.append(f"推理质量: {self.reasoning.level.value}")
        if self.depth.level.value >= "L2":
            warnings.append(f"深度质量: {self.depth.level.value}")
        return "⚠️ " + "；".join(warnings)


# ─────────────────────────────────────────────────
# 评分结果
# ─────────────────────────────────────────────────

class DimensionScore(BaseModel):
    """维度评分结果"""
    dimension_id: str
    score: float = Field(ge=0, le=100)
    max_score: float = Field(gt=0)
    evidence: list[str] = Field(default_factory=list)
    explanation: str = ""
    confidence: float = Field(ge=0, le=1, default=1.0)


class ScoreReport(BaseModel):
    """评分报告"""
    total_score: float = Field(ge=0, le=100)
    grade: Literal["S", "A", "B", "C", "D", "F"]
    dimension_scores: dict[str, DimensionScore] = Field(default_factory=dict)
    falsification_score: float = Field(ge=0, le=100, default=0.0)
    confidence: float = Field(ge=0, le=1, default=1.0)
    warnings: list[str] = Field(default_factory=list)
