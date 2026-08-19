# qual v8 死循环修复——最终方案（v3.1）

日期：2026-08-19
依据：v3 方案 + 第三轮 HeavySkill 验证（4 轨迹）+ 综合审议（v3.1 修正清单，见 `docs/qual-loop-fix-v3.1-checklist.md`）
状态：**最终交付版**——按 v3.1 清单修正后可作为实施基础，不再需要第四轮全量验证

---

## 说明

本 v3.1 方案由两部分组成（实施时以两份分册为准，本文件为合并导读）：

| 部分 | 文档 | 内容 |
|---|---|---|
| 架构设计 v3.1 | `docs/qual-loop-fix-design-v3-arch.md`（59KB，11 节）+ v3.1 修正 | 分层架构图、收敛状态机、预算体系、数据流表、验收修订 |
| 代码设计 v3.1 | `docs/qual-loop-fix-design-v3-code.md`（99KB，1510 行）+ v3.1 修正 | 修正后完整代码、完整新签名、20 个测试用例、4 个合并提交 |

---

## 一、v3 → v3.1 变更摘要（综合审议裁决的 9 项修正）

### P0（7 项，必须修正后才能实施，每项附接线级验收）

| # | 缺陷 | v3.1 修正 | 涉及文件 | 接线级验收 |
|---|---|---|---|---|
| P0-1 | **熔断阈值锚点错误**：文档称"181 行 threshold=2 保持"，实测源码=3；字面实施（3+attempts 3）反而从现状"可达"退化为"死激活" | 显式改 `workflow.py:181` 为 `failure_threshold=2`（或 RETRY_POLICY enforce gate_attempts=4>3） | qual_v8/workflow.py:181；RETRY_POLICY | 测试构造 `QualWorkflow()` 断言 `circuit_breakers[4].failure_threshold < gate_attempts` 且第 3 次尝试 can_execute()=False（**不测自建实例**） |
| P0-2 | **幽灵模块 llm_fallback.py**：真实不存在，fallback 是 run 脚本内联 | 二选一：①提交计划新增创建 `tools/finance/llm_fallback.py`（with_fallback 独立模块）并接线两 run 脚本；②撤销模块化，except 链改造落内联函数，`test_run_scripts_consistent` 改断言内联函数存在 | 新建 llm_fallback.py 或 run_qual_full.py:92 / run_xpev_full.py:177 | 实施后 grep 验证模块存在（方案①）或内联函数含正确 except 顺序（方案②）；测试与代码同落点 |
| P0-3 | **with_fallback except 顺序**：`except DeterministicLLMFailure`(583) 遮蔽子类 `WallClockDeadlineExceeded`(594)，墙钟异常被吞+误触发逃生 | 白名单 `except (LLMCallBudgetExceeded, WallClockDeadlineExceeded)` 移到 `except DeterministicLLMFailure` **之前** | with_fallback 实现 | 单测：注入 WallClockDeadlineExceeded → `_switch()` 调用 0 次、异常原样上抛 |
| P0-4 | **逃生直连无 deadline 预检**：违反 arch 不变量，上界破溃至 deadline+600s | 逃生分支 `direct(...)` 前加 `_deadline_guard`（`monotonic()>deadline → raise WallClockDeadlineExceeded`） | with_fallback 逃生分支 + 两 run 脚本 | 单测：deadline 过期时注入 primary 失败 → 逃生调用 0 次 |
| P0-5 | **arch/code 预算矛盾**：arch=300+S5不计 vs code=200+S5计 | **裁决：采纳 code 侧（200 + S5 每调用必计数）**；arch 全文 300→200、S5"不计"→"计入" | v3-arch §3.4/§4.1/§5；导读:42 | grep 两册+导读数值与 S5 口径全一致；test_workflow_config_budget 断言==200 |
| P0-6 | **harness deadline 参数三册矛盾**：arch 不加 / code 加 / 导读自相矛盾 | **裁决：采纳 code 侧（加 keyword-only deadline）**；arch §439/515 与导读:50 改口 | v3-arch:439/515；导读:50 | 三册 grep 一致；test_budget_deadline(c) 可构造 deadline=已过期 → 抛 WallClockDeadlineExceeded |
| P0-7 | **gate4:226-228 fail-open 未修**（v2 标"已解决"但源码从未落地） | 补修复代码：`llm_caller is None → passed=False + errors`；纳入提交 #1 | gate4.py:226-228 | test_gate4_no_caller_failclosed 绿；实施后 226-228 与 278-280 均不再返回 passed=True |

### P1（2 项，实施时顺带修正）

| # | 缺陷 | 修正 |
|---|---|---|
| P1-8 | 导读:42 不等式反向（"200<180"） | 改"81-150 < 200 且 200 > 180（=5400/30）" |
| P1-9 | 测试计数声称 17=12+4+3，实际 20=13✓+4★+3▲ | 文档改 20 并修正分类计数 |

---

## 二、v3 已验证解决项（4 轨迹 + 综合审议采信，不再修订）

| 项 | 状态 | 验证方式 |
|---|---|---|
| 缺陷16 签名保留章节号（三段式） | ✅ 已解决 | Python 实跑 s4≠s5、第@12章保留、多章节号保序 |
| 缺陷1 豁免 PASS 绕过（累积清单判据） | ✅ 已解决 | 模拟空轮仍 passed=False |
| 缺陷6 单调守卫（先减后置零+原始集） | ✅ 已解决 | 模拟回滚后 issues_fixed==0 |
| 3 个"必红测试"修正版 | ✅ 全绿 | 4 轨迹独立模拟一致 |
| 终止性四重有界 + 确定性失败不重试 + debate 关闭 | ✅ 达成 | 源码实证 |

---

## 三、v3.1 关键设计决策（修订版）

1. **熔断可达性**：workflow.py:181 显式 `failure_threshold=2` + RETRY_POLICY enforce gate_attempts=3 → 第 2 次失败 OPEN、第 3 次 can_execute()=False 真短路（接线级测试封口）
2. **预算 60→200** + S5 计入：200 > 实测 3 轮 150 次 → 正常路径不触发 T_BUDGET；200 > 180（=5400/30）→ T_BUDGET 恒晚于 T_DEADLINE（修正不等式方向）
3. **deadline 双保险**：L1 `_deadline_guard` 包主 caller + L4 harness keyword-only deadline 参数（两册统一为"加"）
4. **with_fallback 白名单前置**：预算/墙钟异常优先于普通确定性失败（杜绝子类遮蔽）
5. **移除死参数**：删除 `on_deterministic`
6. **非自包含补全**：实施清单补列 v2 全部代码依赖（gate4 双 fail-open、depth_reviewer 吞异常+默认50分、harness 分类等）——v3.1 为可落地完整清单

---

## 四、验收标准（v3.1）

| 指标 | v3 | v3.1 |
|---|---|---|
| 自带测试 | 17（计数错） | **20 测试全绿**（13✓+4★+3▲） |
| 熔断 | 单元级可达 | **接线级可达**（QualWorkflow 生产阈值 2 < gate_attempts 3，第 3 次真短路） |
| 运行上界 | deadline+300s（逃生路径破溃） | deadline+300s（逃生预检已落地，含逃生调用） |
| 预算 | 200（arch/code 矛盾） | **200 + S5 计入**（三册一致） |
| deadline 参数 | 三册矛盾 | **三册一致"加"** |
| gate4 fail-open | 226-228 未修 | **双 fail-open 均 fail-closed** |

---

## 五、实施顺序（4 个合并提交，详见 v3-code §4 + v3.1 清单）

1. **提交 #1**：P0-A（3 项）+ gate4 双 fail-open 修复（P0-7）+ 全部签名修订
2. **提交 #2**：with_fallback 白名单前置 + 逃生预检（P0-3/4）+ deadline 链（P0-6）+ 熔断阈值修正（P0-1）——RETRY_POLICY enforce=3 与预算 200 随引入即落地
3. **提交 #3**：预算 200 + S5 计入（P0-5）+ 时长推导表（P1-8）+ 测试计数（P1-9）
4. **提交 #4**：清理（文档同步 + 测试补齐 + 幽灵模块落地 P0-2）

**依赖对**：loop 签名先于 gate4 调用（提交 #1）；_deadline_guard 与 create_harness_caller deadline 参数同提交（提交 #2）；enforce=3 与熔断阈值 2 同提交（提交 #2）；llm_fallback 模块与 with_fallback 改造同提交（提交 #2）。
