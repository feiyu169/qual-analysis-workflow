"""
Qual v9 核心数据类型（frozen dataclass）。

所有跨层传递的数据结构在此定义，消除 dict[str, Any] 传递。
设计原则：frozen=True 确保不可变性；tuple 替代 list 确保不可变语义。

参照：dayu-agent contracts/run.py（RunState 7 态）+ contracts/agent_execution.py（ExecutionContract）
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ============================================================
# Gate 状态机（对齐 dayu RunState 7 态）
# ============================================================

class GateState(str, Enum):  # noqa: UP042
    """Gate 状态枚举（7 态，对齐 dayu RunState）。

    状态机合法转换:
        PENDING → RUNNING → PASSED / FAILED / DEGRADED / BLOCKED / SKIPPED
        FAILED → RUNNING（重试）
        BLOCKED → 终态（enforce 阻断，不重试）
        SKIPPED → 终态（熔断跳过）
    """
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    DEGRADED = "degraded"
    BLOCKED = "blocked"   # 新增：enforce 阻断
    SKIPPED = "skipped"   # 新增：熔断跳过


# 合法状态转换表（frozenset 确保不可变，参照 dayu _VALID_TRANSITIONS）
_VALID_TRANSITIONS: dict[GateState, frozenset[GateState]] = {
    GateState.PENDING: frozenset({GateState.RUNNING, GateState.SKIPPED}),
    GateState.RUNNING: frozenset({GateState.PASSED, GateState.FAILED, GateState.DEGRADED, GateState.BLOCKED}),
    GateState.PASSED: frozenset(),
    GateState.FAILED: frozenset({GateState.RUNNING}),
    GateState.DEGRADED: frozenset(),
    GateState.BLOCKED: frozenset(),
    GateState.SKIPPED: frozenset(),
}


# ============================================================
# 执行阶段（对齐 dayu host RunPhase）
# ============================================================

class RunPhase(str, Enum):  # noqa: UP042
    """执行阶段枚举（对标 dayu host 执行生命周期）。

    映射到 Gate0-8 分组：
        INIT     → 初始化
        DATA     → Gate0-2（数据准备）
        WRITE    → Gate3（章节生成）
        AUDIT    → Gate4（审计修复）
        ASSEMBLE → Gate5-6（估值+结论）
        FINALIZE → Gate7-8（问题转化+终局验证）
    """
    INIT = "init"
    DATA = "data"
    WRITE = "write"
    AUDIT = "audit"
    ASSEMBLE = "assemble"
    FINALIZE = "finalize"


# Gate → Phase 映射
GATE_PHASE_MAP: dict[int, RunPhase] = {
    0: RunPhase.DATA, 1: RunPhase.DATA, 2: RunPhase.DATA,
    3: RunPhase.WRITE,
    4: RunPhase.AUDIT,
    5: RunPhase.ASSEMBLE, 6: RunPhase.ASSEMBLE,
    7: RunPhase.FINALIZE, 8: RunPhase.FINALIZE,
}


# ============================================================
# 写入管线阶段（对齐 dayu write_pipeline）
# ============================================================

class WritePipelinePhase(str, Enum):  # noqa: UP042
    """写入管线阶段（对标 dayu write_pipeline 状态机）。

    流转：DRAFT → REVIEW → REPAIR → CONFIRM → COMMIT
    - DRAFT:   初始生成
    - REVIEW:  审计检查
    - REPAIR:  确定性修复
    - CONFIRM: 修复后复验
    - COMMIT:  提交最终结果
    """
    DRAFT = "draft"
    REVIEW = "review"
    REPAIR = "repair"
    CONFIRM = "confirm"
    COMMIT = "commit"


# ============================================================
# 数据锚点契约（对标 dayu fins/storage 窄协议输入）
# ============================================================

@dataclass(frozen=True)
class DataAnchorContract:
    """数据锚点契约（不可变，替代 duck-typing anchor 参数）。

    Attributes:
        key: 原始键名。
        canonical_key: canonical 键名。
        unit: 单位。
        values: (fiscal_year, value) 对列表。
        source: 数据来源。
    """
    key: str
    canonical_key: str
    unit: str
    values: tuple[tuple[int | None, float], ...]
    source: str = "Wind"


@dataclass(frozen=True)
class FactBinding:
    """事实绑定记录（替代 fact_extractor 的 dict 传递）。

    Attributes:
        metric: 指标名。
        value: 数值。
        unit: 单位。
        source: 来源（Wind/Filing/Derived）。
        fiscal_year: 财年。
        confidence: 置信度。
        binding_type: 绑定类型（exact/derived/placeholder）。
    """
    metric: str
    value: float
    unit: str
    source: str  # "Wind" | "Filing" | "Derived"
    fiscal_year: int | None = None
    confidence: float = 1.0
    binding_type: str = "exact"  # "exact" | "derived" | "placeholder"


# ============================================================
# 检查器输出（替代各检查器各自定义的 Result 类型）
# ============================================================

@dataclass(frozen=True)
class CheckResult:
    """检查器统一输出（替代各检查器自定义的 Result/Issue 类型）。

    Attributes:
        checker_name: 检查器名称。
        passed: 是否通过。
        score: 评分（0-100）。
        violations: 违规列表（NumericViolation/StructuralViolation/ConsistencyIssue）。
    """
    checker_name: str
    passed: bool
    score: float = 100.0
    violations: tuple[Any, ...] = ()


@dataclass(frozen=True)
class GateStateTransition:
    """状态转换记录（审计日志用）。"""
    from_state: GateState
    to_state: GateState
    gate_num: int
    reason: str
    timestamp: str


def is_valid_transition(from_state: GateState, to_state: GateState) -> bool:
    """检查状态转换是否合法。"""
    return to_state in _VALID_TRANSITIONS.get(from_state, frozenset())


# ============================================================
# 数据点（参照 dayu DataPoint）
# ============================================================

@dataclass(frozen=True)
class DataPoint:
    """单个数据点（不可变）。

    Attributes:
        key: 指标名（canonical 键，如"营业收入"）
        value: 数值
        unit: 单位（如"亿元"）
        source: 数据来源（如"Wind"）
        fiscal_year: 财年（如 2025）
    """
    key: str
    value: float
    unit: str = "亿元"
    source: str = "Wind"
    fiscal_year: int | None = None


# ============================================================
# Gate 执行结果（参照 dayu GateResult）
# ============================================================

@dataclass(frozen=True)
class GateResult:
    """Gate 执行结果（不可变）。

    Attributes:
        gate_num: Gate 编号（0-8）
        state: 最终状态
        score: 质量评分（0-100）
        errors: 错误列表
        warnings: 告警列表
        execution_time: 执行耗时（秒）
        timestamp: 时间戳
    """
    gate_num: int
    state: GateState
    score: float = 0.0
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    execution_time: float = 0.0
    timestamp: str = ""

    @property
    def passed(self) -> bool:
        return self.state == GateState.PASSED

    @property
    def degraded(self) -> bool:
        return self.state == GateState.DEGRADED


# ============================================================
# 章节快照
# ============================================================

@dataclass(frozen=True)
class ChapterSnapshot:
    """单个章节快照（不可变）。

    Attributes:
        chapter_num: 章节编号（1-11）
        title: 章节标题
        content: 章节内容
        word_count: 字数
    """
    chapter_num: int
    title: str
    content: str
    word_count: int = 0


# ============================================================
# 检查器输出类型
# ============================================================

@dataclass(frozen=True)
class NumericViolation:
    """数值违规（NumericGuard 输出）。"""
    gate: str
    chapter: int
    message: str
    severity: str  # "fatal" | "important" | "suggestion"


@dataclass(frozen=True)
class StructuralViolation:
    """结构违规（StructuralCheck 输出）。"""
    chapter: int
    section: str
    message: str
    severity: str  # "critical" | "major" | "minor"


@dataclass(frozen=True)
class ConsistencyIssue:
    """跨章一致性问题（CrossChapterConsistency 输出）。

    只保留 data_conflict 类型（删除 conclusion_conflict 和 time_conflict）。
    """
    issue_type: str  # "data_conflict"
    severity: str  # "fatal" | "important" | "suggestion"
    description: str
    chapter1: int
    content1: str
    chapter2: int
    content2: str


@dataclass(frozen=True)
class ReviewIssue:
    """审查问题（Gate4 输出）。"""
    category: str  # "numeric" | "structural" | "consistency"
    description: str
    chapter: int
    severity: str  # "fatal" | "important" | "suggestion"
    fixable: bool = True


# ============================================================
# 修复相关
# ============================================================

@dataclass(frozen=True)
class RepairAction:
    """修复动作。"""
    target_chapter: int
    action_type: str  # "replace" | "insert" | "delete" | "bind_placeholder" | "bind_date"
    old_content: str
    new_content: str
    confidence: float = 1.0
    rule_id: str = ""


@dataclass(frozen=True)
class RepairRecord:
    """修复记录（审计日志用）。"""
    gate_num: int
    chapter_num: int
    rule_id: str
    before_value: str
    after_value: str
    repair_type: str
    confidence: float
    timestamp: str


@dataclass(frozen=True)
class AuditDecision:
    """审计决策（Gate4 输出，参照 dayu AuditDecision）。"""
    passed: bool
    state: GateState
    violations: tuple[ReviewIssue, ...] = ()
    repair_actions: tuple[RepairAction, ...] = ()
    score: float = 100.0


# ============================================================
# Gate 上下文（替代 dict[str, Any]）
# ============================================================

@dataclass(frozen=True)
class GateContext:
    """Gate 执行上下文（不可变，替代 dict[str, Any]）。

    Attributes:
        ticker: 股票代码
        company_name: 公司名称
        market: 市场类型（hk/us/cn）
        qual_mode: 运行模式（shadow/soft/enforce）
        chapters: 已生成章节（唯一允许的 mutable dict，修复过程中需要更新）
        wind_data: Wind 数据（原始 dict，逐步迁移到 WindDataContract）
        filing_data: 财报数据
        gate_results: 已完成的 Gate 结果
        llm_caller: LLM 调用器
        wall_deadline: 墙钟截止时间
        llm_call_budget: LLM 调用预算
        advc_enable_t2: ADVC T2 低置信修复开关
    """
    ticker: str
    company_name: str
    market: str
    qual_mode: str = "shadow"
    chapters: dict[int, str] = field(default_factory=dict)
    wind_data: dict[str, Any] | None = None
    filing_data: dict[str, Any] | None = None
    gate_results: dict[int, GateResult] = field(default_factory=dict)
    llm_caller: Callable[[str, str], str] | None = None
    wall_deadline: float | None = None
    llm_call_budget: int | None = None
    advc_enable_t2: bool = False

    def with_chapters(self, new_chapters: dict[int, str]) -> GateContext:
        """返回更新了章节的新上下文（不可变模式）。"""
        return GateContext(
            ticker=self.ticker,
            company_name=self.company_name,
            market=self.market,
            qual_mode=self.qual_mode,
            chapters=new_chapters,
            wind_data=self.wind_data,
            filing_data=self.filing_data,
            gate_results=self.gate_results,
            llm_caller=self.llm_caller,
            wall_deadline=self.wall_deadline,
            llm_call_budget=self.llm_call_budget,
            advc_enable_t2=self.advc_enable_t2,
        )

    def with_gate_result(self, gate_num: int, result: GateResult) -> GateContext:
        """返回更新了 Gate 结果的新上下文。"""
        new_results = dict(self.gate_results)
        new_results[gate_num] = result
        return GateContext(
            ticker=self.ticker,
            company_name=self.company_name,
            market=self.market,
            qual_mode=self.qual_mode,
            chapters=self.chapters,
            wind_data=self.wind_data,
            filing_data=self.filing_data,
            gate_results=new_results,
            llm_caller=self.llm_caller,
            wall_deadline=self.wall_deadline,
            llm_call_budget=self.llm_call_budget,
            advc_enable_t2=self.advc_enable_t2,
        )


# ============================================================
# 工作流运行结果
# ============================================================

@dataclass(frozen=True)
class WorkflowRunResult:
    """工作流最终结果（不可变）。

    Attributes:
        run_id: 运行 ID
        passed: 是否通过
        gate_results: 各 Gate 结果
        report: 最终报告内容
        quality_degraded: 是否有质量降级
        degradation_reasons: 降级原因列表
        elapsed_seconds: 总耗时
    """
    run_id: str
    passed: bool
    gate_results: dict[int, GateResult] = field(default_factory=dict)
    report: str = ""
    quality_degraded: bool = False
    degradation_reasons: tuple[str, ...] = ()
    elapsed_seconds: float = 0.0
