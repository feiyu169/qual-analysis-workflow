# qual v8 死循环修复——修订后架构设计（v3）

日期：2026-08-19（v3 修订，同日）
依据：
- `docs/qual-loop-fix-design-v2-arch.md`（v2 架构分册，本册修订基线）
- `docs/heavyskill-v2-review.md`（二次审查报告：7 项修正清单；最终判定"需修改后通过"）
- 综合审议裁决细节（会话记录：缺陷 16 正则验证、豁免 PASS 绕过、deadline、熔断、预算）

定位：本文档只含**架构层面**设计（分层、路由、状态机、预算、数据流、边界、验收、不变量）。逐行代码设计由代码专家按本文档落地（v3-code 分册，与本文档并行修订）。
范围：v2 的 18 项修正全部保留 + v3 二次修正 5 组：
- **P0-A-1/2/3**（架构状态机同步）：签名保留章节号的正则链顺序；豁免 PASS 判据改查累积豁免清单；单调守卫 before/after 均取原始签名集 + fixed_count 净修复语义
- **P0-B-1**（deadline 落点明确）：`_deadline_guard` 包覆主 caller（fallback 外层）+ 逃生直连预检；harness 层**不**加 deadline 参数；验收上界改为与实现一致的可证明表述
- **P0-B-2**（arch/code 三处矛盾，按裁决执行）：review_caller 构造位置**采纳 code 侧**（loop 内部 `_build_review_caller` 自建，删除 runner 注入链 + `review_caller_override`）；enable_debate 统一为 **gate4 硬编码恒 False**；异常命名统一为 **`WallClockDeadlineExceeded`**
- **P0-B-3**（架构不变量同步）：熔断必须可触发（阈值 < gate_attempts 或跨 run 持久化）；文本兜底分类不默认计入熔断
- **P1-1**（预算错配）：`max_llm_calls_per_gate` 提高至默认 **300**（≥200 裁决底线）**且** S5 重审不计入预算计数；修正 §8.2"每轮 3-5 次"错误推导（实测 27-50 次/轮）

---

## 0. 架构原则（v3 修订后）

1. **先分类，后路由，重试是例外**：错误四分类；只有 TRANSIENT 可同模型重试；DETERMINETIC 全链非重试，只允许"换路由单次逃生"，仍败即降级+打标（裁决 c）。
2. **单一时间主源**：全局墙钟 deadline 是唯一时间预算；per-call 超时与 per-gate 时长均为其派生值。**v3 强化：deadline 预检必须覆盖所有 LLM 调用入口（主 caller、审查/修复链、逃生直连），"deadline + 在途上限"上界方可证明**（裁决 d + P0-B-1）。
3. **fail-closed 是缺省语义**：任何非 PASS 出口（豁免、早停、预算、超时、审查异常、最大轮数）一律 `passed=False` + 打标；豁免永不产生通过。**v3 修订：PASS 判据查"累积豁免清单为空"（`not any(e["exempted"] for e in exempted.values())`），堵 v2 仅查"本轮剔除集"的绕过**（裁决 a + P0-A-2）。
4. **降级必须带语义标记且标记必须到达报告**：results 恒 9 条目 + 每层降级点打标 + 报告聚合横幅，杜绝静默产出（裁决 d）。
5. **单调性用签名差集判**：**v3 修订：before/after 均取"原始签名集合"（不受豁免剔除影响）**；前后同口径 + deepcopy 快照；`issues_fixed` 为净修复数（回滚时先减后置零）（裁决 e + P0-A-3）。
6. **辩论能力本版本恒关闭（v3 修订）**：v2 称"`enable_debate` 默认 False、config 可驱动"——v3 明示**恒 False**：gate4 调用 loop 时硬编码 `enable_debate=False`，WorkflowConfig 不再驱动该项；loop 签名保留参数（默认 False）仅为 legacy 兼容与未来扩展（裁决 b + P0-B-2）。
7. **单一契约源**：错误枚举、重试语义、豁免规则各只定义一次。**v3 修订：异常命名统一为 code 侧 `DeterministicLLMFailure` / `WallClockDeadlineExceeded` / `LLMCallBudgetExceeded`（唯一定义于 `tools/finance/llm_errors.py`，前两者为父子类关系）**；`ErrorType` 唯一定义于 error_classifier.py（P0-B-2）。
8. **审查 caller 单一构造点（v3 新增）**：审查专用 caller 只允许在 loop 内部 `_build_review_caller` 自建（REVIEW_SYSTEM + `with_fallback` + budgeted，与修复共享同一 budget_state）；runner 不注入 review_caller，无任何 override 参数（P0-B-2，采纳 code 侧）。

---

## 1. 修订后的分层架构（v3）

```
┌──────────────────────────────────────────────────────────────────────┐
│ L0 入口层  run_xpev_full.py / run_qual_full.py                        │
│   改造：① 【v3】不再构造 review_caller（构造点移至 L3 _build_review_   │
│          caller，采纳 code 侧——P0-B-2）；仅构造主 llm_caller：          │
│          with_fallback(create_harness_caller(), 直连工厂)（P1#14 语义  │
│          由 L3 自建满足）                                              │
│        ② fallback 滑动窗口：切换判定移入 except 分支，全故障场景可切换  │
│          （P0-B#10）；确定性失败→换路由单次逃生（P0-B#8）                │
│        ③ 补 DeterministicLLMFailure/with_fallback 导入 +              │
│          run_qual_full 与 run_xpev_full 收敛为同一表达式（P0-B#11/#12）│
└──────────────────────────────┬───────────────────────────────────────┘
                               │ llm_caller（with_fallback 包装）
┌──────────────────────────────▼───────────────────────────────────────┐
│ L1 引擎层  qual_v8/workflow.py（QualWorkflow.execute）                 │
│   改造：① 【deadline 注入层·入口】计算全局 deadline（monotonic 绝对     │
│          时间戳）→ context["_wall_deadline"]；【v3 落点·P0-B-1】主       │
│          caller 外包 _deadline_guard（在 with_fallback 外层，覆盖       │
│          Gate3 主链路 _generate_chapter 的一切调用）                    │
│        ② Gate 循环顶部 deadline 检查 + _fill_failed_gates 补写当前与   │
│          剩余 Gate 的 skipped 条目（results 恒 9 条）                   │
│        ③ 重试语义单一常量表 RETRY_POLICY（shadow/soft/enforce）（#18）  │
│        ④ 熔断记录改用单一枚举源 + 可达阈值；【v3 同步·P0-B-3】熔断必须   │
│          可触发（阈值 < gate_attempts 或跨 run 持久化），文本兜底分类    │
│          不默认计入                                                   │
│        ⑤ 失败后报告打"未修复"标 + quality_degraded（含豁免数/超时）      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ context: llm_caller（deadline_guard 包覆）/
                               │   _wall_deadline / llm_call_budget /
                               │   shadow_skip_repair / _llm_call_count
┌──────────────────────────────▼───────────────────────────────────────┐
│ L2 Gate 层  qual_v8/gates/gate4.py（Gate4AuditRepair）                 │
│   改造：① fail-closed 双堵漏：无 caller→passed=False（P0-A#2）；        │
│          实质审查异常→passed=False（不再返回 True）                     │
│        ② 消费 shadow_skip_repair：shadow 模式跳过修复循环（P0-B#9）     │
│        ③ 传参：【v3】enable_debate=False（硬编码恒 False，无 config     │
│          驱动——P0-B-2）/ llm_call_budget / deadline；【v3】不再传       │
│          review_caller（loop 内部自建）                                │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────┐
│ L3 审查-修复循环层  quality/review_repair_loop.py                      │
│   改造：① 【收敛状态机】豁免证据护栏 + 早停 + 单调守卫 + 预算检查        │
│          （§3；P0-A#1/#3、P1#15）——【v3】PASS 判据=累积豁免清单为空；    │
│          单调守卫 before/after 均取原始签名集                          │
│        ② 【v3】enable_debate 恒 False（gate4 硬编码），辩论块永不执行    │
│        ③ budgeted caller 透传全链（P0-B#6）；deadline 轮首/调用前检查    │
│          （P0-B#7）；【v3】S5 重审不计入预算计数（P1-1）                 │
│        ④ 【v3】审查 caller 由 loop 内部 _build_review_caller 自建：     │
│          REVIEW_SYSTEM → with_fallback → _make_budgeted_caller          │
│          （同一 budget_state）——采纳 code 侧，删除 runner 注入链         │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ 有效超时 = min(调用超时, deadline 剩余)
                               │ （budgeted/guard 预检已保证发起时剩余>0）
┌──────────────────────────────▼───────────────────────────────────────┐
│ L4 LLM 调用层  harness_llm.py（create_harness_caller）                 │
│   改造：① 失败分类四类（§2 决策表）                                    │
│        ② 【v3 修正·P0-B-1】不新增 deadline 参数：调用级 deadline 预检    │
│          由 L1 _deadline_guard（主链路）与 L3 _make_budgeted_caller     │
│          （审查/修复链）完成；harness 自身 timeout=300s 即"单次在途      │
│          上限"，是 deadline 上界推导中的唯一超支项                       │
│        ③ DeterministicLLMFailure 不重试（重试循环前置分流）             │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ /api/llm-bridge（finishReason 语义已具备，
                               │   llm-bridge.js:56-64 实证；清理#17：标注验证性，无需重建）
┌──────────────────────────────▼───────────────────────────────────────┐
│ L5 宿主桥接  plugins/llm-bridge.js（验证性确认，无改动）                │
└──────────────────────────────────────────────────────────────────────┘

横切层（跨 L1-L4）：
  A. 【deadline 注入层】单一绝对 deadline 沿 context 下传，【v3】4 个强制检查点：
     L1 Gate 循环顶部（冗余层）→ L1 主 caller 调用前（_deadline_guard，
     【v3】含逃生直连调用前预检）→ L3 轮首（S0）→ L3 单调用前
     （_make_budgeted_caller，审查 caller 同源）（§4.2）
  B. 【豁免证据护栏层】L3 内：≥3 轮 + 无修复迹象 + 审计记录 + 报告注明豁免数；
     【v3】PASS 判据与 DEGRADE 触发均以"累积豁免清单"为准（P0-A-2）
  C. 【v3】enable_debate 门控：gate4 硬编码 False，恒关闭；无 config 驱动路径
     （原 v2 横切 C"WorkflowConfig → context → gate4 → loop"删除）
  D. 【确定性失败路由】L4 分类 → 全链不重试 → L0 换路由单次逃生 → 逐层降级打标
     （§2 链路；【v3】逃生直连调用前必须过 deadline 预检）
```

**新增职责一览**（对比 v1 原方案；标注 v3 修正）：

| 层 | v1 原方案职责 | v2 新增职责 | v3 修正 |
|---|---|---|---|
| L0 入口 | 构造 llm_caller（含 fallback） | 构造 review_caller（REVIEW_SYSTEM+fallback）注入 | **删除 runner 注入 review_caller**（构造点移至 L3）；fallback 移入 except；换路由单次逃生；双 runner 同步 |
| L1 引擎 | Gate 循环顶部墙钟检查、shadow 降重试、报告打标 | deadline 注入层入口；results 恒 9 条目；RETRY_POLICY；熔断单一枚举+可达阈值 | **`_deadline_guard` 包覆主 caller（P0-B-1 明确落点）**；熔断可触发同步（P0-B-3） |
| L2 Gate4 | fail-closed 一半（仅异常） | 双 fail-open 堵漏；shadow_skip_repair 消费；全参透传（含 review_caller/override） | **enable_debate 恒 False 硬编码；删除 review_caller/override 传参** |
| L3 循环 | 收敛早停+豁免+单调守卫（数量比较） | 收敛状态机；enable_debate 门控；budgeted 全链透传 | **PASS 判据=累积豁免清单；单调守卫原始签名集；S5 不计预算；`_build_review_caller` 自建审查 caller** |
| L4 调用层 | 分类+确定性不重试 | deadline 参数（有效超时派生） | **删除 deadline 参数**（预检由上层 guard/budgeted 完成） |
| L5 桥接 | finishReason 语义补全（改动 7） | 删除，降为验证性确认 | 不变 |

---

## 2. 错误分类与路由决策表（v3）

### 2.1 四类错误 × 处理策略 × 消费方

| 错误类 | 判定源（L4 分类） | 处理策略 | 重试语义 | 消费方 |
|---|---|---|---|---|
| **TRANSIENT** 瞬态 | 网络异常（URLError/ConnectionError/TimeoutError）；`ok=False, finish=error/null` | 同模型退避重试 | L4 内重试 ≤2 次 + 指数退避；L0 fallback 滑动窗口计数（切换判定移入 except）；L1 Gate 级重试 | harness_llm / fallback / workflow Gate 循环 |
| **DETERMINISTIC** 确定性 | `ok=False, finish=max-tokens 且 text 空`；格式契约违反；deadline 耗尽（**`WallClockDeadlineExceeded`**，DeterministicLLMFailure 子类）；预算耗尽（**`LLMCallBudgetExceeded`**，同族终止性异常） | **不重试**；只允许 L0 换路由（直连/换模型）**单次**逃生；仍败 → 降级+打标 | L4/L3/L2/L1 各级循环一律 0 次同模型重试（`except DeterministicLLMFailure: raise` 前置分流）；逃生重试 ≤1 次且必须换路由，**【v3】逃生调用发起前必须过 deadline 预检** | 全链（§2.3 完整链路） |
| **SEMANTIC** 语义 | `ok=True` 但内容不合格（格式校验失败/审查发现的问题/patch 校验失败） | 业务处理：格式修正重写、修复循环 | 业务层自有上限（max_format_retries、max_rounds）；**不再计为 LLM 调用失败**，不计入熔断 | _generate_chapter / review_repair_loop / patch_applier |
| **CIRCUIT_OPEN** 熔断打开 | 熔断器状态 == OPEN 且冷却期未过 | 跳过执行 | 0 次；冷却期后 HALF_OPEN 单次探测 | L1 Gate 循环顶部 `can_execute()` |

**【v3·P0-B-3】熔断可触发不变量**：enforce 模式 `gate_attempts=2` 与熔断阈值 2 同步耗尽会导致 `can_execute()` 永不返回 False（功能性死亡）。架构要求：熔断计数必须**跨 run 持久化**，或阈值满足 `failure_threshold < gate_attempts`，保证第 2 次尝试前 `can_execute()` 已能短路；文本兜底（`UNKNOWN_ERROR`）**不默认计入熔断**（确定性/终止性语义由类型识别或关键词识别显式映射，BUSINESS 不计入）。

### 2.2 DeterministicLLMFailure 完整链路（v3）

```
[1] 产生    harness_llm._call_bridge 返回 ok=False, finish=max-tokens, text 空
            → raise DeterministicLLMFailure(finish_reason="max-tokens", model=...)
            deadline 剩余≤0（guard/budgeted 预检）→ raise WallClockDeadlineExceeded
            （DeterministicLLMFailure 子类；【v3】统一命名，v2 的
            DeadlineExceeded/DeadlineExceededError 全部弃用）
            预算超限（budgeted 计数）→ raise LLMCallBudgetExceeded（同族终止性异常）

[2] 不重试   L4 重试循环: except DeterministicLLMFailure: raise（0 次同模型重试）

[3] 逃生     L0 with_fallback: except DeterministicLLMFailure:
              · 滑动窗口记 True（提示任务-模型错配）
              · 若可换路由（桥接→直连 deepseek-chat，或换非推理模型）→ 单次重试
                · 【v3】逃生调用发起前先过 deadline 预检（剩余≤0 → 直接
                  raise WallClockDeadlineExceeded，不再发起在途超支）
                · 成功 → 返回文本（窗口不清零，保持滑动语义）
                · 失败 → re-raise（携带已尝试路由）
              · 无可用路由 → re-raise
            （禁止：同模型、同路由重试；禁止把确定性失败按 TRANSIENT 退避）

[4] 上层不吞  所有 except Exception 之前必须前置 except DeterministicLLMFailure
              （白名单含 WallClockDeadlineExceeded / LLMCallBudgetExceeded）：
              · tools/finance/workflow.py::_generate_chapter（P0-B#4）：
                不进入格式重试循环 → 直接降级为"数据不足"章节 + 内嵌确定性失败标记
              · review loop / _repair_chapters：该章/该项跳过 + 记录 degraded
              · qual_v8/workflow.py Gate 循环（原 277-284 except Exception）：
                不 Gate 重试 → 熔断记录 permanent → Gate 判失败 → break

[5] 降级+打标 每层降级点必须打标，标记沿 context 聚合到报告：
              · 章节级：内容内嵌 <!-- ⚠️ 确定性失败: finish/model -->，计入 degraded_chapters
              · 审查级：审查 LLM 维度失败 → 该维度跳过 + 计入 degraded_count；
                        同一 Gate 内审查 LLM 失败 ≥3 次或关键维度（结论合理性）失败
                        → Gate4 强制 passed=False（fail-closed）
              · 修复级：该章不修复，计入 remaining_issues（不豁免）
              · Gate 级：Gate passed=False + errors 记录（enforce 模式 → ComplianceBlockedException）
              · 报告级：L1 组装 report 时聚合所有 degraded 标记（章节/豁免/Gate 失败/预算超时）
                        → 统一"质量降级"横幅 + context["quality_degraded"]=True

[6] 熔断      Gate 循环将最终上抛的确定性/终止性异常（含 WallClockDeadlineExceeded、
              LLMCallBudgetExceeded）经 ErrorClassifier 分类为 LLM_EMPTY_OUTPUT
              （permanent, retry=False）→ 熔断计数 +1 → 【v3】跨 run 持久化或
              阈值 < gate_attempts，保证 can_execute() 真能返回 False（P0-B-3）
```

**决策表对应关系**：`DeterministicLLMFailure`/`WallClockDeadlineExceeded`/`LLMCallBudgetExceeded` 的判定源 = L4（max-tokens 空）或 L1/L3 预检（deadline/预算）；策略 = 不重试+换路由单次+降级打标；消费方 = 全链。

---

## 3. 审查-修复循环的收敛状态机（v3）

### 3.1 状态与转换（L3，review_and_repair_loop）

```
                    ┌──────────────────────────────────────────────┐
                    │ S0 IDLE（轮首）                                │
                    │ ① deadline 剩余 ≤0 → T_DEADLINE               │
                    │ ② 调用计数 ≥ 预算上限（默认 300）→ T_BUDGET     │
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
                    │ S2 EXEMPT-FILTER：签名（保留章节号，P0-A#1）    │
                    │  【v3 正则链顺序】：findall 捕获章节号 → 归一化  │
                    │  其余数字 → replace("第N章", "第@{ch}章") 还原   │
                    │  （占位符内的章节号不得被再次归一化；跨章同形    │
                    │  问题 → 不同签名）                              │
                    │  签名 ∈ 累积豁免（entry["exempted"]）→          │
                    │    exempted_pool（计入 remaining）              │
                    │  否则 → kept                                    │
                    └──────────────────────┬───────────────────────┘
                                           │
                    ┌──────────────────────▼───────────────────────┐
                    │ S3 CONVERGENCE（收敛判定，fail-closed 缺省）    │
                    │  kept=∅ ∧ 累积豁免清单为空 → PASS ✅           │
                    │  kept=∅ ∧ 累积豁免清单非空 → DEGRADE ❌        │
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
                    │  【v3】before/after 均取原始签名集合（不受豁免  │
                    │  剔除影响）：                                   │
                    │   before_sigs = S1 轮首全量审查原始签名集       │
                    │   after_sigs  = 修复后同口径全量重审原始签名集   │
                    │  new_sigs = after_sigs − before_sigs           │
                    │  new_sigs ≠ ∅ 或 |after|>|before| → ROLLBACK   │
                    │   （恢复快照；issues_fixed 先减后置零——净修复    │
                    │    语义；记录回归）→ 继续 S6                    │
                    │  无新签名 → 接受修复                            │
                    └──────────────────────┬───────────────────────┘
                                           │
                    ┌──────────────────────▼───────────────────────┐
                    │ S6 EXEMPT-LEARN（证据护栏，P0-A#3）            │
                    │  签名出现 ≥3 轮 ∧ 从未被成功修复（sig ∉        │
                    │  fixed_sigs）→ entry["exempted"]=True + 审计   │
                    │  （签名/首末轮/证据/涉及章节）                  │
                    └──────────────────────┬───────────────────────┘
                                           │ round < max_rounds → S0
                                           │ round == max_rounds → T_MAXROUNDS ❌
```

### 3.2 出口语义（fail-closed 标注）

| 出口 | 触发条件 | passed | 标记/副作用 |
|---|---|---|---|
| **PASS** ✅ | kept=∅ **且 累积豁免清单为空**（`not any(e["exempted"] for e in exempted.values())`） | **True** | 唯一 True 出口；无标记 |
| **DEGRADE** ❌ | kept=∅ 但**累积豁免清单非空** | False | remaining_issues=exempted 项；报告注明豁免数；quality_degraded=True（裁决 a） |
| **EARLY_STOP** ❌ | 问题数不降且上轮修复=0 | False | remaining_issues=kept[:10]；打标 |
| **T_REVIEW_FAIL** ❌ | 审查 LLM 降级达阈值（≥3 或关键维度） | False | errors="审查能力降级"；打标 |
| **T_DEADLINE** ❌ | 轮首 deadline 剩余 ≤0 | False | 打标"全局墙钟预算耗尽" |
| **T_BUDGET** ❌ | 调用计数 > 预算上限（默认 **300**，v2 为 60） | False | 打标"单 Gate 调用预算耗尽"（S5 重审不计入） |
| **T_MAXROUNDS** ❌ | round 达 max_rounds 仍有 kept | False | remaining_issues；打标 |

**豁免语义（裁决 a + P0-A-2 落地）**：豁免只做三件事——(1) 停止对该签名问题的**修复投入**；(2) 将其移入 exempted_pool 随结果返回并计入报告；(3) 在审计日志留痕。**v3 判据修订**：v2 的 PASS 判据检查"本轮被剔除的豁免项（exempted_pool）"，存在绕过——豁免学习置 `entry["exempted"]=True` 后，若该签名后续轮不再报出，exempted_pool 为空、kept 为空 → 误判 PASS（test_exemption_failclosed 必红）。v3 改查**累积豁免清单**（任何 entry 已 `exempted=True` 即非空）→ 该场景仍走 DEGRADE（passed=False）。豁免与 fail-closed 由此彻底不冲突：豁免终止的是循环（有界），而非通过语义（仍是 False）。

**单调守卫（裁决 e + P1#15 + P0-A-3）**：轮首 `chapters_snapshot = deepcopy(chapters)`；修复后对当前内容用**同一管线**（S1 完全相同调用序列）重审；**【v3】before_sigs 与 after_sigs 均取原始签名集合**（before 为 S1 全量审查结果，未经豁免剔除；v2 曾对 before 做剔除过滤造成口径不对称）。回归判定 = `new_sigs = after_sigs − before_sigs ≠ ∅` 或问题总数上升 → 回滚；**【v3】`issues_fixed` 修正**：v2-code 回滚分支 `fixed_count = 0; issues_fixed -= fixed_count` 因顺序错误为 no-op（计数虚高，test_monotonic_guard 必红）——v3 语义为"先减后置零"：`issues_fixed -= fixed_count` 之后才 `fixed_count = 0`，`issues_fixed` 恒为净修复数。

---

## 4. 预算体系设计（v3）

### 4.1 预算结构与优先级

| 预算 | 类型 | 默认 | 作用域 | 触发行为 |
|---|---|---|---|---|
| **全局墙钟 deadline**（主预算） | 绝对 monotonic 时间戳 | 5400s（90 分钟，WorkflowConfig.global_timeout_seconds） | 整个工作流 | 任一检查点触发 → 终止当前工作单元 → fail-closed + 打标 |
| **单 Gate LLM 调用次数**（次预算） | 计数器 | **300**（v2 为 60；裁决底线 ≥200；以 code 分册最终值为准，须 ≥200 且不误伤正常路径） | 单个 Gate（Gate4 循环） | 超过 → 抛 `LLMCallBudgetExceeded` → 终止循环 → fail-closed + 打标。**【v3】S5 单调守卫重审不计入该计数**（单列审计字段，仅受 deadline + max_rounds 约束，有界） |
| 轮数上限 max_rounds | 计数器 | 3 | 审查-修复循环 | 达上限仍有问题 → T_MAXROUNDS |

**优先级**：deadline（全局墙钟） > 调用次数（局部） > 轮数（最弱）。三者是**独立计数器**，先到先触发；任一触发都汇入同一条终止路径（fail-closed + 打标 + 审计），不存在"预算与超时冲突"——它们是嵌套的保险丝。

**【v3·P1-1 预算错配修正】**：v2 上限 60 与实测每轮 27-50 次调用（depth_reviewer + conclusion_validator + repair 实读）矛盾——正常"需第 2 轮"的报告大概率在第 1-2 轮即触发 T_BUDGET 早停打降级标（误伤）。v3 双管齐下：上限提至 300（正常 3 轮业务调用 81-150 次，留充足余量）+ S5 重审不计预算（重审是守卫开销，非业务调用；其有界性由 max_rounds × 单轮重审次数 + deadline 兜底保证）。

**时间冲突消解（裁决 d）**：全局 deadline 是唯一时间主源；per-call 超时 = `min(调用配置超时, deadline 剩余)`，per-gate 时长不再独立配置；任何组件禁止持有自己的墙钟计数器。

### 4.2 deadline 注入与检查点（v3 落点明确）

```
L1  workflow.execute 开头：deadline = monotonic() + global_timeout_seconds
    → context["_wall_deadline"]
        │
L1  主 caller：【v3·P0-B-1】context["llm_caller"] = _deadline_guard(原 llm_caller, deadline)
    （包装在 runner 的 with_fallback 外层 → 覆盖 Gate3 主链路 _generate_chapter
     等一切经主 caller 的调用；v2"create_harness_caller 加 deadline 参数"方案弃用，
     harness 层不加参数）
        │
L1  Gate 循环顶部：monotonic() > deadline → 当前 Gate 记失败 + 剩余 Gate 全补
    skipped 条目 + break（results 恒 9 条目，修 3b 缺条目/打标失效）
        │
L3  循环轮首（S0）：deadline 剩余 ≤0 → T_DEADLINE
        │
L3  单调用前：_make_budgeted_caller 内查剩余 ≤0 → 抛 WallClockDeadlineExceeded
    （审查 caller 的 budgeted 包装同源；【v3】with_fallback 的逃生直连调用发起前
     同样执行预检 —— 保证"所有 LLM 调用入口均有调用前预检"）
        │
L4  harness_llm：【v3】不新增 deadline 参数；调用前预检由上层 guard/budgeted 完成；
    harness 自身 timeout=300s 即"单次在途上限"（上界推导的唯一超支项）
```

**最坏超时上界（v3 可证明表述）**：在"所有 LLM 调用入口（主 caller、审查/修复 budgeted caller、逃生直连）发起前均执行 deadline 预检"的前提下，任何运行终止时间 ≤ **deadline + 单次最长在途调用（默认 300s）**。理由：预检通过后启动的调用是唯一可能越过 deadline 的部分，而其自身超时 ≤300s；逃生调用前同样预检，不会在 deadline 之后发起新的在途调用。该上界与实现一致，可作为验收断言（v2 声称可证明但 Gate3 主链路无调用级检查，断言不成立——v3 以 `_deadline_guard` 落地后成立）。

### 4.3 超时/预算后 results 与报告打标的完整性保证

1. **results 恒 9 条目**：deadline 触发时，`_fill_failed_gates` 为当前 Gate 写失败条目、为所有剩余 Gate 写 `passed=False, errors=["全局墙钟预算耗尽/跳过"]`（修 3b 的 break 缺条目）。
2. **报告组装无条件执行**：report 组装在 Gate 循环外、break 后仍执行；打标逻辑基于完整 results + context 中的 degraded 聚合 → 超时路径下报告必带"未修复/降级/超时"横幅，`quality_degraded=True`。
3. **审计锚定**：每次预算触发写 audit_log（action="budget_exhausted"/"deadline_exceeded"，含 elapsed/调用数），供第三方监督核对。

### 4.4 deadline 传入哪些函数（v3）

| 函数 | 是否接收 deadline | 方式 |
|---|---|---|
| `QualWorkflow.execute` | 计算者 | 注入 context["_wall_deadline"] |
| `_deadline_guard`（【v3】L1 新包装） | 收 | `deadline_guard(caller, deadline)` 包覆主 caller（with_fallback 外层）；调用前预检，剩余≤0 抛 WallClockDeadlineExceeded |
| `with_fallback` 的逃生直连分支 | 【v3】预检 | 逃生调用发起前查 deadline 剩余（架构要求，实现由 fallback 工厂返回的直连 caller 经预检包装或内部检查完成） |
| `Gate4AuditRepair._substantive_review` | 读 | 从 context 读，转发 |
| `review_and_repair_loop` | 收 | 参数 `deadline=None` |
| `_run_substantive_review` / `_repair_chapters` | 收 | 参数 `deadline=None` |
| `_build_review_caller` / `_make_budgeted_caller` | 收 | deadline 传入，budgeted 调用前检查 |
| `create_harness_caller` | **不收（v3 修正）** | v2 §4.4 声称"新增 deadline 参数"与 code 侧签名矛盾——删除；harness 自身 timeout 兜底在途上限 |
| 入口 runner 构造的主 caller | 不直接收 | 由 L1 `_deadline_guard` 包覆（P0-B-1 明确落点） |

---

## 5. 数据流改造（v3，谁传谁收）

### 5.1 新增/变更参数总表

| 参数 | 新增位置 | 默认 | 谁传（源头） | 谁收（消费） |
|---|---|---|---|---|
| `_wall_deadline` | context + 4 个函数签名 | 无（L1 计算） | workflow.execute → context → gate4 → loop → 子函数 | L1/L3 全部检查点 + `_deadline_guard`/`_make_budgeted_caller`（§4.2） |
| `enable_debate` | loop 签名（keyword-only） | **False（恒 False）** | 【v3】gate4 调用 loop 时**硬编码 False**；WorkflowConfig 不再驱动、context 不再携带（删除 v2 config 驱动声称） | loop 辩论块：恒 False 永不执行（v3 明示恒 False） |
| `review_caller` | 【v3】**删除**（不再是参数，context 不再注入） | — | 【v3】无外部注入；loop 内部 `_build_review_caller(llm_caller, budget_state, deadline, llm_call_budget)` 自建（REVIEW_SYSTEM → with_fallback → budgeted，同一 budget_state） | `_run_substantive_review` 的 depth/conclusion（及辩论，恒 False） |
| `review_caller_override` | 【v3】**删除**（v2 虚构参数，从未发布；裁决采纳 code 侧） | — | — | — |
| `llm_call_budget` | context + loop 签名 | **300**（v2 为 60） | workflow → context["llm_call_budget"] → gate4 | loop 构造 budgeted caller，透传全链（P0-B#6）；**【v3】S5 重审不计入计数** |
| `shadow_skip_repair` | context（保留原字段） | True | workflow 按 qual_mode 写入 | gate4 读取：shadow+flag → 跳过修复循环（P0-B#9） |
| `llm_caller` | context（不变） | — | runner（with_fallback 包装）→ L1 `_deadline_guard` 包覆 | gate4 → loop → 修复/审查主链路 |
| `_llm_call_count`（审计） | context | 0 | gate4 写回 `result.llm_calls`（budget_state 终值） | workflow 审计日志（budget_exhausted 留痕） |

### 5.2 关键链路（v3）

```
run_xpev_full / run_qual_full
  └─ llm_caller = with_fallback(create_harness_caller(), 直连工厂, degrade_marker)
                  → 注入 context["llm_caller"]
     （【v3】runner 不再构造 review_caller；两 run 脚本收敛为同一表达式，P1#12）

QualWorkflow.execute
  ├─ deadline = monotonic() + global_timeout_seconds        → context["_wall_deadline"]
  ├─ context["llm_caller"] = _deadline_guard(原 llm_caller, deadline)   ← with_fallback 外层
  ├─ context["llm_call_budget"] / ["shadow_skip_repair"] / ["_llm_call_count"]
  └─ Gate 循环（RETRY_POLICY 常量表驱动重试）→ Gate4 → _substantive_review

gate4._substantive_review（fail-closed：无 caller / 异常 → passed=False）
  └─ review_and_repair_loop(
         chapters, ctx, llm_caller=context["llm_caller"],
         wind_data=…, max_rounds=…, industry=…,
         enable_debate=False,                        ← 【v3】恒 False（硬编码，无 config）
         llm_call_budget=context["llm_call_budget"],
         deadline=context["_wall_deadline"])

review_and_repair_loop（§3 状态机）
  ├─ budget_state = {"calls": 0}                          ← 唯一计数源
  ├─ repair_caller = _make_budgeted_caller(llm_caller, budget_state, deadline, budget)
  ├─ review_caller = _build_review_caller(llm_caller, budget_state, deadline, budget)
  │     └─ inner = create_harness_caller(max_tokens=8000, t=0.3, system=REVIEW_SYSTEM)
  │        fb    = with_fallback(inner, 直连工厂)          ← degrade_marker=None（不污染审查输出）
  │        review= _make_budgeted_caller(fb, budget_state, deadline, budget)  ← 同一 budget_state
  ├─ _run_substantive_review(..., budget_state, deadline, llm_call_budget)
  │     └─ check_depth / check_conclusion（经 review）→ DebateService（恒 False 不执行）
  └─ _repair_chapters(..., deadline)（经 repair_caller）
       + S5 重审（同口径全量；【v3】不计入预算计数，单列审计）

tools/finance/workflow.py::_generate_chapter（Gate3 分章生成，P0-B#4）
  ├─ 经 _deadline_guard 包覆的主 caller（v3 落点：Gate3 主链路有调用级预检）
  └─ except DeterministicLLMFailure: 不格式重试 → 降级章节 + 内嵌标记
```

---

## 6. P0/P1 边界重划（18 项修正矩阵，v3 解决状态）

### 6.1 清单 → 落点 → 阶段 → v3 状态

| # | 修正项 | 落点（文件/层） | 阶段 | v3 状态 |
|---|---|---|---|---|
| 1 | 豁免 fail-open（passed=True 禁止；签名保留章节号；计入 remaining） | review_repair_loop（L3 状态机 S2/S3/DEGRADE） | **P0-A** | ✅ **v3 再修正**：判据改查累积豁免清单（P0-A-2），堵"已豁免签名不再报出→误 PASS"绕过 |
| 2 | gate4 无 caller 第二条 fail-open → passed=False | gate4.py（L2） | **P0-A** | ✅（v2 已解决，v3 不变） |
| 3 | 豁免学习证据护栏（≥3 轮+无修复迹象+审计+报告注明豁免数） | review_repair_loop（S6 + 审计） | **P0-A** | ✅ **v3 同步**：`fixed_sigs`（原始签名集差集）供"从未被修复"判定 |
| 4 | `_generate_chapter` 外层重试吞确定性失败 | tools/finance/workflow.py（L3 上游） | **P0-B** | ✅（v2 已解决，v3 不变） |
| 5 | debate 无条件运行 → `enable_debate` 默认 False | review_repair_loop + gate4 + WorkflowConfig | **P0-B** | ✅ **v3 再修正**：gate4 **硬编码恒 False**，删除 config 驱动声称（P0-B-2） |
| 6 | `_budgeted_caller` 死代码 → 透传全链 | review_repair_loop / _run_substantive_review | **P0-B** | ✅ **v3 再修正**：S5 重审不计入计数（P1-1） |
| 7 | 墙钟只查 Gate 边界 → deadline 调用级注入 | harness_llm + loop + workflow | **P0-B** | ✅ **v3 再修正**：落点 = L1 `_deadline_guard` 包主 caller + 逃生直连预检；harness 不加 deadline 参数（P0-B-1） |
| 8 | 确定性失败无逃生 → 换路由单次重试，仍败降级+打标 | 入口 runner fallback | **P0-B** | ✅ **v3 再修正**：逃生调用前过 deadline 预检 |
| 9 | `shadow_skip_repair` 无消费方 → gate4 读标志 | gate4.py | **P0-B** | ✅（v2 已解决，v3 不变） |
| 10 | fallback 切换只查成功分支 → 移入 except 分支 | run_xpev_full / run_qual_full | **P0-B** | ✅（v2 已解决，v3 不变） |
| 11 | 缺 DeterministicLLMFailure 导入 + run_qual_full 同步 | 两个 runner | **P0-B** | ✅（v2 已解决，v3 不变） |
| 12 | `LLM_EMPTY_OUTPUT` 补入 ERROR_CODE_MAPPING（permanent/retry=False） | error_classifier.py | **P1** | ✅ **v3 再修正**：类型/关键词识别显式映射；文本兜底 UNKNOWN_ERROR 不默认计入熔断（P0-B-3） |
| 13 | 熔断阈值 2（或持久化计数）；BUSINESS 不计入 | circuit_breaker.py + workflow 构造 | **P1** | ✅ **v3 再修正**：阈值 < gate_attempts **或跨 run 持久化**，保证 can_execute() 真能返回 False（P0-B-3）；BUSINESS/UNKNOWN 兜底不计入 |
| 14 | 审查 caller 保留 REVIEW_SYSTEM（外层包 fallback，不裸复用） | runner 构造 review_caller + loop 消费 | **P1** | ✅ **v3 再修正**：**构造点采纳 code 侧**——loop 内部 `_build_review_caller` 自建；删除 runner 注入链与 `review_caller_override`（P0-B-2） |
| 15 | 单调守卫：签名差集 + 前后同口径 + deepcopy 快照 | review_repair_loop（S5） | **P1** | ✅ **v3 再修正**：before/after 均取原始签名集；`issues_fixed` 先减后置零（净修复，P0-A-3） |
| 16 | 签名保留章节号（正则链） | `_issue_signature`（S2） | **P1** | ✅ **v3 再修正**：正则顺序 = findall 捕获章节号 → 归一化其余数字 → 还原占位符（v2-code 的"先替换占位符后归一化"把占位符内章节号一并归一化 → 4/5 章签名仍相同，test_signature_keeps_chapter 必红；P0-A-1） |
| 17 | 改动 7 删除或标注"验证性，无需重建插件" | llm-bridge.js（实证已具备 finishReason） | 清理 | ✅（v2 已解决，v3 不变） |
| 18 | 统一 enforce/soft/shadow 重试语义为单一常量表 | qual_v8/workflow.py RETRY_POLICY | 清理 | ✅（v2 已解决，v3 不变） |

### 6.2 阶段定义与实施顺序（v3 修订）

- **P0 止血（11 项，先实施）**：P0-A 3 项（fail-open 堵漏 + 判据修正，最先）+ P0-B 8 项（止血，含 deadline 落点与 arch/code 三处矛盾的裁决修正）。
- **P1 架构（5 项）**：熔断修复（可触发）、审查 caller 自建、单调守卫、预算错配、实施顺序与单测。
- **清理（2 项）**：#17 实证确认无改动；#18 常量表合并。

**实施顺序（v3 插入修正点；依赖关系同 v2-code §5）**：
1. 先改 `llm_errors.py`（异常契约先行：`DeterministicLLMFailure`/`WallClockDeadlineExceeded`/`LLMCallBudgetExceeded`）→ 再改 loop 签名与状态机（含 `_issue_signature` 正则链、累积豁免判据、单调守卫修正）→ 再改 gate4 调用（enable_debate=False 硬编码、无 review_caller 传参）→ runner 接线（with_fallback + `_deadline_guard` 包主 caller）。
2. 每步配单测（确定性失败 0 重试、豁免累积判据第 4 轮空仍 False、`_issue_signature` 4/5 章不同签、deadline 后调用被拒、单调回滚净计数、budget 截断、熔断 can_execute 真 False）。

---

## 7. 与 v1 原方案相比的架构变化点（v3 终态）

| # | 维度 | v1 原方案 | v2 修订 | v3 终态修正 |
|---|---|---|---|---|
| 1 | 预算模型 | 独立时钟（Gate 顶部 + timeout_per_gate + call timeout） | 单一 deadline 主源 + 4 层检查点；per-call 有效超时 = min(调用超时, 剩余) | 预检覆盖**所有调用入口**（含逃生直连），上界可证明；harness 不加 deadline 参数（P0-B-1） |
| 2 | results 完整性 | 3b break 后缺条目，打标失效 | 超时/预算终止补写当前+剩余 Gate 条目（恒 9 条） | 不变 |
| 3 | 豁免语义 | 剔除后 `not round_issues → passed=True`（fail-open） | PASS 需"排除豁免后为空 **且** 豁免清单为空"；≥3 轮证据护栏 | **判据改查累积豁免清单**（防"已豁免签名不再报出→误 PASS"绕过）（P0-A-2） |
| 4 | 确定性失败路由 | 仅 harness 层不重试，外层仍吞并重试 | 全链非重试 + L0 换路由单次逃生 + 逐层降级打标 + 熔断 permanent | 逃生直连过 deadline 预检；异常命名统一 `WallClockDeadlineExceeded`（P0-B-2） |
| 5 | 单调守卫 | 数量比较（after > before 回滚） | 签名差集 + 前后同口径 + deepcopy 快照 | **before/after 均取原始签名集**；issues_fixed 净修复（先减后置零）（P0-A-3） |
| 6 | debate | 无条件运行（~72min/轮） | `enable_debate` 门控默认 False（config 驱动） | **gate4 硬编码恒 False，无 config 驱动**（P0-B-2） |
| 7 | 审查 caller | 5c 裸复用主 caller（丢 REVIEW_SYSTEM） | runner 构造 review_caller（REVIEW_SYSTEM+fallback）注入；loop 禁止自建 | **采纳 code 侧：loop 内部 `_build_review_caller` 自建**；删除 runner 注入链与 `review_caller_override`（P0-B-2） |
| 8 | 熔断 | 双枚举跨类恒 False；权重 0.5 不可达；BUSINESS 计入 | 单一枚举源；LLM_EMPTY_OUTPUT permanent；阈值 2；BUSINESS 不计入 | **阈值 < gate_attempts 或跨 run 持久化**（可触发）；文本兜底不默认计入（P0-B-3） |
| 9 | 预算调用计数 | `_budgeted_caller` 设计未接 | budgeted caller 透传全链 | **上限 60 → 300**；S5 重审不计入计数（P1-1） |
| 10 | 桥接 | 改动 7 补 finishReason（no-op） | 删除改动，标注验证性确认 | 不变 |
| 11 | 重试语义 | 各模式手写 if/elif 分支 | 单一 RETRY_POLICY 常量表 | 不变 |

---

## 8. 验收标准修订（v3，机制自洽 + 与实现一致）

### 8.1 指标

| 指标 | v2 目标 | v3 目标（与实现一致） | 验证方式 |
|---|---|---|---|
| 终止性 | 任何运行 ≤ 全局 deadline + 单次在途上限（300s），声称"可证明"但实现缺 Gate3 调用级检查 | **任何运行 ≤ deadline + 300s，且可证明**：所有 LLM 调用入口（主 caller/审查/修复/逃生直连）发起前均过预检，唯一超支项 = 已预检的在途调用（≤300s）（P0-B-1） | 注入确定性失败假 caller 回归断言运行结束且 0 次同模型重试；`deadline` 后调用被拒单测（test_budget_deadline 的 deadline 分支 + guard 拒调用例） |
| LLM 空输出重试 | 同模型重试 = 0；换路由单次逃生 ≤1 | 不变（106 次失败 → ≤106 次调用 + ≤106 次单路由逃生，且逃生调用过 deadline 预检） | harness_llm 单测（分类断言）+ with_fallback 单测 |
| Gate4 收敛 | 早停 ≤2 轮；豁免清单非空 → passed=False | **豁免判据 = 累积豁免清单非空 → passed=False**（含"已豁免签名不再报出"场景，test_exemption_failclosed 第 4 轮空仍 False）；无 caller/审查异常 → Gate4 失败 | 状态机单测（DEGRADE/EARLY_STOP/T_REVIEW_FAIL 出口断言） |
| 审查-修复闭环 | 签名差集单调守卫 + 同口径重审 + deepcopy 回滚 | **before/after 均取原始签名集**；回归注入"修复 A 引入 B"断言回滚；issues_fixed 净计数 | 单调守卫单测（含 fixed_count 断言） |
| shadow 语义 | shadow+skip_repair：修复循环跳过；任何降级路径报告必带"未修复"标 + quality_degraded=True | 不变（results 恒 9 条） | 打标断言（9 条目 + 横幅存在） |
| 预算不误伤正常路径 | 上限 60 与实测每轮 27-50 次矛盾 → 正常 2 轮即 T_BUDGET 误伤 | **上限 300 + S5 不计预算：正常 2-3 轮（业务调用 81-150 次）不触发 T_BUDGET**；T_BUDGET 只在真实失控（>300 次或 deadline 内无收敛）时触发（P1-1） | 实测小鹏断言 `result.llm_calls < 300` 且非 budget_exceeded；机制测试 llm_call_budget=2 断言截断 |
| 正常路径时长 | shadow + debate 关闭 + 确定性失败路由：目标 ≤60 分钟（硬兜底 = deadline） | 保留软目标 ≤60 分钟（**实测校准，不作硬断言**）；硬上界 = deadline + 300s | 实测小鹏 + 日志时间戳审计 |

### 8.2 可达时长推导（v3 修正版）

**v2 推导错误**：声称"debate 关闭后每轮实质审查约 3-5 次 LLM 调用，正常 2 轮 ≈ 10-25 分钟"——实测每轮真实 27-50 次调用（depth_reviewer + conclusion_validator + repair 实读），且 v2 上限 60 与该实测直接矛盾（正常第 2 轮即 T_BUDGET 早停）。v3 删除该虚假精确推导，改为与实现一致的代数式：

原 6h+ 卡死的构成：**106 次 max-tokens 空输出 ×（harness 3 尝试 + 外层格式重试 3 次）** + **50-88 项假阳性 × 3 轮 × 每轮全量重审** + **debate 3 章 × 多角色 × 240s × 重试（约 72 分钟/轮）** 三者相乘。

v3 修复后逐项消除：
1. 确定性失败 → 0 次同模型重试（106 次失败从 106×9 次调用降为 ≤106 次调用 + ≤106 次单路由逃生）；
2. 假阳性 → 收敛状态机在 1-2 轮内以 DEGRADE/EARLY_STOP 终止（有界），豁免累积判据防静默 PASS，豁免学习不再为假阳性投入第 4+ 轮修复；
3. debate → 恒 False（72 分钟/轮 → 0）；
4. **v3 新增**：预算上限 60→300 + S5 不计预算 → 正常 2-3 轮（27-50 次/轮业务调用）不再被 T_BUDGET 误伤。

**Gate4 时长代数式（v3）**：
```
T_gate4 ≈ Σ_轮 (N_review + N_repair + N_recheck) × t_call
  · N_review+N_repair ∈ [27, 50] 次/轮（实测，depth+conclusion+repair）
  · N_recheck（S5 重审）同量级（不计预算、计入时长）
  · t_call 依模型/分段长度而异（实测校准，不作虚设）
  · 上界：T_gate4 ≤ min(300 次 × t_call, deadline 剩余)   ← 预算/时间双保险
```
正常 2-3 轮业务调用 81-150 次 < 300 上限（不触发 T_BUDGET）；整链（Gate0-8）软目标 ≤60 分钟（实测校准），最坏路径由 deadline 硬性封顶 ≤ 90 分钟 + 300s。**验收不以"X 分钟内完成"为硬断言，以"≤ deadline + 300s 且有界、预算不误伤正常路径"为准**——指标与机制自洽、与实现一致。

---

## 9. 不变量清单（v3，防矛盾约束，代码专家必须遵守）

1. **单一时间主源**：全局 deadline 之外禁止任何独立墙钟计数器；per-call 超时必须是派生值。**【v3】deadline 预检必须覆盖所有 LLM 调用入口（主 caller、审查/修复 budgeted caller、with_fallback 逃生直连）——否则"deadline + 300s"上界不可证明。**
2. **豁免与 fail-closed 不冲突**：豁免永不产生 `passed=True`；PASS 的唯一条件 = 排除豁免后为空 **且 累积豁免清单为空**（`not any(e["exempted"] for e in exempted.values())`，非仅本轮剔除集）。
3. **确定性失败全链非重试**：任何 `except Exception` 之前必须有 `except DeterministicLLMFailure` 分流（白名单含 `WallClockDeadlineExceeded`/`LLMCallBudgetExceeded`）；逃生重试必须换路由且 ≤1 次，逃生调用前必须过 deadline 预检。
4. **results 恒 9 条目**：预算/超时终止必须补写当前与剩余 Gate 条目；报告打标依赖完整 results。
5. **单调守卫同口径 + 原始签名集**：before/after 用同一审查管线、**均取原始签名集合（不受豁免剔除影响）**；`issues_fixed` 为净修复数（回滚时先减后置零）。
6. **单一枚举源 + 熔断可触发**：`ErrorType` 只允许 error_classifier.py 定义一次；熔断计数**跨 run 持久化或阈值 < gate_attempts**，保证 `can_execute()` 真能返回 False；文本兜底（UNKNOWN_ERROR）与 BUSINESS **不默认计入熔断**。
7. **审查 caller 单一构造点（v3）**：审查专用 caller 只允许 loop 内部 `_build_review_caller` 自建（REVIEW_SYSTEM + with_fallback + budgeted，同一 budget_state）；runner 不注入，`review_caller_override` 不存在。
8. **budgeted caller 全链透传**：业务调用（审查 depth/conclusion + 修复）必须全部计入预算，不允许绕过；**【v3】S5 重审不计入预算计数（单列审计，受 deadline + max_rounds 约束）。**
9. **enable_debate 恒 False（v3）**：gate4 硬编码；WorkflowConfig 不提供驱动路径；loop 签名默认 False 仅作 legacy 兼容。
10. **签名保留章节号（v3）**：`_issue_signature` 正则链顺序 = **findall 捕获章节号 → 归一化其余数字 → replace("第N章", "第@{ch}章") 还原**；占位符内章节号不得被再次归一化；跨章同形问题 → 不同签名（第 4/5/12 章均正确）。
11. **异常命名统一（v3）**：`DeterministicLLMFailure` / `WallClockDeadlineExceeded`（其子类）/ `LLMCallBudgetExceeded` 唯一定义于 `tools/finance/llm_errors.py`；文档与代码禁止再出现 `DeadlineExceeded`/`DeadlineExceededError` 等别名。

---

## 10. 变更记录（v2 → v3）

| # | 位置（v2 章节） | v2 内容 | v3 内容 | 动机（依据） |
|---|---|---|---|---|
| 1 | §0 原则 6 | enable_debate 默认 False（裁决 b，config 可驱动） | **恒 False**：gate4 硬编码，删除 config 驱动声称；loop 参数仅为 legacy 兼容 | P0-B-2：arch 声称 config 驱动 vs code gate4 硬编码 False 矛盾，裁决统一为硬编码 |
| 2 | §0 原则 7 / §9-3 | 异常命名 DeadlineExceeded / DeadlineExceededError | 统一 **WallClockDeadlineExceeded**（+LLMCallBudgetExceeded，定义于 llm_errors.py 单一来源） | P0-B-2：异常命名漂移，裁决统一 code 侧命名 |
| 3 | §0 原则 5 / §3.1 S5 / §9-5 | 单调守卫比较原始签名集合（v2 表述含糊）；v2-code 回滚计数 no-op | **before/after 均取原始签名集**；issues_fixed 先减后置零（净修复） | P0-A-3：裁决"先减后置零；before 取原始集"（test_monotonic_guard 必红） |
| 4 | §1 L0 / §5 数据流 | runner 构造 review_caller 注入 context；loop 消费 + review_caller_override=True | **删除 runner 注入链与 review_caller_override**；loop 内部 `_build_review_caller` 自建（REVIEW_SYSTEM+fallback+budgeted） | P0-B-2：arch/code 构造位置互斥，裁决采纳 code 侧（loop 内部自建） |
| 5 | §1 L1 / §4.2 / §4.4 | 主 caller 包 deadline guard（未明确落点）；create_harness_caller 新增 deadline 参数 | **落点明确**：`_deadline_guard` 包主 caller（with_fallback 外层）+ 逃生直连预检；**harness 不加 deadline 参数** | P0-B-1：审查确认 code 侧 create_harness_caller 无 deadline 参数、_deadline_guard 全文未出现 → v2"deadline+300s 可证明"验收不成立 |
| 6 | §2.1 / §2.2 | deadline 耗尽（DeadlineExceeded 子类） | deadline 耗尽（**WallClockDeadlineExceeded**）；预算耗尽（LLMCallBudgetExceeded）同族；逃生调用前过 deadline 预检 | P0-B-1/P0-B-2：命名统一 + 逃生在途超支排除 |
| 7 | §3.1 S2 / §9（新增 10） | 签名保留章节号（P0-A#1，未指明正则实现） | **正则链顺序**：findall 捕获章节号 → 归一化其余数字 → 还原占位符（占位符内章节号不得被归一化） | P0-A-1：裁决 1 实跑正则链——v2-code"先占位符后归一化"把 `第@4章` 的 4 归一化 → 4/5 章签名仍相同，test_signature_keeps_chapter 必红 |
| 8 | §3.1 S3 / §3.2 / §9-2 | PASS 判据 = kept=∅ ∧ exempted_pool=∅（本轮剔除集） | **PASS = kept=∅ ∧ 累积豁免清单为空**（`not any(e["exempted"] ...)`） | P0-A-2：裁决 2 豁免 PASS 绕过——豁免学习置 exempted=True 后该签名不再报出 → v2 判据误 PASS（test_exemption_failclosed 必红） |
| 9 | §4.1 / §3.1 S0 / §3.2 | max_llm_calls_per_gate = 60 | 默认 **300**（≥200 裁决底线；以 code 分册终值为准）+ **S5 重审不计入计数** | P1-1：预算错配——实测每轮 27-50 次 vs 上限 60 → 正常第 2 轮 T_BUDGET 误伤 |
| 10 | §8.2 | "每轮约 3-5 次 LLM 调用，正常 2 轮 ≈ 10-25 分钟" | 删除虚假精确推导，改代数式（27-50 次/轮实测 + t_call 实测校准 + 上界 min(300×t_call, deadline)） | P1-1：审查确认 arch §8.2 与代码矛盾（实测 27-50 次/轮） |
| 11 | §8.1 终止性 | "deadline + 300s 可证明"（实现无 Gate3 调用级检查） | "deadline + 300s 可证明"**前提 = 所有调用入口预检**（`_deadline_guard` 落地后成立），验收断言与实现一致 | P0-B-1：验收断言从"声称可证明"改为"与实现一致的可证明表述" |
| 12 | §2.1 / §9-6 | 熔断阈值 2 + BUSINESS 不计入（v2 修复） | **v3 同步**：阈值 < gate_attempts 或跨 run 持久化（可触发）；文本兜底 UNKNOWN_ERROR 不默认计入 | P0-B-3（综合审议）：enforce gate_attempts=2 与阈值 2 同步耗尽 → can_execute() 永不返回 False；UNKNOWN_ERROR→默认 TRANSIENT 绕过"BUSINESS 不计入" |
| 13 | §5.1 / §1 L2 | gate4 传参含 review_caller / review_caller_override=True / enable_debate（config） | gate4 传参 = enable_debate=False（硬编码）/ llm_call_budget / deadline；无 review_caller | P0-B-2：三处矛盾全部按裁决统一（见 #1/#4） |
| 14 | §6 矩阵 | 18 项（v2 状态） | 18 项标注 **v3 解决状态**：11 项 v3 再修正（#1/#3/#5/#6/#7/#8/#12/#13/#14/#15/#16），其余 7 项 v2 已解决、v3 不变 | 7 项修正清单落地跟踪 |
| 15 | §0 原则 8（新增） | — | **审查 caller 单一构造点**：只允许 loop 内部自建 | P0-B-2：把裁决固化为架构不变量 |
| 16 | §9-1（强化） | 单一时间主源 | +"deadline 预检覆盖所有 LLM 调用入口（含逃生直连）" | P0-B-1：上界可证明的必要条件 |
| 17 | §9-9 / §9-11（新增） | — | enable_debate 恒 False 不变量；异常命名统一不变量 | P0-B-2：防 arch/code 再漂移 |

**接口一致性声明**：本分册与 code 分册（v3，并行修订）保持一致的四项裁决——① 删除 `review_caller_override`、审查 caller 由 loop 内部 `_build_review_caller` 自建；② 异常统一 `WallClockDeadlineExceeded`；③ `enable_debate` 恒 False（gate4 硬编码）；④ `max_llm_calls_per_gate` 提高（≥200，本分册默认 300；若 code 分册采用不同数值，以 ≥200 内双方一致值为准）。
