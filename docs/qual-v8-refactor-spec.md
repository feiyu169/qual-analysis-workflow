# Qual v8 重构规格（对照 dayu-agent 代码规范）

> 生成时间：2026-08-23  
> 基准：`tools/finance/qual_v8/` 全量源码审计  
> 规范来源：dayu-agent AGENTS.md 九项能力 + contracts 层示例

---

## 一、总体诊断

### 当前架构
```
qual_v8/
├── workflow.py          (495行) ← 主编排，唯一入口
├── core/                (6个文件，共 867行) ← 状态机/审计/熔断/错误分类/监督/引擎
├── gates/               (9个文件，共 2,764行) ← Gate0-8 实现
├── data_anchor.py       (489行) ← 数据锚点（跨章数据同步）
├── numeric_binder.py    (456行) ← 数字回填（PGNB）
├── anchor_repair.py     (258行) ← 锚点驱动确定性修复（ADVC）
├── adapters.py          (148行) ← v2-v7 组件适配层
├── mode_manager.py      (122行) ← 模式管理（shadow/soft/enforce）
├── workflow_context.py  (420行) ← 非侵入式上下文（重复 workflow.py）
├── step_gate_mapping.py (88行) ← Step/Gate 映射表
├── solutions.py         (33行) ← 重复 step_gate_mapping
├── monitoring/alerts.py (170行) ← 监控告警
├── security/auth.py     (162行) ← RBAC 权限矩阵
└── tests/test_core.py   (324行) ← 测试
```

### AGENTS.md 违规清单

| 违规类型 | 文件 | 严重程度 |
|---------|------|---------|
| **`Any` 类型滥用** | workflow.py, gate_engine.py, gate0-8.py, adapters.py, supervisor.py | 高 |
| **无类型返回值** | gate_engine.py `execute()` 返回 `GateResult` 但内部用 `dict[str, Any]` | 高 |
| **God Object** | workflow.py `QualWorkflow` 承担编排+配置+重试+阻断+组装 | 高 |
| **重复代码** | workflow_context.py 与 workflow.py 重复 80% 流程定义 | 高 |
| **重复代码** | solutions.py 与 step_gate_mapping.py 完全重复 | 中 |
| **魔法数字** | gate8.py `50*1024`, `500*1024`, `12000` 字符阈值 | 中 |
| **无类型参数** | `_validate_data(filing_result, wind_result, context)` 全 `dict` | 中 |
| **兼容性代码** | security/auth.py RBAC 从未被调用（dead code） | 中 |
| **缺少 docstring** | 多数内部方法无中文 docstring | 中 |

---

## 二、逐文件重构规格

---

### 文件 1：`workflow.py`（495行）→ 拆分

**当前状态**：
- 行数：495
- 职责：QualWorkflow 主类 + WorkflowConfig + RETRY_POLICY + _FLOW_DEFINITION + _is_critical_gate_error + execute() 主循环
- 问题：God Object（编排+配置+重试+阻断+报告组装+指标收集混在一起）；`typing.Any` 泛滥；`context: dict[str, Any]` 无契约

**重构动作**：拆分为 4 个文件

**重构后规格**：

```python
# qual_v8/contracts.py (~120行)
# 核心数据契约（dataclass + Enum，零业务逻辑）

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class QualMode(str, Enum):
    """Qual 流程运行模式"""
    SHADOW = "shadow"
    SOFT = "soft"
    ENFORCE = "enforce"


class RunPhase(str, Enum):
    """工作流运行阶段"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    ASSEMBLING = "assembling"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True)
class RetryPolicy:
    """重试策略（不可变）"""
    gate_attempts: int      # 执行次数
    gate_retries: int       # 重试次数
    skip_repair: bool       # 是否跳过修复


# 三模式重试策略表（单一事实来源）
RETRY_POLICIES: dict[QualMode, RetryPolicy] = {
    QualMode.SHADOW:  RetryPolicy(gate_attempts=1, gate_retries=0, skip_repair=True),
    QualMode.SOFT:    RetryPolicy(gate_attempts=2, gate_retries=1, skip_repair=False),
    QualMode.ENFORCE: RetryPolicy(gate_attempts=3, gate_retries=2, skip_repair=False),
}


@dataclass
class WorkflowConfig:
    """工作流配置（所有数值有明确语义）"""
    max_retries: int = 3
    timeout_per_gate_seconds: int = 600
    global_timeout_seconds: int = 5400
    max_llm_calls_per_gate: int = 200
    shadow_skip_repair: bool = True
    advc_enable_t2: bool = False


@dataclass
class GateOutput:
    """单 Gate 输出（替代 dict[str, Any]）"""
    gate_num: int
    passed: bool
    score: float
    execution_time_seconds: float
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    check_criteria_passed: bool


@dataclass
class WorkflowResult:
    """工作流最终结果（不可变）"""
    run_id: str
    passed: bool
    gate_outputs: dict[int, GateOutput]
    quality_degraded: bool
    state_history: tuple[dict[str, str], ...]
    audit_entries_count: int


@dataclass
class WorkflowContext:
    """工作流入参契约（替代 context: dict[str, Any]）"""
    ticker: str
    company_name: str
    market: str                              # "cn" | "hk" | "us"
    wind_data: dict[str, object]             # Wind canonical 数据
    filing_data: dict[str, object] | None = None
    llm_caller: object | None = None         # LLM 调用器（Protocol 约束见 llm_caller.py）
    shares: float | None = None
    qual_mode: QualMode = QualMode.SHADOW
    human_confirmed: bool = True
    output_dir: str | None = None
```

```python
# qual_v8/retry_engine.py (~80行)
# 重试 + 熔断 + 墙钟预算（从 workflow.py execute() 提取）

import time
from .contracts import RetryPolicy, WorkflowConfig


def should_continue_gate(
    attempt: int,
    policy: RetryPolicy,
    circuit_breaker_open: bool,
) -> bool:
    """判断 Gate 是否应继续重试"""
    ...


def check_wall_clock(deadline: float) -> bool:
    """检查墙钟预算是否耗尽"""
    return time.monotonic() > deadline


def build_wall_deadline(config: WorkflowConfig) -> float:
    """构建墙钟截止时间"""
    return time.monotonic() + config.global_timeout_seconds
```

```python
# qual_v8/report_assembler.py (~60行)
# 报告组装（从 workflow.py execute() 末尾提取）

from .contracts import WorkflowResult


def assemble_report(
    chapters: dict[int, str],
    company_name: str,
    ticker: str,
) -> str:
    """从章节组装报告"""
    ...


def attach_quality_marker(
    report: str,
    mode: str,
    failed_gates: list[str],
) -> str:
    """在报告头部附加质量受限声明"""
    ...
```

```python
# qual_v8/workflow.py (~200行，重构后)
# 主编排（仅编排，不含配置/重试/组装逻辑）

from .contracts import WorkflowConfig, WorkflowContext, WorkflowResult, GateOutput


class QualWorkflow:
    """Qual 工作流编排器（Gate0→8 顺序执行）"""

    def __init__(self, config: WorkflowConfig | None = None) -> None:
        ...

    def execute(self, ctx: WorkflowContext) -> WorkflowResult:
        """执行工作流"""
        ...

    def get_status(self) -> dict[str, str]:
        """获取当前状态"""
        ...
```

**迁移策略**：
1. 先创建 `contracts.py`，将所有 dataclass/Enum 迁入
2. 提取 `retry_engine.py` + `report_assembler.py`
3. 重写 `workflow.py` 使用新契约
4. 调用方（gate0-8）逐步从 `context: dict` 迁移到 `WorkflowContext`

**验证标准**：
- `pyright --strict qual_v8/` 零错误
- `workflow.py` ≤ 250 行
- 所有 `typing.Any` 消除（用具体类型或 `object`）
- 单元测试：`WorkflowContext` 序列化/反序列化通过

---

### 文件 2：`workflow_context.py`（420行）→ 删除

**当前状态**：
- 行数：420
- 职责：非侵入式上下文（WorkflowContext + QualConfig + ComplianceBlockedException + 单例工厂）
- 问题：与 `workflow.py` 重复 80% 流程定义；`_get_flow_definition()` 重复定义；全局单例 `_workflow_context` 不可测试；`WorkflowContext` 命名冲突

**重构动作**：删除

**迁移策略**：
1. `ComplianceBlockedException` → 迁入 `contracts.py`
2. `QualConfig` → 合并到 `WorkflowConfig`
3. `WorkflowContext` 类 → 被 `contracts.WorkflowContext` dataclass 替代
4. `_get_flow_definition()` → 迁入 `core/supervisor.py` 作为 `FLOW_DEFINITIONS` 常量
5. 全局单例模式 → 删除（依赖注入）

**验证标准**：
- 文件删除后 `import qual_v8` 无报错
- 所有引用点迁移到新契约

---

### 文件 3：`solutions.py`（33行）→ 删除

**当前状态**：
- 行数：33
- 职责：Step/Gate 映射表 + `get_gate_for_step()`
- 问题：与 `step_gate_mapping.py` 完全重复

**重构动作**：删除

**迁移策略**：
- 所有引用迁移到 `step_gate_mapping.py`

**验证标准**：
- 文件删除后无报错

---

### 文件 4：`step_gate_mapping.py`（88行）→ 精简

**当前状态**：
- 行数：88
- 职责：Step/Gate 映射表 + 反向映射 + `print_mapping()`
- 问题：`print_mapping()` 是调试代码，不应在生产模块；`__main__` 入口多余

**重构动作**：精简

**重构后规格**：

```python
# qual_v8/step_gate_mapping.py (~50行)
# Step/Gate 映射表（纯数据 + 查表函数）

STEP_GATE_MAPPING: dict[str, int] = {
    "Step 1": 1,
    "Step 1.5": 0,
    "Step 1.6": 1,
    "Step 2": 2,
    "Step 2.5": 2,
    "Step 3": 3,
    "Step 4": 4,
    "Step 4.5": 5,
    "Step 4.5b": 5,
    "Step 4.6": 5,
    "Step 4.7": 4,
    "Step 5": 6,
    "Step 6": 7,
    "Step 7": 7,
}

GATE_STEP_MAPPING: dict[int, list[str]] = {
    0: ["Step 1.5"],
    1: ["Step 1", "Step 1.6"],
    2: ["Step 2", "Step 2.5"],
    3: ["Step 3"],
    4: ["Step 4", "Step 4.7"],
    5: ["Step 4.5", "Step 4.5b", "Step 4.6"],
    6: ["Step 5"],
    7: ["Step 6", "Step 7"],
    8: [],
}

GATE_NAMES: dict[int, str] = {
    0: "数据源验证",
    1: "类型推断 + 数据提取",
    2: "数据收集 + 参数提取",
    3: "逐章写作",
    4: "审计修复 + 深度审查",
    5: "质量增强 + 组件集成",
    6: "综合结论 + 决策章",
    7: "问题转化 + 记忆存储",
    8: "最终验证",
}


def get_gate_for_step(step_name: str) -> int:
    """根据 Step 名称获取 Gate 编号（未匹配返回 -1）"""
    for prefix, gate_num in STEP_GATE_MAPPING.items():
        if step_name.startswith(prefix):
            return gate_num
    return -1


def get_gate_name(gate_num: int) -> str:
    """获取 Gate 名称"""
    return GATE_NAMES.get(gate_num, f"Gate {gate_num}")
```

**验证标准**：
- `print_mapping()` 删除
- `__main__` 入口删除
- 行数 ≤ 50

---

### 文件 5：`mode_manager.py`（122行）→ 合并入 contracts.py

**当前状态**：
- 行数：122
- 职责：QualMode 枚举 + ModeConfig + ModeManager + 环境变量读取
- 问题：`QualMode` 已在 `contracts.py` 定义；`ModeManager` 是薄封装（3 个 `is_xxx()` 方法）；`MODE_CONFIGS` 配置表未被任何 Gate 消费

**重构动作**：合并入 `contracts.py`

**迁移策略**：
- `QualMode` → `contracts.py`（已定义）
- `get_initial_mode()` → 迁入 `contracts.py` 作为工厂函数
- `ModeManager` 类 → 删除（Gate 直接读 `WorkflowContext.qual_mode`）
- `ModeConfig` + `MODE_CONFIGS` → 删除（未被消费）

**验证标准**：
- 文件删除后无报错
- `get_initial_mode()` 在 `contracts.py` 中可调用

---

### 文件 6：`core/state_machine.py`（139行）→ 保留 + 接口规范化

**当前状态**：
- 行数：139
- 职责：GateState/WorkflowState 枚举 + 状态转换表 + StateMachine 类
- 问题：`state_history: list[dict]` 无类型；`_record_state_change()` 参数全 `str`

**重构动作**：保留 + 接口规范化

**重构后规格**：

```python
# qual_v8/core/state_machine.py (~150行)

from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class GateState(str, Enum):
    """Gate 状态"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_HUMAN = "waiting_human"
    ROLLBACK = "rollback"


class WorkflowState(str, Enum):
    """工作流状态"""
    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_VALID_GATE_TRANSITIONS: dict[GateState, frozenset[GateState]] = {
    GateState.PENDING: frozenset({GateState.RUNNING, GateState.SKIPPED}),
    GateState.RUNNING: frozenset({GateState.PASSED, GateState.FAILED, GateState.WAITING_HUMAN}),
    GateState.PASSED: frozenset(),
    GateState.FAILED: frozenset({GateState.RUNNING, GateState.ROLLBACK}),
    GateState.SKIPPED: frozenset(),
    GateState.WAITING_HUMAN: frozenset({GateState.RUNNING, GateState.FAILED}),
    GateState.ROLLBACK: frozenset({GateState.PENDING}),
}

_VALID_WORKFLOW_TRANSITIONS: dict[WorkflowState, frozenset[WorkflowState]] = {
    WorkflowState.INITIALIZED: frozenset({WorkflowState.RUNNING, WorkflowState.CANCELLED}),
    WorkflowState.RUNNING: frozenset({WorkflowState.PAUSED, WorkflowState.COMPLETED, WorkflowState.FAILED}),
    WorkflowState.PAUSED: frozenset({WorkflowState.RUNNING, WorkflowState.CANCELLED}),
    WorkflowState.COMPLETED: frozenset(),
    WorkflowState.FAILED: frozenset({WorkflowState.RUNNING}),
    WorkflowState.CANCELLED: frozenset(),
}


@dataclass(frozen=True)
class StateTransition:
    """状态转换记录（不可变）"""
    entity: str                    # "workflow" 或 "gate_{n}"
    old_state: str
    new_state: str
    timestamp: datetime


class StateMachine:
    """状态机（Gate + 工作流状态管理）"""

    def __init__(self) -> None:
        self._gate_states: dict[int, GateState] = {}
        self._workflow_state: WorkflowState = WorkflowState.INITIALIZED
        self._history: list[StateTransition] = []

    @property
    def workflow_state(self) -> WorkflowState:
        """当前工作流状态"""
        ...

    def get_gate_state(self, gate_num: int) -> GateState | None:
        """获取指定 Gate 状态"""
        ...

    def initialize_gates(self, gate_nums: tuple[int, ...]) -> None:
        """批量初始化 Gate 状态为 PENDING"""
        ...

    def transition_gate(self, gate_num: int, new_state: GateState) -> bool:
        """转换 Gate 状态（非法转换返回 False）"""
        ...

    def transition_workflow(self, new_state: WorkflowState) -> bool:
        """转换工作流状态"""
        ...

    def get_history(self) -> tuple[StateTransition, ...]:
        """获取状态变更历史（不可变副本）"""
        ...
```

**验证标准**：
- 枚举继承 `str, Enum`（可序列化）
- 转换表使用 `frozenset`（不可变）
- `state_history` 返回 `tuple`（不可变副本）
- 单元测试覆盖率 ≥ 90%

---

### 文件 7：`core/audit_logger.py`（175行）→ 保留 + 接口规范化

**当前状态**：
- 行数：175
- 职责：哈希链审计日志 + SQLite 持久化
- 问题：`details: dict[str, Any]` 无约束；`_save_to_db()` 每次新建连接

**重构动作**：保留 + 接口规范化

**重构后规格**：

```python
# qual_v8/core/audit_logger.py (~180行)

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class AuditEntry:
    """审计日志条目（不可变）"""
    log_id: str
    run_id: str
    gate_num: int | None
    action: str
    timestamp: datetime
    details: dict[str, str | int | float | bool]  # 仅允许 JSON 标量
    user_id: str | None
    previous_hash: str
    current_hash: str


class AuditLogger:
    """审计日志记录器（哈希链防篡改）"""

    def __init__(self, db_path: str | None = None) -> None:
        ...

    def log(
        self,
        run_id: str,
        gate_num: int | None,
        action: str,
        details: dict[str, str | int | float | bool],
        user_id: str | None = None,
    ) -> AuditEntry:
        """记录审计日志"""
        ...

    def verify_chain(self, run_id: str | None = None) -> bool:
        """验证哈希链完整性"""
        ...

    def get_entries(self, run_id: str | None = None) -> tuple[AuditEntry, ...]:
        """获取审计日志条目（不可变副本）"""
        ...
```

**验证标准**：
- `details` 类型约束为 `dict[str, str | int | float | bool]`
- `get_entries()` 返回 `tuple`
- SQLite 连接使用 context manager

---

### 文件 8：`core/circuit_breaker.py`（106行）→ 保留 + 接口规范化

**当前状态**：
- 行数：106
- 职责：熔断器（CLOSED/OPEN/HALF_OPEN）+ 指数退避
- 问题：`ErrorType` 与 `error_classifier.ErrorType` 重复定义

**重构动作**：保留 + 合并 ErrorType

**重构后规格**：

```python
# qual_v8/core/circuit_breaker.py (~110行)

from enum import Enum
from datetime import datetime


class CircuitState(str, Enum):
    """熔断器状态"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


# ErrorType 统一从 error_classifier 导入，此处不再重复定义
from .error_classifier import ErrorType


class CircuitBreaker:
    """熔断器（单 Gate 粒度）"""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        reset_timeout_seconds: int = 60,
        half_open_max_attempts: int = 1,
    ) -> None:
        ...

    def record_failure(self, error_type: ErrorType) -> None:
        """记录失败"""
        ...

    def record_success(self) -> None:
        """记录成功（重置计数器）"""
        ...

    def can_execute(self) -> bool:
        """检查是否允许执行"""
        ...

    def reset(self) -> None:
        """人工重置熔断器"""
        ...

    @property
    def state(self) -> CircuitState:
        """当前状态"""
        ...


def calculate_backoff(attempt: int, base_delay_seconds: int = 1, max_delay_seconds: int = 60) -> int:
    """计算指数退避延迟（含抖动）"""
    ...
```

**验证标准**：
- `ErrorType` 不再重复定义
- 参数名 `reset_timeout` → `reset_timeout_seconds`（语义明确）

---

### 文件 9：`core/error_classifier.py`（113行）→ 保留 + 接口规范化

**当前状态**：
- 行数：113
- 职责：错误码 → ErrorClassification 映射 + 异常分类
- 问题：`ERROR_CODE_MAPPING` 值为 `dict[str, Any]`；`classify_from_exception()` 缺少类型约束

**重构动作**：保留 + 接口规范化

**重构后规格**：

```python
# qual_v8/core/error_classifier.py (~120行)

from dataclasses import dataclass
from enum import Enum


class ErrorType(str, Enum):
    """错误类型（单一定义，circuit_breaker 共用）"""
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    BUSINESS = "business"


@dataclass(frozen=True)
class ErrorClassification:
    """错误分类结果（不可变）"""
    error_type: ErrorType
    retry: bool
    max_retries: int
    escalate: bool
    backoff: bool
    description: str


@dataclass(frozen=True)
class ErrorCodeSpec:
    """错误码规格（替代 dict）"""
    error_type: ErrorType
    retry: bool = False
    max_retries: int = 0
    escalate: bool = False
    backoff: bool = False


ERROR_CODE_SPECS: dict[str, ErrorCodeSpec] = {
    "NETWORK_TIMEOUT": ErrorCodeSpec(ErrorType.TRANSIENT, retry=True, max_retries=3, backoff=True),
    "HTTP_429": ErrorCodeSpec(ErrorType.TRANSIENT, retry=True, max_retries=3, backoff=True),
    "HTTP_401": ErrorCodeSpec(ErrorType.PERMANENT, escalate=True),
    "VALIDATION_FAILED": ErrorCodeSpec(ErrorType.BUSINESS, retry=True, max_retries=1),
    # ... 其余错误码
}


class ErrorClassifier:
    """错误分类器"""

    def classify(self, error_code: str, error_message: str = "") -> ErrorClassification:
        """按错误码分类"""
        ...

    def classify_from_exception(self, exception: BaseException) -> ErrorClassification:
        """从异常分类（类型明确为 BaseException）"""
        ...
```

**验证标准**：
- `ERROR_CODE_MAPPING` → `ERROR_CODE_SPECS`（用 dataclass 替代 dict）
- `classify_from_exception()` 参数类型 `BaseException`

---

### 文件 10：`core/gate_engine.py`（121行）→ 保留 + 接口规范化

**当前状态**：
- 行数：121
- 职责：GateBase 抽象基类 + GateEngine 注册/执行
- 问题：`execute()` 参数 `context: dict[str, Any]`；`check_criteria()` 同上；`GateSpec.pass_criteria: dict[str, Any]`

**重构动作**：保留 + 接口规范化

**重构后规格**：

```python
# qual_v8/core/gate_engine.py (~130行)

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class GateResult:
    """Gate 执行结果（不可变）"""
    gate_num: int
    passed: bool
    score: float
    details: dict[str, str | int | float | bool]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    execution_time_seconds: float
    timestamp: datetime


@dataclass(frozen=True)
class PassCriterion:
    """通过标准"""
    name: str
    criterion_type: str        # "condition" | "quantitative"
    condition: str | None      # 条件名（type=condition 时）
    metric: str | None         # 指标名（type=quantitative 时）
    threshold: float | None    # 阈值（type=quantitative 时）


@dataclass(frozen=True)
class GateSpec:
    """Gate 规格（不可变）"""
    gate_num: int
    name: str
    description: str
    prerequisites: tuple[int, ...]
    timeout_seconds: int
    max_retries: int
    pass_criteria: tuple[PassCriterion, ...]


class GateBase(ABC):
    """Gate 抽象基类"""

    def __init__(self, spec: GateSpec) -> None:
        self._spec = spec
        self._retry_count: int = 0

    @property
    def spec(self) -> GateSpec:
        """Gate 规格"""
        ...

    @abstractmethod
    def execute(self, context: dict[str, object]) -> GateResult:
        """执行 Gate（子类实现）"""
        ...

    @abstractmethod
    def check_criteria(self, context: dict[str, object]) -> bool:
        """检查通过标准（子类实现）"""
        ...

    def can_retry(self) -> bool:
        """是否可重试"""
        ...

    def increment_retry(self) -> None:
        """增加重试计数"""
        ...


class GateEngine:
    """Gate 引擎（注册 + 执行）"""

    def __init__(self) -> None:
        self._gates: dict[int, GateBase] = {}
        self._results: dict[int, GateResult] = {}

    def register_gate(self, gate: GateBase) -> None:
        """注册 Gate"""
        ...

    def execute_gate(self, gate_num: int, context: dict[str, object]) -> GateResult:
        """执行 Gate（含前置条件检查）"""
        ...

    def get_result(self, gate_num: int) -> GateResult | None:
        """获取 Gate 结果"""
        ...
```

**验证标准**：
- `context` 类型从 `dict[str, Any]` → `dict[str, object]`
- `errors`/`warnings` 返回 `tuple`（不可变）
- `GateSpec.pass_criteria` 使用 `tuple[PassCriterion, ...]`

---

### 文件 11：`core/supervisor.py`（213行）→ 保留 + 精简

**当前状态**：
- 行数：213
- 职责：FlowComplianceChecker（5 类检查：前置/执行/通过/失败/人工）
- 问题：`execution_log: dict[str, Any]` 无契约；`_check_failure_handling()` 和 `_check_human_intervention()` 从未被 workflow.py 调用（dead path）

**重构动作**：保留 + 精简

**重构后规格**：

```python
# qual_v8/core/supervisor.py (~150行)

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ComplianceCheck:
    """单项合规检查结果"""
    name: str
    category: str    # "precondition" | "execution" | "criteria"
    passed: bool
    message: str


@dataclass(frozen=True)
class ComplianceResult:
    """合规检查结果"""
    gate_num: int
    passed: bool
    checks: tuple[ComplianceCheck, ...]
    failed_checks: tuple[ComplianceCheck, ...]
    timestamp: datetime


# 流程定义（单一事实来源，从 workflow_context.py 合并）
FLOW_DEFINITIONS: dict[str, dict[str, object]] = {
    "gate_0": {
        "name": "数据源验证",
        "preconditions": [],
        "execution_steps": [
            {"name": "财报获取", "order": 1, "required": True},
            {"name": "Wind数据获取", "order": 2, "required": True},
        ],
        "pass_criteria": [
            {"name": "财报文件存在", "type": "condition", "condition": "filing_exists"},
            {"name": "Wind字段覆盖率", "type": "quantitative", "metric": "wind_coverage", "threshold": 0.95},
        ],
    },
    # ... gate_1 ~ gate_8
}


class FlowComplianceChecker:
    """流程合规性检查器"""

    def __init__(self, flow_definitions: dict[str, dict[str, object]] | None = None) -> None:
        self._definitions = flow_definitions or FLOW_DEFINITIONS

    def check_gate(self, gate_num: int, execution_log: dict[str, object]) -> ComplianceResult:
        """检查单个 Gate 合规性"""
        ...
```

**验证标准**：
- `_check_failure_handling()` 和 `_check_human_intervention()` 删除（dead path）
- `FLOW_DEFINITIONS` 作为模块级常量（单一事实来源）
- 行数 ≤ 150

---

### 文件 12：`gates/gate0.py`（210行）→ 保留 + 接口规范化

**当前状态**：
- 行数：210
- 职责：Gate0 数据源验证（财报+Wind+覆盖率+类型+时间范围）
- 问题：`context: dict[str, Any]`；`_validate_data()` 返回 `dict[str, Any]`；`DataSourceConfig` 硬编码默认值

**重构动作**：保留 + 接口规范化

**重构后规格**：

```python
# qual_v8/gates/gate0.py (~200行)

from dataclasses import dataclass


@dataclass(frozen=True)
class DataSourceConfig:
    """数据源配置（不可变）"""
    primary_source: str = "wind_api"
    required_fields: tuple[str, ...] = (
        "营业收入", "归母净利润", "经营活动现金流量净额", "总资产",
    )
    min_coverage: float = 0.95
    timeout_seconds: int = 30
    max_retries: int = 3


@dataclass(frozen=True)
class ValidationOutcome:
    """验证结果（替代 dict）"""
    passed: bool
    errors: tuple[str, ...]
    coverage: float
    missing_fields: tuple[str, ...]
    has_3y_range: bool


class Gate0DataSourceValidation(GateBase):
    """Gate 0: 数据源验证"""

    def execute(self, context: dict[str, object]) -> GateResult:
        """执行数据源验证"""
        ...

    def check_criteria(self, context: dict[str, object]) -> bool:
        """检查通过标准"""
        ...
```

**验证标准**：
- 内部方法返回 `ValidationOutcome`（替代 `dict`）
- `DataSourceConfig` 使用 `tuple` 替代 `list`

---

### 文件 13-20：`gates/gate1.py` ~ `gates/gate8.py` → 保留 + 接口规范化

**通用重构模式**（适用于所有 Gate）：

1. **消除 `typing.Any`**：
   - `context: dict[str, Any]` → `context: dict[str, object]`
   - 内部方法返回值用 `dataclass` 替代 `dict[str, Any]`

2. **消除魔法数字**：
   - `gate8.py` 的 `50*1024`, `500*1024`, `12000` → 提取为常量
   - `gate6.py` 的 `1000`, `500` 字数阈值 → 提取为常量

3. **消除无类型参数**：
   - 所有内部方法添加类型注解

4. **添加中文 docstring**：
   - 每个公开方法必须有中文 docstring

**各 Gate 特殊问题**：

| Gate | 行数 | 特殊问题 | 重构动作 |
|------|------|---------|---------|
| gate1 | 358 | `_FACT_FIELD_MAP` 硬编码；`_facts_to_dict()` 是桥接函数 | 保留，规范化 |
| gate2 | 235 | `DCFParams` dataclass 已有；回退计算逻辑冗长 | 精简回退逻辑 |
| gate3 | 264 | `_generate_chapters()` 依赖 v2 workflow 函数 | 保留，规范化 |
| gate4 | 387 | `LOGIC_CONTRADICTION_PATTERNS` + `RISK_DISCLOSURE_CHECKLIST` 硬编码 | 提取为常量模块 |
| gate5 | 265 | `_calculate_valuation()` 内含简化 DCF 计算 | 提取为独立函数 |
| gate6 | 295 | `RATING_VALUATION_MAPPING` 硬编码；`_extract_rating()` 正则逻辑 | 提取为常量 |
| gate7 | 194 | `_collect_review_issues()` 从 context 收集（脆弱） | 保留，规范化 |
| gate8 | 558 | 最长 Gate；`_advc_rescue_sweep()` + `_run_redteam_review()` 混入 | 拆分子函数 |

**gate8.py 特殊拆分**：

```python
# qual_v8/gates/gate8.py (重构后 ~350行)

# 魔法数字常量
_MIN_REPORT_SIZE_BYTES = 50 * 1024      # 50KB
_MAX_REPORT_SIZE_BYTES = 500 * 1024     # 500KB
_REDATEAM_CHUNK_THRESHOLD = 12000       # 字符数


class Gate8FinalValidation(GateBase):
    """Gate 8: 最终验证"""

    def execute(self, context: dict[str, object]) -> GateResult:
        ...

    def _run_advc_rescue_sweep(self, context: dict[str, object]) -> AdvcSweepResult:
        """ADVC 组装闸门救援 sweep"""
        ...

    def _check_critical_issues(self, context: dict[str, object]) -> CriticalCheckResult:
        """检查 Critical 问题（数字校验 + 模板指纹 + 结构校验）"""
        ...

    def _run_redteam_review(self, context: dict[str, object]) -> RedteamResult:
        """红队审查层"""
        ...
```

---

### 文件 21：`data_anchor.py`（489行）→ 保留 + 接口规范化

**当前状态**：
- 行数：489
- 职责：DataAnchor（跨章数据同步）+ CrossChapterValidator + get_data_anchor() 工厂 + validate_fiscal_references()
- 问题：`extract_data_spans()` 返回 `list[dict]`；`_anchor_cache` 全局可变状态；`validate_fiscal_references()` 是独立函数但逻辑与 CrossChapterValidator 重叠

**重构动作**：保留 + 接口规范化

**重构后规格**：

```python
# qual_v8/data_anchor.py (~500行)

from dataclasses import dataclass


@dataclass(frozen=True)
class DataPoint:
    """数据点（含财年维度）"""
    key: str
    value: float
    unit: str
    source: str
    timestamp: str
    fiscal_year: int | None


@dataclass(frozen=True)
class DataSpan:
    """数据 span（替代 dict）"""
    start: int
    end: int
    metric_key: str
    metric_name: str
    value: float
    unit: str
    text: str


@dataclass(frozen=True)
class AttributionResult:
    """财年归因结果"""
    fiscal_year: int | None
    matched_value: float | None
    is_latest: bool
    is_historical: bool


class DataAnchor:
    """数据锚点（唯一数据源，跨章数据同步）"""

    def __init__(self) -> None:
        self._anchors: dict[str, list[DataPoint]] = {}

    def set_anchor(self, key: str, value: float, unit: str = "亿元",
                   source: str = "Wind", fiscal_year: int | None = None) -> None:
        """设置数据锚点（同 key 多财年追加）"""
        ...

    def get_anchor(self, key: str, fiscal_year: int | None = None) -> float | None:
        """获取数据锚点值"""
        ...

    def get_all_anchors(self) -> dict[str, tuple[DataPoint, ...]]:
        """获取所有锚点（不可变副本）"""
        ...

    def get_latest_fiscal_year(self) -> int | None:
        """获取最新财年"""
        ...

    def get_metric_points(self, metric: str) -> tuple[DataPoint, ...]:
        """获取某指标全部财年锚点（按财年升序）"""
        ...

    def attribute_value(self, metric: str, value: float,
                        tolerance: float = 0.01) -> tuple[int | None, float | None]:
        """财年归因"""
        ...

    def attribute_text_value(self, metric: str, value: float,
                             tolerance: float = 0.01) -> AttributionResult:
        """文本数值归因"""
        ...

    def extract_data_spans(self, content: str) -> tuple[DataSpan, ...]:
        """逐出现值提取（返回 tuple 替代 list[dict]）"""
        ...

    def validate_chapter_any_fy(self, chapter_num: int, chapter_content: str) -> tuple[str, ...]:
        """验证章节数据（命中任一财年即通过）"""
        ...

    def init_from_wind_data(self, wind_data: dict[str, object]) -> None:
        """从 Wind 数据初始化锚点"""
        ...


class CrossChapterValidator:
    """跨章节数据验证器"""

    def __init__(self, data_anchor: DataAnchor) -> None:
        self._anchor = data_anchor

    def validate_all_chapters(self, chapters: dict[int, str]) -> CrossChapterResult:
        """验证所有章节数据一致性"""
        ...

    def fix_all_chapters(self, chapters: dict[int, str]) -> tuple[dict[int, str], tuple[str, ...]]:
        """修复所有章节数据"""
        ...


@dataclass(frozen=True)
class CrossChapterResult:
    """跨章验证结果"""
    passed: bool
    errors: tuple[str, ...]
    error_count: int


# 锚点工厂（替代全局可变 _anchor_cache）
def get_data_anchor(wind_data: dict[str, object]) -> DataAnchor:
    """按 wind_data 内容缓存 DataAnchor（只读共享）"""
    ...
```

**验证标准**：
- `extract_data_spans()` 返回 `tuple[DataSpan, ...]`（替代 `list[dict]`）
- `get_all_anchors()` 返回 `dict[str, tuple[DataPoint, ...]]`
- `validate_chapter_any_fy()` 返回 `tuple[str, ...]`

---

### 文件 22：`numeric_binder.py`（456行）→ 保留 + 接口规范化

**当前状态**：
- 行数：456
- 职责：PGNB（占位符回填 + 日期语义绑定 + 裸数字绑定 + 语义错配检测）
- 问题：`DERIVED_METRICS` 值为 `dict`；`ops_data: dict | None` 无约束；`_METRIC_NUM_RE` 正则硬编码

**重构动作**：保留 + 接口规范化

**重构后规格**：

```python
# qual_v8/numeric_binder.py (~460行)

from dataclasses import dataclass


@dataclass(frozen=True)
class DerivedMetricSpec:
    """派生指标规格"""
    formula: str
    deps: tuple[str, ...]
    available: bool


DERIVED_METRICS: dict[str, DerivedMetricSpec] = {
    "毛利率": DerivedMetricSpec("毛利/营收", (), False),
    "净利率": DerivedMetricSpec("归母净利润/营业收入", ("归母净利润", "营业收入"), True),
    # ...
}


@dataclass(frozen=True)
class BindResult:
    """回填结果"""
    content: str
    unresolved_placeholders: tuple[str, ...]


@dataclass(frozen=True)
class DateBindResult:
    """日期绑定结果"""
    content: str
    fixes: tuple[str, ...]


def bind_placeholders(
    content: str,
    anchor: DataAnchor,
    chapter_num: int,
    fiscal_year: int | None = None,
    ops_data: dict[str, dict[str, str | float]] | None = None,
) -> BindResult:
    """回填章节占位符"""
    ...


def bind_fuzzy_dates(
    content: str,
    wind_data: dict[str, object],
    chapter_num: int,
) -> DateBindResult:
    """日期语义程序绑定"""
    ...


def bind_bare_numbers(
    content: str,
    anchor: DataAnchor,
    chapter_num: int,
) -> BindResult:
    """裸数字程序绑定"""
    ...


def validate_bare_numbers(
    content: str,
    anchor: DataAnchor,
    chapter_num: int,
) -> tuple[str, ...]:
    """检查裸财务数字幻觉"""
    ...


def validate_placeholder_semantics(content: str) -> tuple[str, ...]:
    """检测占位符语义错配"""
    ...
```

**验证标准**：
- `DERIVED_METRICS` 值类型从 `dict` → `DerivedMetricSpec`
- 所有返回值使用 `dataclass` 或 `tuple`

---

### 文件 23：`anchor_repair.py`（258行）→ 保留 + 接口规范化

**当前状态**：
- 行数：258
- 职责：ADVC 层1（T1/T2/T3 确定性数值修复 + 全章 sweep）
- 问题：`repair_chapter_values()` 参数 `anchor` 无类型；`_format_value()` 内部函数

**重构动作**：保留 + 接口规范化

**重构后规格**：

```python
# qual_v8/anchor_repair.py (~260行)

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RepairFix:
    """一次确定性修复（审计记录）"""
    chapter: int
    metric: str
    metric_key: str
    span_start: int
    span_end: int
    old_value: float
    new_value: float
    fiscal_year: int | None
    kind: str          # "multiply10" | "divide10" | "prefix_drop" | "digit_typo"
    confidence: str    # "high" (T1) | "low" (T2)


@dataclass(frozen=True)
class UnresolvedValue:
    """T3 只标注项"""
    chapter: int
    metric: str
    metric_key: str
    value: float
    reason: str        # "no_signature" | "ambiguous" | "conflict" | "digit_typo_hint"
    detail: str


@dataclass
class ChapterRepairResult:
    """单章修复结果"""
    content: str
    fixes: tuple[RepairFix, ...] = ()
    unresolved: tuple[UnresolvedValue, ...] = ()
    hints: tuple[UnresolvedValue, ...] = ()


def repair_chapter_values(
    chapter_num: int,
    content: str,
    anchor: DataAnchor,
    *,
    enable_t2: bool = False,
) -> ChapterRepairResult:
    """单章确定性数值修复"""
    ...


def sweep_all_chapters(
    chapters: dict[int, str],
    anchor: DataAnchor,
    *,
    enable_t2: bool = False,
) -> tuple[dict[int, str], tuple[RepairFix, ...], tuple[UnresolvedValue, ...], tuple[UnresolvedValue, ...]]:
    """全章确定性清洗"""
    ...
```

**验证标准**：
- `RepairFix` 使用 `span_start`/`span_end` 替代 `tuple[int, int]`
- 返回值使用 `tuple` 替代 `list`

---

### 文件 24：`adapters.py`（148行）→ 保留 + 精简

**当前状态**：
- 行数：148
- 职责：v2-v7 组件适配层（build_data_context + wind_coverage + has_3y_range + get_latest_wind_value + industry_for + extract_rating_from_chapters）
- 问题：`industry_for()` 硬编码行业映射；`extract_rating_from_chapters()` 与 `gate6._extract_rating()` 重复

**重构动作**：保留 + 精简

**重构后规格**：

```python
# qual_v8/adapters.py (~120行)

# 行业映射表（替代硬编码 if-elif）
INDUSTRY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "新能源汽车": ("小鹏", "蔚来", "理想", "比亚迪"),
    "科技": ("腾讯", "阿里", "百度", "字节"),
    "消费": ("美团", "京东", "拼多多", "淘宝"),
    "数字内容": ("阅文", "中文在线", "掌阅", "晋江"),
    "金融": ("招行", "工行", "建行", "平安"),
}

DEFAULT_INDUSTRY = "综合"


def industry_for(company_name: str) -> str:
    """从公司名推导行业"""
    ...


def build_data_context(
    ticker: str,
    company_name: str,
    market: str,
    wind_data: dict[str, object] | None = None,
    filing_data: dict[str, object] | None = None,
) -> object:
    """构造 DataContext"""
    ...


def wind_coverage(wind_data: dict[str, object] | None) -> tuple[float, tuple[str, ...]]:
    """Wind 数据 canonical 键覆盖率 + 缺失字段"""
    ...


def has_3y_range(wind_data: dict[str, object] | None) -> bool:
    """检查 Wind 数据是否覆盖 3 年"""
    ...


def get_latest_wind_value(wind_data: dict[str, object] | None, canonical: str) -> float | None:
    """获取某指标最新财年值"""
    ...
```

**验证标准**：
- `extract_rating_from_chapters()` 删除（与 gate6 重复，gate6 保留）
- `industry_for()` 使用查表替代 if-elif
- 行数 ≤ 120

---

### 文件 25：`monitoring/alerts.py`（170行）→ 保留 + 接口规范化

**当前状态**：
- 行数：170
- 职责：AlertManager + MetricsCollector + 告警规则
- 问题：`alert_rules` 使用 lambda（不可序列化）；`Metrics` 字段无默认值约束

**重构动作**：保留 + 接口规范化

**重构后规格**：

```python
# qual_v8/monitoring/alerts.py (~170行)

from dataclasses import dataclass, field
from enum import Enum


class AlertLevel(str, Enum):
    """告警级别"""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Alert:
    """告警"""
    name: str
    level: AlertLevel
    message: str
    timestamp: str
    details: dict[str, str | int | float] = field(default_factory=dict)


@dataclass
class Metrics:
    """监控指标"""
    gate_pass_rate: dict[int, float] = field(default_factory=dict)
    gate_avg_duration_seconds: dict[int, float] = field(default_factory=dict)
    gate_failure_count: dict[int, int] = field(default_factory=dict)
    circuit_break_count: int = 0
    sla_violation_count: int = 0


@dataclass(frozen=True)
class AlertRule:
    """告警规则（替代 lambda）"""
    name: str
    level: AlertLevel
    message: str
    # 条件字段
    min_pass_rate: float | None = None
    max_failure_count: int | None = None
    max_sla_violations: int | None = None
    max_api_latency_ms: float | None = None


ALERT_RULES: tuple[AlertRule, ...] = (
    AlertRule("Gate通过率过低", AlertLevel.WARNING, "Gate通过率低于80%", min_pass_rate=0.80),
    AlertRule("Gate连续失败", AlertLevel.CRITICAL, "Gate连续失败3次以上", max_failure_count=3),
    AlertRule("人工SLA违规", AlertLevel.WARNING, "人工SLA违规次数过多", max_sla_violations=5),
    AlertRule("熔断器打开", AlertLevel.CRITICAL, "熔断器已打开"),
    AlertRule("API延迟过高", AlertLevel.WARNING, "API延迟超过1000ms", max_api_latency_ms=1000),
)


class AlertManager:
    """告警管理器"""

    def __init__(self) -> None:
        self._alerts: list[Alert] = []
        self._metrics = Metrics()

    def check_alerts(self, metrics: Metrics) -> tuple[Alert, ...]:
        """检查告警规则，返回触发的告警"""
        ...

    def get_alerts(self, level: AlertLevel | None = None) -> tuple[Alert, ...]:
        """获取告警"""
        ...


class MetricsCollector:
    """指标收集器"""

    def record_gate_result(self, gate_num: int, result: dict[str, object]) -> None:
        """记录 Gate 结果"""
        ...

    def record_execution_time(self, gate_num: int, duration_seconds: float) -> None:
        """记录执行时间"""
        ...

    def get_metrics(self) -> Metrics:
        """获取指标"""
        ...
```

**验证标准**：
- `alert_rules` 从 lambda → `AlertRule` dataclass（可序列化）
- `get_alerts()` 返回 `tuple`

---

### 文件 26：`security/auth.py`（162行）→ 删除

**当前状态**：
- 行数：162
- 职责：RBAC 权限矩阵 + DataMasker + KeyManager
- 问题：**整个模块从未被任何 Gate 或 workflow 调用**（dead code）；`Permission.SKIP` 未在枚举中定义但被引用

**重构动作**：删除

**迁移策略**：
- 确认无任何 import 引用后直接删除
- 若未来需要 RBAC，从 dayu-agent 移植成熟实现

**验证标准**：
- 文件删除后 `grep -r "security.auth" qual_v8/` 无结果

---

### 文件 27：`tests/test_core.py`（324行）→ 扩充

**当前状态**：
- 行数：324
- 职责：核心组件单元测试
- 问题：覆盖率不足（仅测试 state_machine/audit_logger/circuit_breaker/error_classifier/gate0）；Gate1-8 无测试；`TestB1ChapterCoverage` 使用 `mock.patch` 路径错误（`finance.workflow` → `tools.finance.workflow`）

**重构动作**：扩充

**重构后规格**：

```python
# qual_v8/tests/test_core.py (~500行)
# 目标：单文件覆盖率 ≥ 80%

import unittest
from unittest import mock


class TestStateMachine(unittest.TestCase):
    """状态机测试（已有，扩充边界用例）"""
    ...


class TestAuditLogger(unittest.TestCase):
    """审计日志测试（已有）"""
    ...


class TestCircuitBreaker(unittest.TestCase):
    """熔断器测试（已有）"""
    ...


class TestErrorClassifier(unittest.TestCase):
    """错误分类器测试（已有）"""
    ...


class TestGateEngine(unittest.TestCase):
    """Gate 引擎测试（新增）"""
    def test_register_and_execute(self) -> None: ...
    def test_prerequisite_check(self) -> None: ...


class TestGate0DataSourceValidation(unittest.TestCase):
    """Gate0 测试（扩充）"""
    def test_execute_with_valid_data(self) -> None: ...
    def test_execute_with_missing_filing(self) -> None: ...
    def test_check_criteria(self) -> None: ...


class TestGate1TypeInference(unittest.TestCase):
    """Gate1 测试（新增）"""
    ...


class TestGate2DataCollection(unittest.TestCase):
    """Gate2 测试（新增）"""
    ...


class TestDataAnchor(unittest.TestCase):
    """DataAnchor 测试（新增）"""
    def test_set_and_get_anchor(self) -> None: ...
    def test_multi_fiscal_year(self) -> None: ...
    def test_validate_chapter_any_fy(self) -> None: ...


class TestNumericBinder(unittest.TestCase):
    """NumericBinder 测试（新增）"""
    def test_bind_placeholders(self) -> None: ...
    def test_bind_fuzzy_dates(self) -> None: ...
    def test_validate_bare_numbers(self) -> None: ...


class TestAnchorRepair(unittest.TestCase):
    """ADVC 测试（新增）"""
    def test_repair_chapter_values(self) -> None: ...
    def test_self_verification(self) -> None: ...
```

**验证标准**：
- 单文件覆盖率 ≥ 80%
- 每个 Gate 至少 3 个测试用例
- DataAnchor 至少 5 个测试用例

---

## 三、重构优先级排序

| 优先级 | 文件 | 动作 | 原因 |
|--------|------|------|------|
| P0 | `workflow_context.py` | 删除 | 与 workflow.py 80% 重复，维护负担 |
| P0 | `solutions.py` | 删除 | 与 step_gate_mapping.py 完全重复 |
| P0 | `security/auth.py` | 删除 | dead code，从未被调用 |
| P1 | `workflow.py` | 拆分 | God Object，需提取 contracts/retry_engine/report_assembler |
| P1 | `contracts.py` | 新建 | 所有 dataclass/Enum 集中定义 |
| P1 | `core/state_machine.py` | 规范化 | 核心组件，接口需先稳定 |
| P1 | `core/gate_engine.py` | 规范化 | GateBase 接口影响所有 Gate |
| P2 | `gates/gate0-8.py` | 规范化 | 统一消除 Any/魔法数字/无类型参数 |
| P2 | `data_anchor.py` | 规范化 | 核心数据层，返回值需类型化 |
| P2 | `numeric_binder.py` | 规范化 | PGNB 核心，DERIVED_METRICS 需类型化 |
| P2 | `anchor_repair.py` | 规范化 | ADVC 核心，span 需类型化 |
| P3 | `adapters.py` | 精简 | 删除重复函数 |
| P3 | `monitoring/alerts.py` | 规范化 | lambda → AlertRule |
| P3 | `core/supervisor.py` | 精简 | 删除 dead path |
| P3 | `step_gate_mapping.py` | 精简 | 删除调试代码 |
| P4 | `tests/test_core.py` | 扩充 | 覆盖率 ≥ 80% |

---

## 四、迁移检查清单

### Phase 1：清理（1天）
- [ ] 删除 `workflow_context.py`
- [ ] 删除 `solutions.py`
- [ ] 删除 `security/auth.py`
- [ ] 确认所有 import 无报错

### Phase 2：契约层（2天）
- [ ] 创建 `contracts.py`（所有 dataclass/Enum）
- [ ] 创建 `retry_engine.py`
- [ ] 创建 `report_assembler.py`
- [ ] 重写 `workflow.py` 使用新契约

### Phase 3：核心组件规范化（2天）
- [ ] 规范化 `core/state_machine.py`
- [ ] 规范化 `core/gate_engine.py`
- [ ] 规范化 `core/audit_logger.py`
- [ ] 规范化 `core/circuit_breaker.py`
- [ ] 规范化 `core/error_classifier.py`
- [ ] 精简 `core/supervisor.py`

### Phase 4：Gate 规范化（3天）
- [ ] 规范化 gate0-8.py（统一消除 Any/魔法数字）
- [ ] 规范化 `data_anchor.py`
- [ ] 规范化 `numeric_binder.py`
- [ ] 规范化 `anchor_repair.py`
- [ ] 精简 `adapters.py`
- [ ] 规范化 `monitoring/alerts.py`
- [ ] 精简 `step_gate_mapping.py`

### Phase 5：测试（2天）
- [ ] 扩充 `tests/test_core.py` 至覆盖率 ≥ 80%
- [ ] `pyright --strict qual_v8/` 零错误
- [ ] 全量回归测试通过

---

## 五、验收标准

1. **类型安全**：`pyright --strict` 零错误
2. **无 Any**：`grep -r "typing.Any" qual_v8/` 返回空
3. **无魔法数字**：所有阈值/常量提取为命名常量
4. **无 God Object**：`workflow.py` ≤ 250 行
5. **无重复代码**：`solutions.py`/`workflow_context.py` 已删除
6. **无 dead code**：`security/auth.py` 已删除
7. **测试覆盖**：`tests/test_core.py` 覆盖率 ≥ 80%
8. **文档完整**：所有公开方法有中文 docstring
9. **向后兼容**：`from qual_v8 import QualWorkflow, WorkflowConfig` 仍可用
