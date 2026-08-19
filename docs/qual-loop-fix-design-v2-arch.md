# qual v8 死循环修复——修订后架构设计（v2）

日期：2026-08-19
依据：`docs/qual-loop-fix-design.md`（原方案）+ `docs/heavyskill-fix-review.md`（HeavySkill 审查报告，18 项修正清单 + 5 项设计裁决）+ 源码实证核对
定位：本文档只含**架构层面**设计（分层、路由、状态机、预算、数据流、边界、验收）。逐行代码设计由代码专家按本文档落地。
范围：P0 止血（11 项：P0-A×3 + P0-B×8）+ P1 架构（5 项）+ 清理（2 项），与 18 项修正清单一一对应（见 §7 矩阵）。

---

## 0. 架构原则（v2 修订后）

1. **先分类，后路由，重试是例外**：错误四分类；只有 TRANSIENT 可同模型重试；DETERMINISTIC 全链非重试，只允许"换路由单次逃生"，仍败即降级+打标（裁决 c）。
2. **单一时间主源**：全局墙钟 deadline 是唯一时间预算；per-call 超时与 per-gate 时长均为其派生值，禁止多套独立时钟（裁决 d，消解原"预算与超时冲突"）。
3. **fail-closed 是缺省语义**：任何非 PASS 出口（豁免、早停、预算、超时、审查异常、最大轮数）一律 `passed=False` + 打标；豁免永不产生通过（裁决 a）。
4. **降级必须带语义标记且标记必须到达报告**：results 恒 9 条目 + 每层降级点打标 + 报告聚合横幅，杜绝静默产出（裁决 d）。
5. **单调性用签名差集判**：前后同口径 + deepcopy 快照，防"修复 A 引入 B"被数量比较掩盖（裁决 e）。
6. **可选能力显式门控**：辩论（debate）是可选增强，`enable_debate` 默认 False（裁决 b）。
7. **单一契约源**：错误枚举、重试语义、豁免规则各只定义一次（清理#17/#18、P1#12）。

---

## 1. 修订后的分层架构

```
┌──────────────────────────────────────────────────────────────────────┐
│ L0 入口层  run_xpev_full.py / run_qual_full.py                        │
│   改造：① 构造 review_caller（REVIEW_SYSTEM + 同一 fallback 策略包覆，│
│          不再裸复用主 caller —— P1#14）                                 │
│        ② fallback 滑动窗口：切换判定移入 except 分支，全故障场景可切换  │
│          （P0-B#10）；确定性失败→换路由单次逃生（P0-B#8）                │
│        ③ 补 DeterministicLLMFailure 导入 + run_qual_full 同步（P0-B#11）│
└──────────────────────────────┬───────────────────────────────────────┘
                               │ llm_caller / review_caller
┌──────────────────────────────▼───────────────────────────────────────┐
│ L1 引擎层  qual_v8/workflow.py（QualWorkflow.execute）                 │
│   改造：① 【deadline 注入层·入口】计算全局 deadline（monotonic 绝对     │
│          时间戳）→ context["deadline"]；主 caller 包 deadline guard     │
│        ② Gate 循环顶部 deadline 检查（超时→当前 Gate 记失败 + 剩余     │
│          Gate 全部补写 skipped 条目 —— 修 3b 缺条目/打标失效）           │
│        ③ 重试语义单一常量表 RETRY_POLICY（shadow/soft/enforce）（#18）  │
│        ④ 熔断记录改用单一枚举源 + 可达阈值（P1#12/#13）                 │
│        ⑤ 失败后报告打"未修复"标 + quality_degraded（含豁免数/超时）      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ context: llm_caller / review_caller /
                               │   llm_call_budget / deadline /
                               │   enable_debate / shadow_skip_repair
┌──────────────────────────────▼───────────────────────────────────────┐
│ L2 Gate 层  qual_v8/gates/gate4.py（Gate4AuditRepair）                 │
│   改造：① fail-closed 双堵漏：无 caller→passed=False（P0-A#2）；        │
│          实质审查异常→passed=False（不再返回 True）                     │
│        ② 消费 shadow_skip_repair：shadow 模式跳过修复循环（P0-B#9）     │
│        ③ 传参：review_caller / review_caller_override=True /           │
│          enable_debate / llm_call_budget / deadline（P0-B#5/#6/#7）     │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────┐
│ L3 审查-修复循环层  quality/review_repair_loop.py                      │
│   改造：① 【收敛状态机】豁免证据护栏 + 早停 + 单调守卫 + 预算检查       │
│          （§3；P0-A#1/#3、P1#15）                                      │
│        ② 【enable_debate 门控】默认 False，跳过辩论 3 章×多角色         │
│          （P0-B#5；裁决 b）                                            │
│        ③ budgeted caller 透传全链（P0-B#6），deadline 轮首/调用前检查   │
│          （P0-B#7）                                                    │
│        ④ 审查 caller 消费外部注入的 review_caller（保留 REVIEW_SYSTEM）│
└──────────────────────────────┬───────────────────────────────────────┘
                               │ 有效超时 = min(调用超时, deadline 剩余)
┌──────────────────────────────▼───────────────────────────────────────┐
│ L4 LLM 调用层  harness_llm.py（create_harness_caller）                 │
│   改造：① 失败分类四类（§2 决策表）                                    │
│        ② 【deadline 感知】新增 deadline 参数：调用前查剩余、有效超时    │
│          min(timeout, remaining)、剩余≤0 抛 DeadlineExceeded（确定性类）│
│        ③ DeterministicLLMFailure 不重试（重试循环前置分流）             │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ /api/llm-bridge（finishReason 语义已具备，
                               │   llm-bridge.js:56-64 实证；清理#17：标注验证性，无需重建）
┌──────────────────────────────▼───────────────────────────────────────┐
│ L5 宿主桥接  plugins/llm-bridge.js（验证性确认，无改动）                │
└──────────────────────────────────────────────────────────────────────┘

横切层（跨 L1-L4）：
  A. 【deadline 注入层】单一绝对 deadline 沿 context 下传，4 个强制检查点：
     L1 Gate 循环顶部 → L3 轮首 → L3 单调用前 → L4 桥接有效超时（§4）
  B. 【豁免证据护栏层】L3 内：≥3 轮 + 无修复迹象 + 审计记录 + 报告注明豁免数（P0-A#3）
  C. 【enable_debate 门控】WorkflowConfig → context → gate4 → loop（P0-B#5）
  D. 【确定性失败路由】L4 分类 → 全链不重试 → L0 换路由单次逃生 → 逐层降级打标（§2 链路）
```

**新增职责一览**（对比原方案 §1）：

| 层 | 原方案职责 | v2 新增职责 |
|---|---|---|
| L0 入口 | 构造 llm_caller（含 fallback） | 构造 review_caller（保留 REVIEW_SYSTEM）；fallback 切换移入 except；换路由单次逃生；双 runner 同步 |
| L1 引擎 | Gate 循环顶部墙钟检查、shadow 降重试、报告打标 | deadline 注入层入口；results 恒 9 条目补写；单一 RETRY_POLICY 表；熔断单一枚举源+可达阈值 |
| L2 Gate4 | fail-closed 一半（仅异常）、传主 caller | 双 fail-open 堵漏（无 caller/异常）；shadow_skip_repair 消费；全参透传 |
| L3 循环 | 收敛早停+豁免+单调守卫（数量比较） | 收敛状态机（豁免证据护栏/签名差集单调/deadline 检查点）；enable_debate 门控；budgeted caller 全链透传 |
| L4 调用层 | 分类+确定性不重试 | deadline 参数（有效超时派生）；DeadlineExceeded 归确定性类 |
| L5 桥接 | finishReason 语义补全（改动 7） | **删除**：现状已具备（实证），降为验证性确认 |

---

## 2. 错误分类与路由决策表

### 2.1 四类错误 × 处理策略 × 消费方

| 错误类 | 判定源（L4 分类） | 处理策略 | 重试语义 | 消费方 |
|---|---|---|---|---|
| **TRANSIENT** 瞬态 | 网络异常（URLError/ConnectionError/TimeoutError）；`ok=False, finish=error/null` | 同模型退避重试 | L4 内重试 ≤2 次 + 指数退避；L0 fallback 滑动窗口计数（切换判定移入 except）；L1 Gate 级重试 | harness_llm / fallback / workflow Gate 循环 |
| **DETERMINISTIC** 确定性 | `ok=False, finish=max-tokens 且 text 空`；格式契约违反；deadline 耗尽（DeadlineExceeded 子类） | **不重试**；只允许 L0 换路由（直连/换模型）**单次**逃生；仍败 → 降级+打标 | L4/L3/L2/L1 各级循环一律 0 次同模型重试（`except DeterministicLLMFailure: raise` 前置分流）；逃生重试 ≤1 次且必须换路由 | 全链（§2.3 完整链路） |
| **SEMANTIC** 语义 | `ok=True` 但内容不合格（格式校验失败/审查发现的问题/patch 校验失败） | 业务处理：格式修正重写（_generate_chapter 格式循环）、修复循环（_repair_chapters） | 业务层自有上限（max_format_retries、max_rounds）；**不再计为 LLM 调用失败**，不计入熔断 | _generate_chapter / review_repair_loop / patch_applier |
| **CIRCUIT_OPEN** 熔断打开 | 熔断器状态 == OPEN 且冷却期未过 | 跳过执行 | 0 次；冷却期后 HALF_OPEN 单次探测 | L1 Gate 循环顶部 `can_execute()` |

### 2.2 DeterministicLLMFailure 完整链路（从抛出到降级打标）

```
[1] 产生    harness_llm._call_bridge 返回 ok=False, finish=max-tokens, text 空
            → raise DeterministicLLMFailure(finish_reason="max-tokens", model=...)
            deadline 剩余≤0 → raise DeadlineExceededError（DeterministicLLMFailure 子类）

[2] 不重试   L4 重试循环: except DeterministicLLMFailure: raise（0 次同模型重试）

[3] 逃生     L0 _llm_with_fallback: except DeterministicLLMFailure:
              · 滑动窗口记 True（提示任务-模型错配）
              · 若可换路由（桥接→直连 deepseek-chat，或换非推理模型）→ 单次重试
                · 成功 → 返回文本（窗口不清零，保持滑动语义）
                · 失败 → re-raise（携带已尝试路由）
              · 无可用路由 → re-raise
            （禁止：同模型、同路由重试；禁止把确定性失败按 TRANSIENT 退避）

[4] 上层不吞  所有 except Exception 之前必须前置 except DeterministicLLMFailure:
              · tools/finance/workflow.py::_generate_chapter（P0-B#4）：
                不进入格式重试循环 → 直接降级为"数据不足"章节 + 内嵌确定性失败标记
              · review loop / _repair_chapters：该章/该项跳过 + 记录 degraded
              · qual_v8/workflow.py Gate 循环（原 277-284 except Exception）：
                不 Gate 重试 → 熔断记录 permanent → Gate 判失败 → break

[5] 降级+打标 每层降级点必须打标，标记沿 context 聚合到报告：
              · 章节级：内容内嵌 <!-- ⚠️ 确定性失败: finish/model -->，计入 context["degraded_chapters"]
              · 审查级：审查 LLM 维度失败 → 该维度跳过 + 计入 degraded_count；
                        同一 Gate 内审查 LLM 失败 ≥3 次或关键维度（结论合理性）失败
                        → Gate4 强制 passed=False（fail-closed，防"审查降级→假 pass"）
              · 修复级：该章不修复，计入 remaining_issues（不豁免）
              · Gate 级：Gate passed=False + errors 记录（enforce 模式 → ComplianceBlockedException）
              · 报告级：L1 组装 report 时聚合所有 degraded 标记（章节/豁免/Gate 失败/预算超时）
                        → 统一"质量降级"横幅 + context["quality_degraded"]=True

[6] 熔断      Gate 循环将最终上抛的 DeterministicLLMFailure 经 ErrorClassifier
              分类为 LLM_EMPTY_OUTPUT（permanent, retry=False, escalate=True，P1#12）
              → 熔断计数 +1（阈值 2 可达，P1#13）→ 连续确定性失败可熔断后续执行
```

**决策表对应关系**：`DeterministicLLMFailure` 的判定源 = L4（max-tokens 空/DeadlineExceeded）；策略 = 不重试+换路由单次+降级打标；消费方 = 全链（L0 逃生、L4 起抛、L1 熔断与打标、L3 收敛状态机把未修复计入 remaining）。

---

## 3. 审查-修复循环的收敛状态机

### 3.1 状态与转换（L3，review_and_repair_loop）

```
                    ┌──────────────────────────────────────────────┐
                    │ S0 IDLE（轮首）                                │
                    │ ① deadline 剩余 ≤0 → T_DEADLINE               │
                    │ ② 调用计数 ≥60  → T_BUDGET                    │
                    └──────────────────────┬───────────────────────┘
                                           │ 通过
                    ┌──────────────────────▼───────────────────────┐
                    │ S1 REVIEW：全量审查（同口径管线）              │
                    │  deep（确定性 5 项） + substantive（LLM，经     │
                    │  budgeted+deadline 感知 caller）               │
                    │  审查 LLM 失败降级 → degraded_count++；         │
                    │  达到降级阈值 → T_REVIEW_FAIL（fail-closed）    │
                    └──────────────────────┬───────────────────────┘
                                           │ issues[]（原始集合）
                    ┌──────────────────────▼───────────────────────┐
                    │ S2 EXEMPT-FILTER：签名（保留章节号，P0-A#1）   │
                    │  签名 ∈ exempted → exempted_pool               │
                    │  否则 → kept                                   │
                    └──────────────────────┬───────────────────────┘
                                           │
                    ┌──────────────────────▼───────────────────────┐
                    │ S3 CONVERGENCE（收敛判定，fail-closed 缺省）   │
                    │  kept=∅ ∧ exempted_pool=∅ → PASS ✅           │
                    │  kept=∅ ∧ exempted_pool≠∅ → DEGRADE ❌        │
                    │  kept≠∅ ∧ round>1 ∧ |kept|≥|kept_prev|        │
                    │        ∧ fixed_prev=0 → EARLY_STOP ❌          │
                    │  否则 → 进入修复                               │
                    └──────────────────────┬───────────────────────┘
                                           │
                    ┌──────────────────────▼───────────────────────┐
                    │ S4 REPAIR：轮首 deepcopy 快照 chapters_snapshot│
                    │  patch 修复（budgeted+deadline 感知 caller）    │
                    │  确定性失败/异常 → 该章跳过 + 记录（不豁免）     │
                    └──────────────────────┬───────────────────────┘
                                           │
                    ┌──────────────────────▼───────────────────────┐
                    │ S5 MONOTONIC-GUARD（签名差集，P1#15）          │
                    │  同口径重审（deep+substantive 同管线，原始     │
                    │  签名集合，不受豁免剔除影响）                    │
                    │  新签名 ⊄ 旧签名 → ROLLBACK（恢复快照，         │
                    │  fixed=0，记录回归）→ 继续 S6                  │
                    │  无新签名 → 接受修复                           │
                    └──────────────────────┬───────────────────────┘
                                           │
                    ┌──────────────────────▼───────────────────────┐
                    │ S6 EXEMPT-LEARN（证据护栏，P0-A#3）            │
                    │  签名出现 ≥3 轮 ∧ 无修复迹象（该签名从未因修复  │
                    │  消失）→ 加入 exempted + 审计记录               │
                    │  （签名/首末轮/证据/涉及章节）                  │
                    └──────────────────────┬───────────────────────┘
                                           │ round < max_rounds → S0
                                           │ round == max_rounds → T_MAXROUNDS ❌
```

### 3.2 出口语义（fail-closed 标注）

| 出口 | 触发条件 | passed | 标记/副作用 |
|---|---|---|---|
| **PASS** ✅ | kept=∅ 且 exempted_pool=∅ | **True** | 唯一 True 出口；无标记 |
| **DEGRADE** ❌ | kept=∅ 但豁免清单非空 | False | remaining_issues=exempted_pool；报告注明豁免数；quality_degraded=True（裁决 a） |
| **EARLY_STOP** ❌ | 问题数不降且上轮修复=0 | False | remaining_issues=kept[:10]；打标 |
| **T_REVIEW_FAIL** ❌ | 审查 LLM 降级达阈值（≥3 或关键维度） | False | errors="审查能力降级"；打标 |
| **T_DEADLINE** ❌ | 轮首 deadline 剩余 ≤0 | False | 打标"全局墙钟预算耗尽" |
| **T_BUDGET** ❌ | 调用计数 > 60 | False | 打标"单 Gate 调用预算耗尽" |
| **T_MAXROUNDS** ❌ | round 达 max_rounds 仍有 kept | False | remaining_issues；打标 |

**豁免语义（裁决 a 落地）**：豁免只做三件事——(1) 停止对该签名问题的**修复投入**（消费预算/轮数的元凶）; (2) 将其移入 exempted_pool 随结果返回并计入报告; (3) 在审计日志留痕。豁免**永不**参与 PASS 判定；"排除豁免后为空"只是 DEGRADE 的触发，PASS 还需"豁免清单为空"。由此豁免与 fail-closed 不冲突：豁免终止的是循环（有界），而非通过语义（仍是 False）。

**单调守卫（裁决 e + P1#15）**：轮首 `chapters_snapshot = deepcopy(chapters)`；修复后对快照的当前内容用**同一管线**（S1 完全相同调用序列）重审；比较**原始签名集合**（不含豁免剔除，防剔除干扰）——`after_signatures ⊄ before_signatures` 即回归 → 回滚。数量比较被弃用，因"删 A 加 B"在数量上不可见。

---

## 4. 预算体系设计

### 4.1 预算结构与优先级

| 预算 | 类型 | 默认 | 作用域 | 触发行为 |
|---|---|---|---|---|
| **全局墙钟 deadline**（主预算） | 绝对 monotonic 时间戳 | 5400s（90 分钟，WorkflowConfig.global_timeout_seconds） | 整个工作流 | 任一检查点触发 → 终止当前工作单元 → fail-closed + 打标 |
| **单 Gate LLM 调用次数**（次预算） | 计数器 | 60（WorkflowConfig.max_llm_calls_per_gate） | 单个 Gate（Gate4 循环） | 超过 → 终止循环 → fail-closed + 打标 |
| 轮数上限 max_rounds | 计数器 | 3 | 审查-修复循环 | 达上限仍有问题 → T_MAXROUNDS |

**优先级**：deadline（全局墙钟） > 调用次数（局部） > 轮数（最弱）。三者是**独立计数器**，先到先触发；任一触发都汇入同一条终止路径（fail-closed + 打标 + 审计），因此**不存在"预算与超时冲突"**——它们不是竞争关系，而是嵌套的保险丝。

**时间冲突消解（裁决 d）**：原方案存在三套独立时钟（timeout_per_gate=600、global=5400、call=300）互相矛盾。v2 规则：**全局 deadline 是唯一时间主源**；per-call 超时 = `min(调用配置超时, deadline 剩余)`，per-gate 时长不再独立配置；任何组件禁止持有自己的墙钟计数器。

### 4.2 deadline 注入与 4 层检查点

```
L1  workflow.execute 开头：deadline = monotonic() + global_timeout_seconds
    → context["deadline"]；主 llm_caller 外包 _deadline_guard（预检）
        │
L1  Gate 循环顶部：monotonic() > deadline → 当前 Gate 记失败 + 剩余 Gate 全补
    skipped 条目 + break（results 恒 9 条目，修 3b 缺条目/打标失效）
        │
L3  循环轮首（S0）：deadline 剩余 ≤0 → T_DEADLINE
        │
L3  单调用前：budgeted caller 查剩余 ≤0 → 抛 DeadlineExceeded（确定性类，不重试）
        │
L4  harness_llm（新增 deadline 参数）：调用前查剩余；effective_timeout =
    min(timeout, max(1, remaining)) 作为 urlopen 超时；返回后再查剩余
```

**最坏超时上界**：deadline + 单次在途调用上限（默认 300s）。理由：预检在调用前执行，唯一可能超支的是一个已在途的桥接调用（其自身超时 ≤300s）。该上界是**可证明的**，可作为验收断言。

### 4.3 超时/预算后 results 与报告打标的完整性保证

1. **results 恒 9 条目**：deadline 触发时，`results[f"gate_{n}"]` 为当前 Gate 写失败条目、为所有剩余 Gate 写 `passed=False, errors=["全局墙钟预算耗尽/跳过"]`。原方案 3b 的 `break` 直接跳出导致后续条目缺失，`all(r["passed"] ...)` 与报告打标判断双双失效——v2 以"补写条目"修复。
2. **报告组装无条件执行**：现有 report 组装（qual_v8/workflow.py:365-374）在 Gate 循环外、`break` 后仍会执行；打标逻辑基于**完整的 results** + context 中的 degraded 聚合（§2.2[5]），因此超时路径下报告必然带"未修复/降级/超时"横幅，`quality_degraded=True`。
3. **审计锚定**：每次预算触发写 audit_log（action="budget_exhausted"/"deadline_exceeded"，含 elapsed/调用数），供第三方监督核对（qual_v8 监督链不变）。

### 4.4 deadline 传入哪些函数

| 函数 | 是否接收 deadline | 方式 |
|---|---|---|
| `QualWorkflow.execute` | 计算者 | 注入 context["deadline"] |
| `Gate4AuditRepair._substantive_review` | 读 | 从 context 读，转发 |
| `review_and_repair_loop` | 收 | 新参数 `deadline=None` |
| `_run_substantive_review` / `_repair_chapters` | 收 | 新参数 `deadline=None` |
| `create_harness_caller` | 收 | 新参数 `deadline=None`（审查 caller 构造时传入） |
| 入口 runner 构造的主 caller | 不直接收 | 由 L1 `_deadline_guard` 包覆预检；在途上限由 harness 300s 兜底 |

---

## 5. 数据流改造（谁传谁收）

### 5.1 新增/变更参数总表

| 参数 | 新增位置 | 默认 | 谁传（源头） | 谁收（消费） |
|---|---|---|---|---|
| `deadline` | context + 4 个函数签名 | 无（L1 计算） | workflow.execute → context → gate4 → loop → 子函数；harness_llm 构造参数 | L1/L2/L3/L4 全部检查点（§4.2） |
| `enable_debate` | WorkflowConfig + context + loop 签名 | **False**（裁决 b） | WorkflowConfig → context["enable_debate"] → gate4 → loop | `_run_substantive_review` 第 5 步辩论块：False 时整体跳过 |
| `review_caller_override` | loop 签名 | False | gate4 恒传 True（P0-B#14：外部注入为权威，loop 禁止自建裸 caller） | `_run_substantive_review`：决定审查 caller 来源 |
| `review_caller` | context + loop 签名 | None | 入口 runner 构造（REVIEW_SYSTEM + 同一 fallback 策略包覆）→ context → gate4 | loop：override=True 时优先使用，保留审查专用 system |
| `llm_call_budget` | context + loop 签名 | 60（config） | workflow → context["llm_call_budget"] → gate4 | loop 构造 budgeted caller，**透传全链**（P0-B#6） |
| `shadow_skip_repair` | context（保留原字段） | True | workflow 按 qual_mode 写入 | gate4 读取：shadow+flag → 跳过修复循环（P0-B#9） |
| `llm_caller` | context（不变） | — | runner（fallback 包装）→ L1 包 deadline guard | gate4 → loop → 修复/审查主链路 |

### 5.2 关键链路

```
run_xpev_full / run_qual_full
  ├─ llm_caller   = fallback(create_harness_caller())            → context["llm_caller"]
  ├─ review_caller = fallback(create_harness_caller(system=REVIEW_SYSTEM, deadline=…))
  │                                                              → context["review_caller"]   （P1#14）
  └─ fallback 闭包内：滑动窗口 + 确定性失败换路由单次逃生（P0-B#8/#10）

QualWorkflow.execute
  ├─ deadline = monotonic() + global_timeout_seconds             → context["deadline"]
  ├─ context["llm_caller"] = _deadline_guard(原 llm_caller, deadline)
  ├─ context["enable_debate"] / ["llm_call_budget"] / ["shadow_skip_repair"]
  └─ Gate 循环（RETRY_POLICY 常量表驱动重试）→ Gate4 → _substantive_review

gate4._substantive_review（fail-closed：无 caller / 异常 → passed=False）
  └─ review_and_repair_loop(
         chapters, ctx, llm_caller=context["llm_caller"],
         wind_data=…, max_rounds=3, industry=…,
         review_caller=context["review_caller"],
         review_caller_override=True,
         enable_debate=context["enable_debate"],
         llm_call_budget=context["llm_call_budget"],
         deadline=context["deadline"])

review_and_repair_loop（§3 状态机）
  ├─ 构造 budgeted caller（计数 ≤ llm_call_budget + deadline 预检）
  ├─ _run_substantive_review(..., review_caller, review_caller_override,
  │                          enable_debate, budgeted_caller, deadline)   ← 全链透传（P0-B#6）
  │     └─ check_depth / check_conclusion / DebateService(仅 enable_debate=True)
  │        ← 均使用 budgeted+deadline 感知的 review_caller
  └─ _repair_chapters(..., deadline)（llm_caller 已 budgeted+deadline 感知）

tools/finance/workflow.py::_generate_chapter（Gate3 分章生成，P0-B#4）
  ├─ 新增 deadline 参数（透传）
  └─ except DeterministicLLMFailure: 不格式重试 → 降级章节 + 内嵌标记
```

---

## 6. P0/P1 边界重划（18 项修正清单落地矩阵）

### 6.1 清单 → 落点 → 阶段

| # | 修正项 | 落点（文件/层） | 阶段 | 在本文档的位置 |
|---|---|---|---|---|
| 1 | 豁免 fail-open（passed=True 禁止；签名保留章节号；计入 remaining） | review_repair_loop（L3 状态机 S2/S3/DEGRADE） | **P0-A** | §3.1/§3.2；裁决 a |
| 2 | gate4 无 caller 第二条 fail-open → passed=False | gate4.py（L2） | **P0-A** | §1/§2.2 |
| 3 | 豁免学习证据护栏（≥3 轮+无修复迹象+审计+报告注明豁免数） | review_repair_loop（S6 + 审计） | **P0-A** | §3.1/§1 横切 B |
| 4 | `_generate_chapter` 外层重试吞确定性失败 | tools/finance/workflow.py（L3 上游） | **P0-B** | §2.2[4] |
| 5 | debate 无条件运行 → `enable_debate` 默认 False | review_repair_loop + gate4 + WorkflowConfig | **P0-B** | §5.1；裁决 b |
| 6 | `_budgeted_caller` 死代码 → 透传全链 | review_repair_loop / _run_substantive_review | **P0-B** | §5.1/§5.2 |
| 7 | 墙钟只查 Gate 边界 → deadline 调用级注入 | harness_llm + loop + workflow | **P0-B** | §4.2；裁决 d |
| 8 | 确定性失败无逃生 → 换路由单次重试，仍败降级+打标 | 入口 runner fallback | **P0-B** | §2.2[3]/[5]；裁决 c |
| 9 | `shadow_skip_repair` 无消费方 → gate4 读标志 | gate4.py | **P0-B** | §5.1 |
| 10 | fallback 切换只查成功分支 → 移入 except 分支 | run_xpev_full / run_qual_full | **P0-B** | §2.2[3] |
| 11 | 缺 DeterministicLLMFailure 导入 + run_qual_full 同步 | 两个 runner | **P0-B** | §1 L0 |
| 12 | `LLM_EMPTY_OUTPUT` 补入 ERROR_CODE_MAPPING（permanent/retry=False） | error_classifier.py | **P1** | §2.2[6] |
| 13 | 熔断阈值 2（或持久化计数）；BUSINESS 不计入 | circuit_breaker.py + workflow 构造 | **P1** | §2.2[6]/§7 |
| 14 | 审查 caller 保留 REVIEW_SYSTEM（外层包 fallback，不裸复用） | runner 构造 review_caller + loop 消费 | **P1** | §1 L0/§5 |
| 15 | 单调守卫：签名差集 + 前后同口径 + deepcopy 快照 | review_repair_loop（S5） | **P1** | §3.1/§3.2；裁决 e |
| 16 | 实施顺序（先改 loop 签名再改 gate4 调用）+ 新逻辑单测 | 实施计划 | **P1** | §8 |
| 17 | 改动 7 删除或标注"验证性，无需重建插件" | llm-bridge.js（实证已具备 finishReason） | 清理 | §1 L5 |
| 18 | 统一 enforce/soft/shadow 重试语义为单一常量表 | qual_v8/workflow.py RETRY_POLICY | 清理 | §1 L1 |

### 6.2 P0/P1 阶段定义（v2 重划）

- **P0 止血（11 项，先实施）**：P0-A 3 项（fail-open 堵漏，最先）+ P0-B 8 项（止血）。判定标准：不落地则"死循环"或"静默产出"任一仍可能发生。
- **P1 架构（5 项）**：熔断修复、审查 caller 保留 REVIEW_SYSTEM、单调守卫签名差集、实施顺序与单测。判定标准：P0 落地后系统已安全有界，P1 提升正确性与可观测性。
- **清理（2 项）**：不产生新代码行为（#17 实证确认无改动；#18 常量表合并）。
- **实施顺序（#16）**：先改 `review_repair_loop` 签名与状态机 → 再改 gate4 调用（避免改调用方时目标签名未定）；`llm_errors.py` 契约先行；每步配单测（确定性失败 0 重试、豁免不 pass、deadline 触发 results 完整性、单调回滚、budget 截断）。

---

## 7. 与原方案相比的架构变化点

| # | 维度 | 原方案 | v2 修订 | 依据 |
|---|---|---|---|---|
| 1 | 预算模型 | 独立时钟（Gate 顶部检查 + timeout_per_gate + call timeout） | **单一 deadline 主源 + 4 层检查点**；per-call 有效超时 = min(调用超时, 剩余) | 裁决 d（P0-B#7） |
| 2 | results 完整性 | 3b `break` 后缺条目，打标失效 | 超时/预算终止必须补写当前+剩余 Gate 条目（恒 9 条） | 裁决 d |
| 3 | 豁免语义 | 剔除后 `not round_issues → passed=True`（fail-open） | 豁免仅降级；PASS 需"排除豁免后为空 **且** 豁免清单为空"；豁免 ≥3 轮证据护栏 + 审计 | 裁决 a（P0-A#1/#3） |
| 4 | 确定性失败路由 | 仅 harness 层不重试，外层仍吞并重试 | 全链非重试 + L0 换路由单次逃生 + 逐层降级打标 + 熔断 permanent 类 | 裁决 c（P0-B#4/#8） |
| 5 | 单调守卫 | 数量比较（`after > before` 回滚） | 签名差集（after ⊄ before）+ 前后同口径 + deepcopy 快照 | 裁决 e（P1#15） |
| 6 | debate | 无条件运行（3 章×多角色×240s，~72min/轮） | `enable_debate` 门控默认 False | 裁决 b（P0-B#5） |
| 7 | 审查 caller | 5c 裸复用主 caller（丢 REVIEW_SYSTEM） | runner 构造 review_caller（REVIEW_SYSTEM+fallback）注入；loop 禁止自建 | P1#14 |
| 8 | 熔断 | 双枚举跨类恒 False；权重 0.5 不可达；BUSINESS 计入 | 单一枚举源；LLM_EMPTY_OUTPUT permanent；阈值 2；BUSINESS 不计入 | P1#12/#13 |
| 9 | 预算调用计数 | `_budgeted_caller` 设计未接 | budgeted caller 透传 _run_substantive_review 全链（depth/conclusion/debate/repair） | P0-B#6 |
| 10 | 桥接 | 改动 7 补 finishReason（no-op） | 删除改动，标注验证性确认 | 清理#17 |
| 11 | 重试语义 | 各模式手写 if/elif 分支 | 单一 RETRY_POLICY 常量表 | 清理#18 |

---

## 8. 验收标准修订（机制自洽版）

### 8.1 指标

| 指标 | 原目标（不达标） | v2 目标（与机制自洽） | 验证方式 |
|---|---|---|---|
| 终止性 | ≤30-40 分钟 | **任何运行 ≤ 全局 deadline（默认 90 分钟）+ 单次在途上限（300s）**；无无界卡死 | 注入确定性失败假 caller 回归：断言运行结束且 0 次同模型重试 |
| LLM 空输出重试 | 0 次重试 | **同模型重试 = 0；换路由单次逃生 ≤ 1**（106 次失败 → 至多 106 次单路由调用，不再 ×3） | harness_llm 单测（分类断言） |
| Gate4 收敛 | 问题数不降即早停（1-2 轮） | 早停 ≤2 轮；豁免清单非空 → **passed=False + 报告注明豁免数**；无 caller/审查异常 → Gate4 失败 | 状态机单测（DEGRADE/EARLY_STOP/T_REVIEW_FAIL 出口断言） |
| 审查-修复闭环 | 清单驱动 + 单调性 + 豁免 | 签名差集单调守卫 + 同口径重审 + deepcopy 回滚；回归注入"修复 A 引入 B"断言回滚 | 单调守卫单测 |
| shadow 语义 | 单次执行 + 报告打标 | shadow+skip_repair：修复循环跳过；任何降级路径报告必带"未修复"标 + quality_degraded=True（results 恒 9 条） | 打标断言（9 条目 + 横幅存在） |
| 正常路径时长 | 30-40 分钟 | **shadow + debate 关闭 + 确定性失败路由：目标 ≤ 60 分钟**（硬兜底 = deadline） | 实测小鹏 + 日志时间戳审计 |

### 8.2 debate 关闭 + 确定性失败路由后的可达时长推导

原 6h+ 卡死的构成：**106 次 max-tokens 空输出 ×（harness 3 尝试 + 外层格式重试 3 次）** + **50-88 项假阳性 × 3 轮 × 每轮全量重审** + **debate 3 章 × 多角色 × 240s × 重试（约 72 分钟/轮）** 三者相乘。

v2 修复后逐项消除：
1. 确定性失败 → 0 次同模型重试（106 次失败从 106×9 次调用降为 ≤106 次调用+≤106 次单路由逃生）；
2. 假阳性 → 收敛状态机在 1-2 轮内以 DEGRADE/EARLY_STOP 终止（有界），且豁免学习不再为假阳性投入第 4+ 轮修复；
3. debate → 关闭（72 分钟/轮 → 0）。

**Gate4 时长上界 = min(60 调用预算 × 单调用时长, deadline 剩余)**；debate 关闭后每轮实质审查约 3-5 次 LLM 调用（depth/conclusion 等），正常 2 轮 ≈ 10-25 分钟。整链（Gate0-8）正常路径 **40-60 分钟**，最坏路径由 deadline 硬性封顶 **≤ 90 分钟 + 300s**。原先"≤30-40 分钟"不可达的原因（HeavySkill 教训 4）：未关 debate（72min/轮）且 60×300s 调用上限与 30-40 分钟直接矛盾——v2 以"deadline 硬上限 + 正常路径软目标"替代，指标与机制自洽。

---

## 9. 不变量清单（防矛盾约束，代码专家必须遵守）

1. **单一时间主源**：全局 deadline 之外禁止任何独立墙钟计数器；per-call 超时必须是派生值（消解预算/超时冲突）。
2. **豁免与 fail-closed 不冲突**：豁免永不产生 `passed=True`；PASS 的唯一条件 = 排除豁免后为空 **且** 豁免清单为空。
3. **确定性失败全链非重试**：任何 `except Exception` 之前必须有 `except DeterministicLLMFailure` 分流；逃生重试必须换路由且 ≤1 次。
4. **results 恒 9 条目**：预算/超时终止必须补写当前与剩余 Gate 条目；报告打标依赖完整 results。
5. **单调守卫同口径**：before/after 用同一审查管线、比较原始签名集合（不受豁免剔除影响）。
6. **单一枚举源**：`ErrorType` 只允许 error_classifier.py 定义一次，circuit_breaker 导入复用（消除跨类恒 False）。
7. **审查 caller 保留 REVIEW_SYSTEM**：禁止裸复用主 caller 作审查；fallback 策略由 runner 在外部统一包覆。
8. **budgeted caller 全链透传**：调用计数必须覆盖实质性审查与修复的所有 LLM 调用（含 depth/conclusion/debate/repair），不允许绕过。
