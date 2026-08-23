# Qual v9 重构方案（三方会审仲裁版）

**日期**：2026-08-23  
**仲裁流程**：架构专家 + 代码专家 + 评审专家逐模块对照 dayu-agent，逐一仲裁  
**仲裁依据**：dayu-agent 6 模块全量代码审查 + 重型引擎对比 + 融合风险分析 + 风险评估

---

## 一、仲裁结果总表

| 模块 | dayu 行数 | 纳入决定 | qual 需要行数 | 理由摘要 |
|------|----------|---------|-------------|---------|
| contracts/ | 5,373 | **部分纳入** | ~1,800 | 公共类型骨架（AgentMessage/RunState/CancellationToken/AppEvent）纳入；ExecutionContract/FinsCommand/ToolsetConfig 排除 |
| host/ | 16,915 | **不纳入** | ~0 | qual 在 DSH 子代理环境运行，DSH 已有等价替代（Session/Run/并发/取消/Resume） |
| engine/ | 26,744 | **部分纳入** | ~12,000 | 核心推理循环/LLM Runner/SSE/ToolRegistry/工具信封/参数校验纳入；web/doc/processors/tools 排除 |
| services/write_pipeline/ | 13,622 | **不纳入** | ~0 | qual 的 Gate0-8 状态机是 write_pipeline 的完全替代 |
| fins/storage/ | 4,719 | **不纳入** | ~0 | qual 用 Wind MCP 直接获取数据，不需要本地仓储协议 |
| prompting/ | 1,591 | **部分纳入** | ~500 | 条件渲染 + 模板变量替换纳入；scene manifest 体系排除 |
| **合计** | **68,964** | — | **~14,300** | 排除 79.3%，qual 只需 20.7% |

---

## 二、逐模块仲裁详情

### 模块 1: contracts/（22 文件，5,373 行）

**架构专家评估**：
- 核心设计理念：frozen dataclass + Protocol + 零 dict[str, Any] 传递
- qual 需要：部分需要——公共类型定义是通用骨架

**代码专家评估**：
- 纳入：AgentMessage TypedDict（~200 行）、RunState 7 态状态机（~174 行）、CancellationToken（~121 行）、AppEvent/AppResult（~109 行）、RunnerType/ModelConfig（~192 行）、lazy import __init__.py（~154 行）
- 排除：ExecutionContract（534 行）——qual 用 GateContract 替代；agent_execution_serialization（721 行）——序列化层过重；fins.py（669 行）——qual 不需要财报领域契约；host_execution（193 行）——qual 无 Host 层；toolset_config/toolset_registrar/tool_configs（~800 行）——qual 工具集固定

**评审专家仲裁**：**部分纳入 ~1,800 行**
- 理由：contracts 层的核心价值是"强类型定义"，qual 需要这个。但 dayu 的 contracts 层包含了大量 qual 不需要的执行链契约（ExecutionContract）和财报领域契约（FinsCommand）。

---

### 模块 2: host/（28 文件，16,915 行）

**架构专家评估**：
- 核心设计理念：Session/Run/并发/事件/Timeout/Cancel/Resume/记忆/Reply 九项能力
- qual 不需要：qual 在 DSH 子代理环境中运行，DSH 已有等价替代

**代码专家评估**：
- executor.py（1,945 行）：qual 的 GateRunner 替代
- run_registry.py（572 行）：qual 的 GateState 状态机替代
- concurrency.py（335 行）：qual 单次分析，不需要并发治理
- session_registry.py（316 行）：qual 无多会话
- conversation_memory.py（1,338 行）：qual 无多轮会话
- pending_turn_store.py（1,456 行）：qual 无 Resume 需求
- reply_outbox_store.py（990 行）：qual 直接写文件

**评审专家仲裁**：**不纳入**
- 理由：qual 在 DSH 子代理环境中运行，DSH 已提供 Session/Run/并发/取消/Resume 等等价能力。dayu 的 host 层是为"独立部署的多租户系统"设计的，qual 是"嵌入式单次分析工具"，架构场景完全不同。
- **替代方案**：qual 的 GateRunner（~150 行）实现 Gate 生命周期管理，GateState（~100 行）实现状态机，两者合计 ~250 行即可覆盖 qual 需要的 host 能力。

---

### 模块 3: engine/（54 文件，26,744 行）

**架构专家评估**：
- 核心设计理念：AsyncAgent tool loop + LLM Runner + 工具注册表 + 参数校验器
- qual 需要：部分需要——工具基础设施是通用的

**代码专家评估**：
- 纳入：
  - async_agent.py（2,093 行）→ 简化版 ~800 行（保留 tool loop 状态机，去掉 compaction/continuation）
  - async_openai_runner.py（1,982 行）→ 简化版 ~600 行（保留 HTTP 调用+重试，去掉流式 SSE）
  - tool_registry.py（591 行）→ ~400 行（保留注册+参数校验+安全检查）
  - tool_result.py（341 行）→ ~250 行（统一工具结果信封）
  - argument_validator.py（545 行）→ ~400 行（JSON Schema 校验）
  - events.py（304 行）→ ~200 行（结构化事件模型）
  - protocols.py（78 行）→ ~80 行（Runner Protocol）
  - exceptions.py（285 行）→ ~200 行（异常层级）
  - tool_contracts.py（230 行）→ ~150 行（工具契约）
- 排除：
  - sse_parser.py（990 行）：qual 用同步 JSON
  - context_budget.py（444 行）：Gate 模型天然限制上下文
  - duplicate_call_guard.py（269 行）：Gate 模型不需要
  - tool_trace.py（1,505 行）：qual 有自己的 audit trail
  - processors/（7,953 行）：qual 已有自己的 parsers
  - tools/（6,831 行）：qual 的工具完全不同
  - async_cli_runner.py（588 行）：已弃用
  - reasoning_protocol.py（120 行）：vendor 特化

**评审专家仲裁**：**部分纳入 ~12,000 行**（但需精简到 ~3,000 行）
- 仲裁修正：代码专家估算 ~3,260 行更合理（不是 12,000 行）。dayu 的 engine 层 26,744 行中，qual 需要的核心工具基础设施（Runner/ToolRegistry/ToolResult/ArgumentValidator/Events/Protocols/Exceptions）精简后约 3,000 行。
- 理由：工具结果信封 + 参数校验器 + 结构化事件 + Protocol 抽象是通用需要，不依赖 dayu 的 AsyncAgent 模式。

---

### 模块 4: services/write_pipeline/（22 文件，13,622 行）

**架构专家评估**：
- 核心设计理念：状态机驱动章节执行 + audit/confirm/repair 三步闭环 + 修复合同自动生成
- qual 不需要：qual 的 Gate0-8 状态机是完全替代

**代码专家评估**：
- pipeline.py（1,543 行）：qual 的 GateRunner 替代
- chapter_execution_coordinator.py（561 行）：qual 的 Gate3 替代
- chapter_audit_coordinator.py（570 行）：qual 的 Gate4 替代
- audit_rules.py（1,190 行）：qual 的 3 个检查器替代
- repair_executor.py（446 行）：qual 的 ADVC/PGNB 替代
- prompt_builder.py（601 行）：qual 的 _build_chapter_prompt 替代
- scene_executor.py（888 行）：qual 的 llm_caller 替代
- artifact_store.py（1,022 行）：qual 直接写文件

**评审专家仲裁**：**不纳入**
- 理由：qual 的 Gate0-8 状态机和 write_pipeline 解决同一问题（定性分析报告生成），但架构不同。dayu 用流水线协调器（chapter_execution_coordinator + chapter_audit_coordinator），qual 用 Gate 状态机（gate3.py + gate4.py）。两者是**架构等价物**，不是互补关系。
- **但应借鉴的设计**：
  1. 状态机驱动的章节执行（ChapterExecutionState）→ qual 的 Gate3 可以引入
  2. 结构化审计决策（AuditDecision）→ qual 的 Gate4 可以引入
  3. 修复合同自动生成（RepairContract）→ qual 的 ADVC 可以引入
  这些设计可以在 qual 的 Gate 内部实现，不需要引入整个 write_pipeline。

---

### 模块 5: fins/storage/（20 文件，4,719 行）

**架构专家评估**：
- 核心设计理念：6 个窄 Protocol + Factory 模式 + Batch 事务
- qual 不需要：qual 用 Wind MCP 直接获取数据

**代码专家评估**：
- repository_protocols.py（337 行）：qual 用 Wind MCP 替代
- fs_* 实现（~3,000 行）：qual 不需要本地文件仓储
- _fs_storage_infra.py（1,208 行）：qual 不需要 batch 事务

**评审专家仲裁**：**不纳入**
- 理由：qual 的数据获取通过 Wind MCP（实时 API）和 MinerU（PDF 解析），不需要本地仓储协议。dayu 的 storage 层是为"离线财报管线"设计的（下载→解析→存储→查询），qual 的数据流是"实时获取→直接使用"。
- **但应借鉴的设计**：窄 Protocol 拆分原则（不搞 God Repository）→ qual 的 DataAnchor 可以按职责拆分为 FinanceAnchor / OpsAnchor / MarketAnchor。

---

### 模块 6: prompting/（7 文件，1,591 行）

**架构专家评估**：
- 核心设计理念：scene manifest 继承 + 条件渲染 + context_slots 收口
- qual 需要：部分需要——条件渲染是通用能力

**代码专家评估**：
- 纳入：
  - prompt_renderer.py 的 `<when_tool>` 条件渲染逻辑（~200 行）
  - prompt_composer.py 的模板变量替换（~200 行）
  - prompt_contribution_slots.py 的 context_slots 收口（~100 行）
- 排除：
  - scene_definition.py（721 行）：scene manifest 体系过重
  - prompt_plan.py：qual 的 prompt 路径固定
  - tool_snapshot.py：qual 的工具集固定

**评审专家仲裁**：**部分纳入 ~500 行**
- 理由：条件渲染让 prompt 模板能根据运行时工具集自动裁剪（如 `<when_tool wind>` 自动裁剪 Wind 相关指令），避免 prompt 膨胀。这是 qual 需要的。
- scene manifest 继承体系对 qual 过重（qual 的 Gate prompt 结构固定，不需要动态继承）。

---

## 三、仲裁后 qual v9 代码量预估

| 类别 | 行数 | 来源 |
|------|------|------|
| **contracts 层**（从 dayu 裁剪） | ~1,800 | AgentMessage/RunState/CancellationToken/AppEvent/RunnerType |
| **engine 工具基础设施**（从 dayu 裁剪） | ~3,000 | Runner/ToolRegistry/ToolResult/ArgumentValidator/Events/Protocols |
| **prompting**（从 dayu 裁剪） | ~500 | 条件渲染 + 模板变量替换 + context_slots |
| **Gate 引擎**（qual 新增） | ~3,000 | GateRunner/GateState/Gate0-8/GateContext/GateResult |
| **检查器**（qual 保留精简） | ~900 | NumericGuard(380) + StructuralCheck(300) + CrossChapter(200) |
| **数据层**（qual 保留） | ~3,000 | DataAnchor + PGNB + ADVC + bind_fuzzy_dates + fact_extractor |
| **领域服务**（qual 新增） | ~2,000 | report_builder + retry_policy + orchestrator |
| **DSH 集成**（qual 新增） | ~1,000 | harness_llm + llm_bridge + adapters |
| **测试** | ~3,000 | 单元测试 + 集成测试 + 金标准 |
| **总计** | **~18,200** | — |

---

## 四、与之前 V9 方案的差异

| 维度 | 之前 V9 方案 | 仲裁后 V9 |
|------|------------|----------|
| **contracts 行数** | ~1,200 | ~1,800（增加 RunnerType/ModelConfig） |
| **engine 层** | ~150（仅 GateRunner） | ~3,000（引入工具结果信封/参数校验器/事件模型） |
| **host 层** | ~12,000 | **0**（DSH 已有等价替代） |
| **write_pipeline** | ~8,000 | **0**（Gate 状态机替代，但借鉴状态机/审计决策/修复合同设计） |
| **storage** | ~800 | **0**（Wind MCP 替代） |
| **prompting** | ~500 | ~500（不变） |
| **总代码量** | ~30,000 | **~18,200**（-39%） |

---

## 五、仲裁引入的 3 个关键设计借鉴

虽然 host/write_pipeline/storage 整体不纳入，但仲裁决定借鉴其核心设计：

### 5.1 从 write_pipeline 借鉴：状态机驱动的章节执行

```
Gate3 内部：
  ChapterState: PREPARE → GENERATE → VALIDATE → REPAIR → COMPLETE
  - PREPARE: 构建 prompt + 注入锚点
  - GENERATE: LLM 生成章节
  - VALIDATE: PGNB + ADVC + 检查器
  - REPAIR: 程序化修复（不调 LLM）
  - COMPLETE: 返回章节内容
```

### 5.2 从 write_pipeline 借鉴：结构化审计决策

```
Gate4 内部：
  AuditDecision:
    passed: bool
    violations: tuple[Violation, ...]  # 结构化违规列表
    repair_actions: tuple[RepairAction, ...]  # 自动推导的修复动作
  - violations 按严重性分级（fatal/important/suggestion）
  - repair_actions 由程序自动推导（不依赖 LLM）
```

### 5.3 从 host 借鉴：Gate 生命周期管理

```
GateRunner:
  - run_all(ctx) → dict[int, GateResult]
  - _run_single_gate(gate_num, ctx) → GateResult
  - _handle_failure(gate_num, result, ctx) → 重试/降级/阻断
  - 墙钟 deadline 守卫
  - 熔断器集成
```

---

## 六、实施路线图（仲裁后）

| Phase | 内容 | 工期 | 交付物 |
|-------|------|------|--------|
| **Phase 0** | contracts 层 + 清理死代码 | 1 周 | 6 新文件 ~1,800 行 + 删除 18 文件 |
| **Phase 1** | engine 工具基础设施 | 2 周 | 8 新文件 ~3,000 行（Runner/Registry/Validator/Events） |
| **Phase 2** | Gate 引擎 + 检查器精简 | 2 周 | GateRunner/GateState + 3 检查器 |
| **Phase 3** | Gate4 重构（状态机驱动 + 结构化审计） | 1 周 | 单轮确定性修复 + AuditDecision |
| **Phase 4** | prompting + Gate3 章节生成 | 2 周 | 条件渲染 + ChapterState 状态机 |
| **Phase 5** | 数据层精简 + Gate5-8 | 1 周 | DataAnchor 精简 + 估值/结论/终局 |
| **Phase 6** | 集成测试 + 验收 | 2 周 | 金标准 + pyright + 全流程验证 |
| **总计** | | **11 周** | |

---

## 七、验收标准

| 维度 | 标准 |
|------|------|
| **类型安全** | `pyright --strict` 零错误 |
| **代码量** | ≤20,000 行（从 57,318 降到 ~18,200） |
| **检查器** | 3 个（全部程序化） |
| **审查循环** | 单轮确定性修复（无 max_rounds） |
| **全流程** | 小鹏 9868.HK ≤15 分钟产出完整报告 |
| **Gate4 通过率** | ≥70% |
| **向后兼容** | `from qual_v8 import QualWorkflow` 仍可用 |
