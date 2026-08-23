# Qual v9 重构方案（HeavySkill K8 审查修订版）

**日期**：2026-08-23  
**版本**：v2.0（基于 HeavySkill K8 审查 6 项 P0 整改修订）  
**审查状态**：HeavySkill K8 有条件通过（8/8 轨迹，0 截断）  
**前序文档**：`docs/qual-v9-arbitrated-plan.md`（仲裁版）→ 本版修订

---

## 修订说明

HeavySkill K8 审查结论为**有条件通过**，提出 6 项 P0 整改。本版逐一落实：

| P0 | 整改要求 | 本版落实位置 |
|----|---------|-------------|
| P0-1 | 冻结检查器 16→3，建立覆盖矩阵 + 影子运行 | §三 |
| P0-2 | 定义 Gate4 修复失败出口状态机 | §四 |
| P0-3 | 补齐轻量存储与审计能力 | §五 |
| P0-4 | 建立回归测试集 | §六 |
| P0-5 | 重排工期至 16 周 | §七 |
| P0-6 | 补充生产可运营性设计 | §八 |

---

## 一、架构设计（四层分治，不变）

```
┌─────────────────────────────────────────────────┐
│  Layer 4: 终局兜底（程序化）                       │
│  ADVC + PGNB + bind_fuzzy_dates + 组装            │
├─────────────────────────────────────────────────┤
│  Layer 3: 质量保障（确定性检查器）                  │
│  numeric_guard + structural_check + cross_chapter │
├─────────────────────────────────────────────────┤
│  Layer 2: 章节生成（LLM 驱动，只读 Layer 1 数据）  │
│  Gate3: LLM 写章节，数字必须来自 DataAnchor 占位符  │
├─────────────────────────────────────────────────┤
│  Layer 1: 数据获取（程序化控制）                    │
│  Wind MCP + 财报解析 + DataAnchor + 事实提取       │
│  LLM 不参与数据获取                                │
└─────────────────────────────────────────────────┘
```

**核心约束**（不变）：Layer 2 的 LLM **只能读取** Layer 1 的数据（通过占位符），**不能自己生成数字**。

---

## 二、仲裁结果总表（不变）

| 模块 | dayu 行数 | 纳入决定 | qual 需要行数 | 理由摘要 |
|------|----------|---------|-------------|---------|
| contracts/ | 5,373 | **部分纳入** | ~1,800 | 公共类型骨架纳入 |
| host/ | 16,915 | **不纳入** | ~0 | DSH 已有等价替代 |
| engine/ | 26,744 | **部分纳入** | ~3,000 | 工具基础设施纳入 |
| write_pipeline/ | 13,622 | **不纳入** | ~0 | Gate 状态机替代 |
| fins/storage/ | 4,719 | **纳入轻量版** | ~800 | P0-3：补齐审计/快照存储 |
| prompting/ | 1,591 | **部分纳入** | ~2,000 | P0-5：prompting 重估至 2,000 行 |
| **合计** | **68,964** | — | **~7,600** | 排除 89% |

---

## 三、P0-1：检查器 16→3 覆盖矩阵 + 影子运行

### 3.1 覆盖矩阵

| # | 旧检查器 | 行数 | 去向 | 替代方式 | 漏检风险 |
|---|---------|------|------|---------|---------|
| 1 | numeric_guard | 403 | **保留** | — | 无 |
| 2 | structural_check | 407 | **保留** | — | 无 |
| 3 | cross_chapter_consistency | 505 | **保留精简** | 删除结论/时间冲突，只保留数据冲突 | 低：结论冲突由 LLM 生成质量承担 |
| 4 | fact_checker | 435 | **删除** | DataAnchor validate_chapter_any_fy 已替代 | 无：实测 P6 诊断确认全量假阳性 |
| 5 | conclusion_validator | 451 | **删除** | LLM 审查解析太粗糙（"问题"关键词触发） | 中：丢失结论合理性检查 → 由 Gate6 LLM 生成质量承担 |
| 6 | depth_reviewer | ~300 | **删除** | LLM 审查质量不可控 | 中：丢失分析深度检查 → 由 prompt 骨架约束承担 |
| 7 | assumption_checker | ~300 | **删除** | LLM 审查 | 低：假设检查由 Gate5 估值参数校验替代 |
| 8 | date_anchor_check | 388 | **删除** | bind_fuzzy_dates 已替代 | 无：实测确认日期问题由程序化绑定解决 |
| 9 | logic_consistency_check | 383 | **合并到 structural_check** | 逻辑矛盾模式匹配移入 structural_check | 无：纯 regex 匹配，合并无损 |
| 10 | data_reasonableness_check | 381 | **合并到 numeric_guard** | 数据合理性阈值移入 numeric_guard | 无：纯数值阈值，合并无损 |
| 11 | debate_service | ~200 | **删除** | LLM 质量不可控 | 低：辩论机制实测从未通过 |
| 12 | assumption_checker | ~300 | **删除** | 同 #7 | — |
| 13 | review_integrator | 875 | **删除** | 合并到 orchestrator | 无：只是编排层 |

### 3.2 影子运行策略

**Phase 2（检查器精简）期间**：
1. 保留旧 16 个检查器代码（不删除文件）
2. 新 3 个检查器作为**主路径**执行
3. 旧检查器作为**影子模式**运行（只记录不阻断）
4. 影子运行覆盖样本：
   - 小鹏 9868.HK 7 轮失败样本（验证漏检率）
   - 20 个历史成功报告样本（验证误报率）
5. **A/B 对比**：新 3 个检查器的问题列表 vs 旧 16 个检查器的问题列表
6. **通过标准**：新检查器漏检率 < 5%（与旧检查器对比）
7. **Phase 5 之后才允许删除旧检查器文件**

### 3.3 检查器分级审计策略

| 级别 | 含义 | 处理方式 |
|------|------|---------|
| **P0 阻断** | 数字幻觉/财年错位/空壳章 | 阻断报告输出 |
| **P1 修复** | 格式违规/结构缺失/证据不足 | 程序化修复，修复失败标注降级 |
| **P2 警告** | 逻辑矛盾/数据合理性/表述差异 | 记录到报告附录，不阻断 |

---

## 四、P0-2：Gate4 单轮修复的完整状态机

### 4.1 状态机定义

```
Gate4 状态机：
  CHECKING → (pass) → PASSED
  CHECKING → (fail + fixable) → REPAIRING
  CHECKING → (fail + not fixable + fatal) → FAILED_TERMINAL
  CHECKING → (fail + not fixable + non-fatal) → DEGRADED
  REPAIRING → (repair success + recheck pass) → PASSED
  REPAIRING → (repair success + recheck fail) → DEGRADED
  REPAIRING → (repair fail) → DEGRADED
  DEGRADED → 标注降级，继续后续 Gate
  FAILED_TERMINAL → 终止，转人工队列
```

### 4.2 三态出口

| 出口 | 条件 | 行为 |
|------|------|------|
| **PASSED** | 3 检查器全通过，或修复后复验通过 | 进入 Gate5 |
| **DEGRADED** | 修复后复验仍有非 fatal 问题 | 标注"质量受限"到报告头部，继续后续 Gate |
| **FAILED_TERMINAL** | 检查器发现 fatal 问题且无法程序化修复 | 终止流程，输出诊断报告，转人工队列 |

### 4.3 修复记录要求

每次修复必须记录：
```python
@dataclass(frozen=True)
class RepairRecord:
    gate_num: int
    chapter_num: int
    rule_id: str              # 触发规则 ID
    before_value: str         # 修复前值
    after_value: str          # 修复后值
    repair_type: str          # "replace" | "insert" | "delete"
    confidence: float         # 置信度
    timestamp: str
```

### 4.4 再验证闭环

```
修复 → 只重查被修复的章节（增量复验，不全量重查）→ 通过/降级
```

**墙钟硬限**：Gate4 总耗时 ≤ 120s（含检查 + 修复 + 复验）

---

## 五、P0-3：轻量存储与审计能力

### 5.1 存储需求分析

HeavySkill 审查指出：Wind MCP 只解决实时数据获取，不能替代审计日志/中间状态存储。需保留轻量 storage adapter。

### 5.2 最小存储协议（3 个窄 Protocol）

参照 dayu 的 6 个窄 Protocol，qual 只需 3 个：

```python
class AuditLogProtocol(Protocol):
    """审计日志：记录每次 Gate 执行的输入/输出/修复"""
    def log_gate_execution(self, gate_num: int, input_hash: str, 
                           result: GateResult, repair_records: tuple[RepairRecord, ...]) -> None: ...
    def get_gate_history(self, run_id: str) -> tuple[GateResult, ...]: ...

class SnapshotProtocol(Protocol):
    """输入快照：不可变，用于回溯和回归测试"""
    def save_snapshot(self, run_id: str, wind_data: dict, filing_data: dict, 
                      facts: dict) -> str: ...  # 返回 snapshot_id
    def load_snapshot(self, snapshot_id: str) -> dict: ...

class ReportVersionProtocol(Protocol):
    """报告版本：最终报告 + 质量标注 + 追溯信息"""
    def save_report(self, run_id: str, report: str, quality_markers: dict,
                    gate_results: dict[int, GateResult]) -> str: ...
    def load_report(self, run_id: str) -> dict: ...
```

### 5.3 实现

默认实现：文件系统（JSON 文件），~800 行。不引入 SQLite/数据库依赖。

```
workspace/
├── snapshots/
│   └── {run_id}/
│       ├── wind_data.json
│       ├── filing_data.json
│       └── facts.json
├── audit_logs/
│   └── {run_id}.jsonl
└── reports/
    └── {run_id}/
        ├── report.md
        ├── quality_markers.json
        └── gate_results.json
```

---

## 六、P0-4：回归测试集与评估体系

### 6.1 回归测试样本

| 样本 | 类型 | 用途 |
|------|------|------|
| 小鹏 9868.HK FY2023/2024/2025 | 失败样本 | 验证 Gate4 死循环是否消除 |
| 阅文 0772.HK（历史成功） | 成功样本 | 验证 v9 不退化 |
| 模拟空壳章（0 个数字） | 边界样本 | 验证空壳检测 |
| 模拟纯幻觉章节（所有数字错误） | 边界样本 | 验证 PGNB 兜底 |
| 模拟多财年混用 | 边界样本 | 验证 FiscalSemantics |

### 6.2 评估指标

| 指标 | 定义 | 目标 |
|------|------|------|
| **Gate4 通过率** | Gate4 输出 PASSED 或 DEGRADED 的比例 | ≥70% |
| **数字准确率** | 最终报告中数字与 Wind 锚点匹配的比例 | ≥95% |
| **空壳章率** | 最终报告中小数数字 <3 的财务章比例 | 0% |
| **全流程耗时** | 从启动到产出报告的总时间 | ≤15 分钟 |
| **漏检率** | 新 3 检查器 vs 旧 16 检查器的问题覆盖差异 | <5% |

### 6.3 回归测试流程

```
代码变更 → 运行回归测试集 → 检查所有指标 → 全部达标 → 允许合并
                                            → 任一不达标 → 阻断，修复后重跑
```

---

## 七、P0-5：重排工期（11 周 → 16 周）

| Phase | 内容 | 工期 | 交付物 | Go/No-Go 评审 |
|-------|------|------|--------|--------------|
| **Phase 0** | contracts 层 + 清理死代码 + 存储协议 | **2 周** | contracts(1,800行) + storage(800行) + 删除 18 文件 | 合约完整性检查 |
| **Phase 1** | engine 工具基础设施 | **2 周** | Runner/Registry/Validator/Events(3,000行) | pyright 零错误 |
| **Phase 2** | Gate 引擎 + 检查器（影子运行） | **3 周** | GateRunner/GateState + 3 新检查器 + 旧检查器影子模式 | A/B 漏检率 <5% |
| **Phase 3** | Gate4 重构（状态机 + 修复闭环） | **1 周** | 单轮确定性修复 + AuditDecision + 三态出口 | Gate4 状态机验证 |
| **Phase 4** | prompting + Gate3 章节生成 | **3 周** | 条件渲染(2,000行) + ChapterState 状态机 | 小鹏单章质量验证 |
| **Phase 5** | 数据层精简 + Gate5-8 + 删除旧检查器 | **2 周** | DataAnchor 精简 + 估值/结论/终局 + 删除影子检查器 | 全流程 ≤15 分钟 |
| **Phase 6** | 集成测试 + 回归测试 + 灰度 | **3 周** | 回归测试集 + 金标准 + v8/v9 影子运行 + 灰度切换 | 回归全指标达标 |
| **总计** | | **16 周** | | 6 个 Go/No-Go 评审门 |

### 7.1 工期调整说明

| 调整 | 原方案 | 修订后 | 理由 |
|------|--------|--------|------|
| Phase 0 | 1 周 | 2 周 | 增加存储协议设计 + 实现 |
| Phase 2 | 2 周 | 3 周 | 增加影子运行 + A/B 验证 |
| Phase 4 | 2 周 | 3 周 | prompt 迭代是质量基础，需要充分验证 |
| Phase 5 | 1 周 | 2 周 | 增加旧检查器删除 + Gate5-8 充分验证 |
| Phase 6 | 2 周 | 3 周 | 增加回归测试集 + v8/v9 影子运行 + 灰度切换 |

---

## 八、P0-6：生产可运营性设计

### 8.1 可观测性

| 能力 | 实现方式 | 优先级 |
|------|---------|--------|
| **结构化日志** | 每个 Gate 执行记录 input_hash/output/duration/repair_records | P0 |
| **trace_id** | 每次 run 分配唯一 trace_id，贯穿 Gate0-8 | P0 |
| **Gate 状态回放** | 通过 audit_log 可回放任意 Gate 的执行过程 | P1 |
| **执行追踪** | LLM 调用次数/token 消耗/工具调用次数 | P1 |

### 8.2 人工介入

| 场景 | 处理方式 |
|------|---------|
| Gate4 FAILED_TERMINAL | 输出诊断报告（问题列表 + 修复记录），转人工队列 |
| Gate4 DEGRADED | 报告头部标注"质量受限"，列出未修复问题 |
| Gate8 终局仍有 P0 问题 | 阻断输出，转人工复核 |

### 8.3 灰度与回滚

| 能力 | 实现方式 |
|------|---------|
| **v8/v9 影子运行** | v9 作为主路径，v8 作为影子（只记录不输出），对比结果 |
| **灰度切换** | 通过配置开关 `qual_version: "v8" | "v9" | "shadow_both"` |
| **回滚** | 配置切回 v8，v9 的存储/审计数据保留供分析 |
| **断点续跑** | 通过 SnapshotProtocol 保存中间状态，支持从任意 Gate 恢复 |

### 8.4 LLM 调用治理

| 能力 | 参数 | 默认值 |
|------|------|--------|
| 重试 | max_retries | 2 |
| 超时 | timeout_per_call | 120s |
| Token 预算 | max_tokens_per_gate | 32,768 |
| 总预算 | max_total_tokens | 200,000 |
| 降级 | 超预算时 | 标注"LLM 预算耗尽"，跳过非关键 Gate |

---

## 九、代码量重估

| 类别 | 原估算 | 修订后 | 变化原因 |
|------|--------|--------|---------|
| contracts 层 | ~1,800 | ~1,800 | 不变 |
| engine 工具基础设施 | ~3,000 | ~3,000 | 不变 |
| prompting | ~500 | ~2,000 | P0-5：prompt 迭代需要更多模板和条件渲染 |
| Gate 引擎 | ~3,000 | ~3,000 | 不变 |
| 检查器 | ~900 | ~900 | 不变 |
| 数据层 | ~3,000 | ~3,000 | 不变 |
| 存储协议 | ~0 | ~800 | P0-3：新增 3 个窄 Protocol + 文件系统实现 |
| 领域服务 | ~2,000 | ~2,000 | 不变 |
| DSH 集成 | ~1,000 | ~1,000 | 不变 |
| 可观测性/运营 | ~0 | ~1,500 | P0-6：日志/trace/人工介入/灰度 |
| 测试 | ~3,000 | ~5,000 | P0-4：回归测试集 + 影子运行 + 金标准 |
| 迁移/适配 | ~0 | ~1,000 | P0-6：v8/v9 并存适配层 |
| **总计** | **~18,200** | **~25,000** | +37%（主要是测试/运营/存储） |

---

## 十、验收标准（修订）

| 维度 | 标准 |
|------|------|
| **类型安全** | `pyright --strict` 零错误 |
| **代码量** | 生产代码 ≤20,000 行 + 测试/运营 ≤8,000 行 |
| **检查器** | 3 个主路径 + 旧检查器影子模式（Phase 5 后删除） |
| **审查循环** | 单轮确定性修复 + 三态出口（PASSED/DEGRADED/FAILED_TERMINAL） |
| **全流程** | 小鹏 9868.HK ≤15 分钟产出完整报告 |
| **Gate4 通过率** | ≥70% |
| **漏检率** | 新 3 检查器 vs 旧 16 检查器 <5% |
| **回归测试** | 全指标达标（数字准确率 ≥95%、空壳章率 0%） |
| **向后兼容** | `from qual_v8 import QualWorkflow` 仍可用 |
| **灰度** | v8/v9 影子运行对比通过 |
