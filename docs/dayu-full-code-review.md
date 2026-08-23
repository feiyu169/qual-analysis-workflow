# Dayu-Agent 全量代码审查报告（逐模块对照 Qual）

**审查日期**：2026-08-22  
**审查范围**：dayu-agent 全量 ~200,000 行代码（含 tests），6 个并行子代理逐文件审查  
**对照对象**：qual v8（57,318 行 / 262 文件）

---

## 一、总览：dayu 哪些是 qual 需要的？

| 模块 | dayu 行数 | qual 需要 | 比例 | 必要性 |
|------|----------|----------|------|--------|
| contracts/ | 5,373 | ~1,200 | 22% | **核心借鉴** |
| execution/ | 2,330 | ~500 | 21% | 部分借鉴 |
| host/ | 16,915 | ~12,000 | 71% | **大量借鉴** |
| engine/ | 26,744 | ~5,200 | 19% | 工具基础设施借鉴 |
| engine/processors/ | 7,953 | ~1,500 | 19% | 表单切分质量借鉴 |
| engine/tools/ | 6,831 | ~310 | 5% | 不需要 |
| services/ | 3,749 | ~2,000 | 53% | 部分借鉴 |
| services/write_pipeline/ | 13,622 | ~8,000 | 59% | **核心借鉴** |
| fins/domain/ | 828 | ~200 | 24% | 领域模型借鉴 |
| fins/downloaders/ | 3,711 | ~300 | 8% | 简化版 |
| fins/ingestion/ | 1,173 | 0 | 0% | 不需要 |
| fins/pipelines/ | 17,012 | ~500 | 3% | 不需要 |
| fins/processors/ | 20,931 | ~2,000 | 10% | 表单切分借鉴 |
| fins/storage/ | 4,719 | ~800 | 17% | **仓储协议借鉴** |
| fins/tools/ | 7,096 | ~600 | 8% | 核心读工具借鉴 |
| fins/根目录 | 13,209 | ~200 | 2% | ticker 归一化 |
| cli/ | 7,845 | 0 | 0% | 不需要 |
| prompting/ | 1,591 | ~500 | 31% | scene manifest 借鉴 |
| startup/ | 912 | ~300 | 33% | 配置加载借鉴 |
| process_lifecycle/ | 566 | 0 | 0% | 不需要 |
| wechat/ | 5,961 | 0 | 0% | 不需要 |
| web/ | 4,281 | 0 | 0% | 不需要 |
| render/ | 383 | 0 | 0% | 不需要 |
| **总计** | **~192,000** | **~36,300** | **19%** | — |

**核心结论：dayu ~192,000 行代码中，qual 实际只需要约 36,300 行（19%）。**

---

## 二、逐模块关键发现

### 2.1 contracts/（5,373 行 → qual 需要 ~1,200 行）

**qual 必须新建的核心契约**：
- `GateContract` / `GateResultContract`（替代 dict[str, Any] 传递）→ 对照 dayu `agent_execution.py`
- `GateState` 5 态状态机 → 对照 dayu `run.py` RunState 7 态
- `CancellationToken` → 对照 dayu `cancellation.py`
- `QualEvent` / `QualResult` → 对照 dayu `events.py`
- `CheckerProtocol` / `RepairerProtocol` → 对照 dayu `protocols.py`

**qual 不需要的**：
- `agent_execution_serialization.py`（721 行）—— 序列化层可简化
- `reply_outbox.py`（157 行）—— qual 无多通道投递
- `session.py`（82 行）—— qual 无多会话
- `toolset_config.py`（318 行）—— qual 工具集固定

### 2.2 host/（16,915 行 → qual 需要 ~12,000 行）

**qual 需要的 4 项能力**（dayu 有 9 项）：

| 能力 | qual 需要 | 来源文件 | 估算行数 |
|------|----------|---------|---------|
| Gate 生命周期 | ✅ | `executor.py`（1,945 行）+ `run_registry.py`（572 行） | ~2,000 |
| 并发治理 | ✅ | `concurrency.py`（335 行） | ~300 |
| 事件发布 | ✅ | `event_bus.py`（153 行）+ `events.py`（48 行） | ~200 |
| Timeout 控制 | ✅ | `executor.py` 内 deadline watcher | ~200 |
| Session 管理 | ❌ | — | 0 |
| Cancel 控制 | ❌ | — | 0 |
| Resume | ❌ | — | 0 |
| 多轮会话 | ❌ | — | 0 |
| Reply outbox | ❌ | — | 0 |

**关键发现**：
- dayu 的 Host 层设计精良（状态机清晰、契约稳定），但大部分是 qual 不需要的"多会话多租户"能力
- `conversation_memory.py`（1,338 行）qual 只需要 ~500 行（去掉 compaction/episodic summary）
- `protocols.py`（1,210 行）qual 全量借鉴——定义了所有稳定的 Protocol 接口

### 2.3 engine/（26,744 行 → qual 需要 ~5,200 行）

**qual 最应该借鉴的 4 个概念**：

| 概念 | dayu 文件 | qual 需要 | 理由 |
|------|----------|----------|------|
| 统一工具结果信封 | `tool_result.py`（341 行） | ✅ 全量借鉴 | LLM 输出不可信，需要统一信封 |
| 参数校验器 | `argument_validator.py`（545 行） | ✅ 全量借鉴 | JSON Schema 驱动校验 |
| 结构化事件模型 | `events.py`（304 行） | ✅ 全量借鉴 | 替代 dict 传事件 |
| 协议抽象 | `protocols.py`（78 行） | ✅ 全量借鉴 | Protocol 模式便于测试 Mock |

**qual 不需要的**：
- `async_agent.py`（2,093 行）—— qual 是 Gate 顺序执行，不是 LLM 自主 tool loop
- `sse_parser.py`（990 行）—— qual 用同步 JSON 响应
- `context_budget.py`（444 行）—— Gate 模型天然限制上下文
- `duplicate_call_guard.py`（269 行）—— Gate 模型每 Gate 最多一次调用
- `tool_trace.py`（1,505 行）—— qual 有自己的 audit trail
- 全部 `processors/`（7,953 行）—— qual 已有自己的 parsers
- 全部 `tools/`（6,831 行）—— qual 的工具完全不同

### 2.4 services/write_pipeline/（13,622 行 → qual 需要 ~8,000 行）

**这是 dayu 最值得 qual 借鉴的模块**——audit/confirm/repair 三步闭环：

```
初始写作 → 程序审计 → LLM 审计 → 证据复核 → 锚点修复 → 修复策略决策 → 局部修复/整章重建 → 回到程序审计
```

**qual 应借鉴的 5 个核心设计**：

| 设计 | dayu 文件 | qual 现状 | 差距 |
|------|----------|----------|------|
| 状态机驱动的章节执行 | `chapter_execution_coordinator.py`（561 行） | 硬编码循环 | **大** |
| 结构化审计决策 | `audit_rules.py`（1,190 行） | 简单 pass/fail | **大** |
| 三步审计闭环 | `chapter_audit_coordinator.py`（570 行） | 无 confirm 步骤 | **中** |
| 修复合同自动生成 | `repair_executor.py`（446 行） | LLM 自由 patch | **大** |
| 过程状态追踪 | `pipeline.py`（1,543 行）内 process_state | 无 | **大** |

**qual 不需要的**：
- `artifact_store.py`（1,022 行）—— qual 无持久化产物管理
- `template_parser.py`（335 行）—— qual 的模板更简单
- `company_facets.py`（357 行）—— qual 的行业判断更简单

### 2.5 fins/storage/（4,719 行 → qual 需要 ~800 行）

**最值得借鉴的架构设计**——6 个窄 Protocol：

```
CompanyMetaRepositoryProtocol      — 公司级元数据
SourceDocumentRepositoryProtocol   — 原始财报 CRUD
ProcessedDocumentRepositoryProtocol — 解析产物 CRUD
DocumentBlobRepositoryProtocol     — 文件字节读写
BatchingRepositoryProtocol         — 批量事务
FilingMaintenanceRepositoryProtocol — 维护操作
```

**qual 当前**：`filing_service.py` 直接用 `Path` 操作文件系统，无 Protocol 抽象。
**qual 借鉴**：定义 3 个窄 Protocol（CompanyMeta + SourceDocument + ProcessedDocument），简化实现。

### 2.6 不需要的模块（合计 ~85,000 行）

| 模块 | 行数 | 不需要的理由 |
|------|------|------------|
| cli/ | 7,845 | qual 是 DSH 技能，不需要独立 CLI |
| wechat/ | 5,961 | qual 无微信通道 |
| web/ | 4,281 | qual 有 DSH Web GUI |
| fins/pipelines/（大部分） | 16,500 | qual 不需要 SEC 6-K/Docling/离线快照 |
| engine/processors/（大部分） | 6,400 | qual 已有自己的 parsers |
| engine/tools/（大部分） | 6,500 | qual 的工具完全不同 |
| process_lifecycle/ | 566 | qual 运行在 DSH 里 |
| fins/ingestion/ | 1,173 | qual 无长事务 |
| render/ | 383 | qual 不输出 PDF/Word |
| gui/ | 4 | 空占位 |
| 其他冗余 | ~36,000 | 重复代码/兼容性/CLI 特定 |

---

## 三、qual 重构后的预期代码量

| 类别 | 当前 | 重构后 | 来源 |
|------|------|--------|------|
| qual_v8/ 核心 | 6,849 | ~5,000 | 精简 + contracts |
| quality/ 检查器 | 20,034 | ~12,000 | 删除 10 个检查器 |
| workflow.py | 3,446 | 0（拆分） | — |
| 新 contracts/ | 0 | ~1,200 | 借鉴 dayu |
| 新 host 层 | 0 | ~3,000 | 借鉴 dayu（精简版） |
| 新 write_pipeline | 0 | ~5,000 | 借鉴 dayu |
| 数据层 | ~2,500 | ~4,600 | 借鉴 dayu storage/tools |
| prompting | ~300 | ~800 | 借鉴 dayu scene manifest |
| 其他 | ~24,000 | ~8,000 | 保留核心 |
| **总计** | **~57,000** | **~39,600** | **-30%** |

---

## 四、AGENTS.md 编码约束（应直接应用到 qual）

从 dayu 的 AGENTS.md（109 行）中提取 qual 必须遵守的约束：

1. **禁止 `Any`/无类型参数** → qual 当前 15+ 处违规
2. **禁止 God object/function** → workflow.py 是典型
3. **禁止兼容性代码** → qual 的 `HAS_*` 标志位
4. **禁止魔法数字/字符串** → qual 的 Gate 阈值硬编码
5. **完整中文 docstring** → qual 覆盖不完整
6. **Protocol 优先** → qual 直接依赖具体实现
7. **frozen dataclass** → qual 用可变 dataclass
8. **pyright 强制** → qual 无类型检查
9. **测试覆盖率 ≥80%** → qual 以 mock 为主

---

## 五、核心结论

### dayu 的代码量为什么是 qual 的 3.5 倍？

| 原因 | 行数占比 | 说明 |
|------|---------|------|
| **多 UI 层** | ~18,000 行（9%） | CLI + WeChat + Web + GUI，qual 只有 DSH 技能 |
| **多市场覆盖** | ~40,000 行（21%） | SEC + CN + HK 全量管线，qual 只有 HK/CN |
| **重型引擎** | ~27,000 行（14%） | LLM 自主 tool loop + SSE + context budget，qual 是 Gate 顺序执行 |
| **完整产品化** | ~25,000 行（13%） | Session/Run/Resume/Reply/记忆/并发，qual 是单次分析 |
| **冗余/兼容** | ~15,000 行（8%） | 重复定义、旧代码、CLI 特定逻辑 |
| **qual 真正需要的** | ~36,000 行（19%） | contracts + host 核心 + write_pipeline + storage + prompting |

### qual 应该从 dayu 借鉴什么？

**直接搬用**（~15,000 行）：
1. contracts 层（frozen dataclass + Protocol + 状态机）
2. host 核心（executor + run_registry + event_bus + concurrency）
3. write_pipeline 核心（state machine + audit rules + repair executor）

**设计理念借鉴**（~10,000 行 qual 自己写）：
4. 仓储协议（3 个窄 Protocol + 简化实现）
5. 工具结果信封 + 参数校验器
6. scene manifest 继承 + 条件渲染

**不需要**（~130,000 行）：
7. 多 UI 层 / 多市场管线 / 重型引擎 / 完整产品化 / 冗余代码
