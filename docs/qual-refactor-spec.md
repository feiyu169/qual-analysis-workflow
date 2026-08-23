# Qual 重构规格书（对照 dayu-agent）

**日期**：2026-08-22  
**范本**：[noho/dayu-agent](https://github.com/noho/dayu-agent)（已 clone 到 .pip-tmp/dayu-agent/）  
**目标**：以 dayu 的 contracts 层 + 四层边界 + AGENTS.md 编码约束为范本，重构 qual v8

---

## 一、总体对照表

| Dayu 模块 | 行数 | 功能 | Qual 对应 | Qual 行数 | 重构动作 |
|-----------|------|------|-----------|-----------|---------|
| `contracts/` | 5,373 | 强类型跨层契约 | **无** | 0 | **新建** |
| `host/` | 16,915 | 托管执行层（session/run/并发/取消） | `qual_v8/core/` | 895 | **新建** |
| `engine/` | 11,960 | Agent 执行器（tool loop/trace） | `qual_v8/gates/` | 2,791 | **重构** |
| `engine/tools/` | 6,831 | 工具注册/执行 | `qual_v8/numeric_binder.py` 等 | ~1,000 | **合并** |
| `services/` | 3,749 | 业务语义层 | `workflow.py` | 3,446 | **拆分** |
| `services/internal/write_pipeline/` | 13,622 | 报告写作流水线 | `quality/review_repair_loop.py` | 841 | **重构** |
| `fins/` | 15,867 | 财报管线（下载/解析/存储） | `fact_extractor.py` + `filing_service.py` | ~2,500 | **保留** |
| `fins/storage/` | 6,067 | 仓储协议 | **无**（直接 dict） | 0 | **新建** |
| `prompting/` | 1,591 | Prompt 渲染 | `workflow.py` 内嵌 | ~300 | **抽取** |
| `contracts/agent_types.py` | 530 | AgentMessage TypedDict | **无**（dict 传递） | 0 | **新建** |
| `contracts/cancellation.py` | 332 | CancellationToken | **无** | 0 | **新建** |
| `contracts/run.py` | 174 | RunRecord 7 态状态机 | `qual_v8/core/state_machine.py` | ~150 | **重构** |
| `contracts/session.py` | 82 | SessionRecord 4 态 | **无** | 0 | **新建** |
| `contracts/events.py` | 109 | AppEvent/AppResult | **无** | 0 | **新建** |
| `contracts/protocols.py` | 237 | ToolExecutor/ToolTraceRecorder | **无** | 0 | **新建** |

---

## 二、新建 `qual/contracts/` 层（P0，1 周）

### 2.1 文件清单

```
tools/finance/qual/contracts/
├── __init__.py              — lazy import + _EXPORT_MAP（参照 dayu/contracts/__init__.py）
├── data_context.py          — DataContextContract（替代 dict[str, Any] context）
├── gate_contract.py         — GateContract（Gate 间传递的执行契约）
├── wind_data.py             — WindDataContract（Wind 数据强类型）
├── filing_data.py           — FilingDataContract（财报数据强类型）
├── facts.py                 — FactsContract（事实表强类型）
├── chapter.py               — ChapterContract（章节数据强类型）
├── review_result.py         — ReviewResultContract（审查结果强类型）
├── gate_state.py            — GateState 状态机（7 态，参照 dayu/contracts/run.py）
├── events.py                — QualEvent/AppResult（事件契约）
├── cancellation.py          — CancellationToken（参照 dayu/contracts/cancellation.py）
└── protocols.py             — CheckerProtocol/RepairerProtocol（检查器/修复器协议）
```

### 2.2 核心接口定义

```python
# qual/contracts/data_context.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

@dataclass(frozen=True)
class WindDataContract:
    """Wind 数据强类型契约（替代 dict[str, Any]）。
    
    Attributes:
        income: 利润表数据 {指标名: [FY2023, FY2024, FY2025]}。
        balance: 资产负债表数据。
        cashflow: 现金流量表数据。
        quote: 行情数据。
        valuation: 估值数据。
        year_labels: 财年标签列表。
    """
    income: dict[str, list[float | None]]
    balance: dict[str, list[float | None]]
    cashflow: dict[str, list[float | None]]
    quote: dict[str, float | str | None] = field(default_factory=dict)
    valuation: dict[str, float | None] = field(default_factory=dict)
    year_labels: list[int] = field(default_factory=lambda: [2023, 2024, 2025])


@dataclass(frozen=True)
class FilingDataContract:
    """财报数据强类型契约。
    
    Attributes:
        sections: 章节内容 {章节名: 内容}。
        tables: 表格数据。
        metadata: 元数据（ticker/market/fiscal_year/years/prior_years）。
    """
    sections: dict[str, str]
    tables: list[dict] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class FactsContract:
    """事实表强类型契约。
    
    Attributes:
        company_name: 公司名称。
        ticker: 股票代码。
        fiscal_year: 财年。
        revenue: 营业收入（亿元）。
        net_profit: 归母净利润（亿元）。
        operating_profit: 营业利润（亿元）。
        total_assets: 总资产（亿元）。
        operational: 运营数据。
    """
    company_name: str
    ticker: str
    fiscal_year: int
    revenue: float | None = None
    net_profit: float | None = None
    operating_profit: float | None = None
    total_assets: float | None = None
    operational: dict[str, float | None] = field(default_factory=dict)


@dataclass(frozen=True)
class DataContextContract:
    """Gate 间传递的完整数据上下文（替代 dict[str, Any]）。
    
    Attributes:
        ticker: 股票代码。
        company_name: 公司名称。
        market: 市场类型（hk/us/cn）。
        data_quality: 数据质量评级。
        wind: Wind 数据。
        filing: 财报数据。
        facts: 事实表。
        chapters: 已生成章节 {章节号: 内容}。
        facets: 类型推断结果。
    """
    ticker: str
    company_name: str
    market: str
    data_quality: str = "unknown"
    wind: WindDataContract | None = None
    filing: FilingDataContract | None = None
    facts: FactsContract | None = None
    chapters: dict[int, str] = field(default_factory=dict)
    facets: dict[str, object] = field(default_factory=dict)
```

```python
# qual/contracts/gate_contract.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

class GateState(str, Enum):
    """Gate 状态枚举（参照 dayu/contracts/run.py RunState）。
    
    状态机合法转换:
        PENDING → RUNNING → PASSED / FAILED / SKIPPED
        FAILED → RUNNING（重试）
    """
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"

# 合法状态转换表
_VALID_TRANSITIONS: dict[GateState, frozenset[GateState]] = {
    GateState.PENDING: frozenset({GateState.RUNNING, GateState.SKIPPED}),
    GateState.RUNNING: frozenset({GateState.PASSED, GateState.FAILED}),
    GateState.PASSED: frozenset(),
    GateState.FAILED: frozenset({GateState.RUNNING}),
    GateState.SKIPPED: frozenset(),
}


@dataclass(frozen=True)
class GateContract:
    """Gate 执行契约（Service → Gate 的输入）。
    
    Attributes:
        gate_num: Gate 编号（0-8）。
        gate_name: Gate 名称。
        data_context: 数据上下文。
        prerequisites: 前置 Gate 编号列表。
        max_retries: 最大重试次数。
        deadline: 墙钟截止时间（秒）。
    """
    gate_num: int
    gate_name: str
    data_context: DataContextContract
    prerequisites: tuple[int, ...] = ()
    max_retries: int = 1
    deadline: float | None = None


@dataclass(frozen=True)
class GateResultContract:
    """Gate 执行结果契约（Gate → Service 的输出）。
    
    Attributes:
        gate_num: Gate 编号。
        state: 最终状态。
        errors: 错误列表。
        warnings: 告警列表。
        issues_found: 发现的问题数。
        issues_fixed: 修复的问题数。
        remaining_issues: 未修复的问题。
        chapters: 修复后的章节（如有）。
    """
    gate_num: int
    state: GateState
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    issues_found: int = 0
    issues_fixed: int = 0
    remaining_issues: tuple[str, ...] = ()
    chapters: dict[int, str] | None = None
```

```python
# qual/contracts/protocols.py
from __future__ import annotations
from typing import Protocol, runtime_checkable

@runtime_checkable
class CheckerProtocol(Protocol):
    """检查器协议（所有检查器必须实现）。
    
    方法:
        check: 执行检查，返回问题列表。
        name: 检查器名称。
    """
    @property
    def name(self) -> str: ...
    def check(self, content: str, context: DataContextContract) -> list[str]: ...


@runtime_checkable
class RepairerProtocol(Protocol):
    """修复器协议（所有修复器必须实现）。
    
    方法:
        repair: 执行修复，返回修复后内容和修复记录。
    """
    def repair(self, content: str, issues: list[str], context: DataContextContract) -> tuple[str, list[str]]: ...
```

```python
# qual/contracts/events.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

class QualEventType(str, Enum):
    """Qual 事件类型。"""
    GATE_STARTED = "gate_started"
    GATE_PASSED = "gate_passed"
    GATE_FAILED = "gate_failed"
    CHAPTER_GENERATED = "chapter_generated"
    CHAPTER_REPAIRED = "chapter_repaired"
    CHECKER_WARNING = "checker_warning"
    REPAIR_APPLIED = "repair_applied"
    DONE = "done"
    ERROR = "error"

@dataclass
class QualEvent:
    """Qual 标准事件。"""
    type: QualEventType
    payload: dict[str, object] = field(default_factory=dict)
    gate_num: int | None = None
    chapter_num: int | None = None

@dataclass
class QualResult:
    """Qual 执行结果。"""
    success: bool
    chapters: dict[int, str]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    degraded: bool = False
    gate_summary: dict[int, GateResultContract] = field(default_factory=dict)
```

---

## 三、重构 `workflow.py`（P1，2 周）

### 3.1 拆分方案

```
workflow.py (3,446行) → 5 个模块:

qual/orchestrator.py    (~300行) — 编排入口
  - run_qual_analysis(ticker, company_name, market, ...) -> QualResult
  - 只做 Step 调度，不含业务逻辑
  - 用 DataContextContract 传递数据（不用 dict）

qual/chapter_generator.py (~600行) — 章节生成
  - generate_chapter(chapter_num, prompt, ctx, llm_caller) -> str
  - 包含 PGNB（bind_bare_numbers + bind_placeholders + bind_fuzzy_dates）
  - 包含 ADVC（anchor_repair）
  - 不含审查逻辑

qual/data_collector.py  (~400行) — 数据收集
  - collect_data(ticker, company_name, market, wind_data, filing_data) -> DataContextContract
  - 包含 Wind 数据处理、事实提取、DataAnchor 构建
  - 输出强类型 DataContextContract

qual/report_assembler.py (~200行) — 报告组装
  - assemble_report(chapters, ctx, output_dir) -> str
  - 包含 Gate8 终局 sweep（ADVC + PGNB + 日期绑定）
  - 包含质量标注

qual/adapters.py        (~200行) — v8 Gate 引擎适配
  - 适配 qual_v8/gates/ 的 Gate 引擎到新的 contracts 层
  - 桥接旧 Gate 接口和新 GateContract/GateResultContract
```

### 3.2 删除的检查器（从 16 个精简到 3 个）

| 检查器 | 状态 | 原因 |
|--------|------|------|
| `numeric_guard.py` | **保留** | 确定性检查（量级/空章/空壳/财年/币值） |
| `structural_check.py` | **保留** | 确定性检查（H1/小节/证据标记） |
| `cross_chapter_consistency.py` | **精简** | 只保留数据冲突检查，删除结论/时间检查 |
| `fact_checker.py` | **删除** | 已被 DataAnchor 替代（单财年假设跑三财年报告） |
| `conclusion_validator.py` | **删除** | LLM 审查响应解析太粗糙（"问题"关键词触发） |
| `depth_reviewer.py` | **删除** | LLM 审查，质量不可控 |
| `assumption_checker.py` | **删除** | LLM 审查 |
| `date_anchor_check.py` | **删除** | 已被 bind_fuzzy_dates 替代 |
| `logic_consistency_check.py` | **删除** | 与 cross_chapter 重复 |
| `data_reasonableness_check.py` | **删除** | 与 DataAnchor 重复 |
| `review_integrator.py` | **删除** | 审查整合逻辑合并到 orchestrator |
| `debate_service.py` | **删除** | 对抗辩论，LLM 质量不可控 |
| `patch_applier.py` | **精简** | 只保留确定性 patch，删除 LLM patch |
| `review_repair_loop.py` | **重构** | 从 max_rounds=3 改为单轮：生成→确定性修复→审计 |

### 3.3 审查修复循环重构

```
当前（max_rounds=3）：
  Gate3 生成 → Gate4 审查（16 检查器）→ LLM patch → 校验 → 回滚/通过 → 重复 3 轮

重构后（单轮）：
  Gate3 生成 → 确定性修复（ADVC + PGNB + bind_fuzzy_dates）→ 结构检查 → 通过/标注
```

**关键变化**：
- 删除 LLM patch 修复（`_repair_chapters` 的 LLM 调用）
- 删除 max_rounds 重试循环
- 删除单调性守卫（不再需要——没有 LLM 重写就没有回归）
- 保留确定性修复（ADVC + PGNB + bind_fuzzy_dates）
- 保留结构检查（structural_check）
- 未修复的问题 → 标注到报告（不阻断）

---

## 四、AGENTS.md 编码约束（P0，立即）

新建 `tools/finance/qual/AGENTS.md`：

```markdown
# Qual 编码约束（参照 dayu-agent AGENTS.md）

## 类型约束
- 禁止 `dict[str, Any]` 作为跨层传递类型（用 frozen dataclass）
- 禁止无类型参数和无类型返回值
- pyright 强制通过

## 结构约束
- 禁止 God object/function（单文件 ≤500 行，单函数 ≤50 行）
- 禁止兼容性代码（re-export、wrapper/facade）
- 禁止魔法数字/字符串（用 Enum 或常量）

## 测试约束
- 单文件测试覆盖率 ≥80%
- 关键路径必须有端到端测试（不依赖 mock）
- 测试跟着实现迁移，不为旧测试保留兼容逻辑

## 文档约束
- 函数必须提供中文 docstring（参数、返回值、异常）
- 类与模块提供中文概览 docstring
```

---

## 五、实施顺序

| 阶段 | 时间 | 内容 | 交付物 |
|------|------|------|--------|
| **P0** | 1 周 | contracts 层 + AGENTS.md | `qual/contracts/` 12 文件 |
| **P1** | 1 周 | 精简检查器（16→3）+ 审查循环改为单轮 | 删除 10 个检查器文件 |
| **P2** | 2 周 | workflow.py 拆分（3,446→5 模块） | `qual/orchestrator.py` 等 5 文件 |
| **P3** | 2 周 | Gate 引擎重构（contracts 驱动） | `qual_v8/gates/` 重构 |
| **P4** | 1 周 | 章节并行生成 | `qual/chapter_generator.py` 并行版 |
| **P5** | 2 周 | 独立审计模型 | `qual/auditor.py` |

---

## 六、验证标准

| 维度 | 标准 |
|------|------|
| **类型安全** | pyright 零错误 |
| **测试覆盖** | 456 passed（现有）+ 新 contracts 测试 |
| **全流程** | 小鹏 9868.HK 3 年年报 ≤20 分钟产出完整报告 |
| **Gate4 通过率** | ≥70%（当前 0%） |
| **代码量** | 从 57,000 行降到 ~35,000 行 |

---

## 七、架构专家补充：四层架构详细设计

### 7.1 四层架构映射

```
Qual 当前：workflow.py (3,446行单体) → Gate0-8 串行
Qual 重构后：UI → Service → Host → Agent（参照 dayu 四层）
```

| 层 | Qual 职责 | 对照 dayu |
|----|----------|-----------|
| **UI** | CLI 入口 + 结果渲染 | `dayu/cli/` |
| **Service** | 业务语义：ticker 解析、数据收集决策、章节策略 | `dayu/services/` |
| **Host** | 托管执行：Gate 生命周期、并发、取消、事件 | `dayu/host/` |
| **Agent** | 消息执行：LLM 调用、工具执行、PGNB | `dayu/engine/` |

### 7.2 Host 层能力（精简版）

dayu 的 Host 有九项能力，qual 只需要四项：

| 能力 | qual 需要 | 实现方式 |
|------|----------|---------|
| Gate 生命周期 | ✅ | GateState 5 态状态机 |
| 并发治理 | ✅ | 章节并行生成时的 lane 机制 |
| 事件发布 | ✅ | QualEvent 流式输出 |
| Timeout 控制 | ✅ | deadline watcher |

### 7.3 Gate4 死循环根治

**重构方案**：
1. 删除 LLM patch 修复 + max_rounds 重试循环
2. 改为**单轮确定性修复**：ADVC → PGNB → bind_fuzzy_dates → structural_check
3. 未修复的问题 → 标注到报告（不阻断，不重试）

**预期效果**：Gate4 通过率 0% → ≥70%

### 7.4 章节并行生成

```
批次1：[ch1, ch2, ch3]（无依赖）
批次2：[ch4, ch5, ch6]（依赖 ch1-3 摘要）
批次3：[ch7, ch8, ch9, ch10, ch11]（依赖前序章节）
```
**预期效果**：运行时间 40-60 分钟 → 15-20 分钟

---

## 八、代码专家补充：逐文件重构规格

### 8.1 删除清单（10 个检查器文件，~5,100 行）

| 文件 | 行数 | 删除原因 |
|------|------|---------|
| `fact_checker.py` | 435 | 已被 DataAnchor 替代 |
| `conclusion_validator.py` | 451 | LLM 审查解析太粗糙 |
| `depth_reviewer.py` | ~300 | LLM 审查质量不可控 |
| `assumption_checker.py` | ~300 | LLM 审查 |
| `date_anchor_check.py` | 388 | 已被 bind_fuzzy_dates 替代 |
| `logic_consistency_check.py` | 383 | 与 cross_chapter 重复 |
| `data_reasonableness_check.py` | 381 | 与 DataAnchor 重复 |
| `debate_service.py` | ~200 | LLM 质量不可控 |
| `review_integrator.py` | 875 | 合并到 orchestrator |
| `_legacy/` | 1,388 | 旧版代码 |

### 8.2 精简清单（3 个保留文件）

| 文件 | 当前 → 精简后 | 变化 |
|------|-------------|------|
| `cross_chapter_consistency.py` | 505 → ~300 | 只保留数据冲突 |
| `review_repair_loop.py` | 841 → ~200 | 删除 LLM patch/重试 |
| `patch_applier.py` | 157 → ~100 | 只保留确定性 patch |

### 8.3 重构后代码量预估

| 类别 | 当前 | 重构后 | 变化 |
|------|------|--------|------|
| qual_v8/ 核心 | 6,849 | ~5,000 | -27% |
| quality/ 检查器 | 20,034 | ~12,000 | -40% |
| workflow.py | 3,446 | 0（拆分） | -100% |
| 新 contracts/ | 0 | ~1,180 | 新增 |
| 新模块 | 0 | ~1,700 | 新增 |
| **总计** | ~30,329 | ~19,880 | **-34%** |
