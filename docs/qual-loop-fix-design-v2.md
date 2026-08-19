# qual v8 死循环修复——修订版方案（v2）

日期：2026-08-19
依据：`docs/qual-loop-fix-design.md`（v1 原方案）+ `docs/heavyskill-fix-review.md`（审查报告 18 项修正清单）
修订方式：架构专家 + 代码专家并行修订（双专家），本文件为合并版

---

## 说明

本 v2 方案由两部分组成：

| 部分 | 文档 | 内容 |
|---|---|---|
| 架构设计 | `docs/qual-loop-fix-design-v2-arch.md`（38KB） | 分层架构图、错误路由决策表、收敛状态机、预算体系、数据流、P0/P1 边界、验收修订、不变量清单 |
| 代码设计 | `docs/qual-loop-fix-design-v2-code.md`（76KB） | 18 项缺陷逐项修订代码（精确行号）、完整新签名、确定性失败六消费方链路、预算全链接线、4 个合并提交实施顺序、15 个测试用例 |

**实施时以两份分册为准，本文件为导读与变更摘要。**

---

## 一、v1 → v2 变更摘要

### 1. 架构层变化（11 条，详见 v2-arch §7）

| 变化 | 说明 |
|---|---|
| 新增 4 个横切层 | deadline 注入层 / 豁免证据护栏层 / enable_debate 门控 / 确定性失败路由 |
| 收敛状态机 | S0-S6 + 8 出口；PASS 唯一 True；DEGRADE/EARLY_STOP/T_REVIEW_FAIL/T_DEADLINE/T_BUDGET/T_MAXROUNDS 全 fail-closed |
| 豁免 pass 判据修订 | "排除豁免后为空 **且** 豁免清单为空" 才 PASS；豁免非空 → FAIL + 降级标记 |
| 单一 deadline 主源 | 消除 v1 三套独立时钟（全局 5400s / 单 Gate 60 调用 / 单调用 300s）冲突；最坏上界 = deadline + 300s 在途 |
| results 恒 9 条目 | 修 v1 3b break 后 results 缺 gate 4-8 条目导致打标失效 |
| L5 桥接降为验证 | llm-bridge.js:56-64 已返回 finishReason，原改动 7 为 no-op |

### 2. 代码层变化（18 项缺陷全部修订，详见 v2-code）

| 阶段 | 项数 | 要点 |
|---|---|---|
| P0-A | 3 | 豁免 fail-closed+证据护栏；gate4.py:226-228 第二条 fail-open 修复；检查器吞异常→"审查不完整"+默认 50 分删除 |
| P0-B | 8 | _generate_chapter 短路（含 v8 Gate3 双路径同修）；with_fallback 装饰器+补 import；单调守卫 deepcopy+签名差集+同口径；_budgeted_caller 全链透传；全局 deadline+_fill_failed_gates；enable_debate=False；shadow_skip_repair 消费；REVIEW_SYSTEM 保留+fallback |
| P1 | 5 | run_qual_full 同步；RETRY_POLICY 三模式统一；LLM_EMPTY_OUTPUT 映射；熔断枚举统一+阈值2+REVIEW_UNRESOLVED；签名保留章节号 |
| 清理 | 2 | 改动7 移除（no-op 确认）；15 个测试用例 |

## 二、五项设计裁决的落地位置

| 裁决 | 落地文档 |
|---|---|
| (a) 豁免不允许 passed=True | v2-arch §3 状态机 + v2-code P0-A-1 |
| (b) D9 辩论 enable_debate=False | v2-arch §5 数据流 + v2-code P0-B-5 |
| (c) 确定性失败→换模型单次→降级打标 | v2-arch §2 路由决策表 + v2-code 确定性失败链路 |
| (d) 墙钟 deadline 调用级注入 | v2-arch §4 预算体系 + v2-code P0-B-8 |
| (e) 单调守卫签名差集+同口径 | v2-arch §3 状态机 + v2-code P0-B-6 |

## 三、验收标准修订（v2）

| 指标 | v1（不可达） | v2 |
|---|---|---|
| 最坏运行时长 | ≤30-40 分钟 | **deadline + 300s 硬上限**（正常路径 ≤60 分钟） |
| 空输出重试 | 106×3→0 | 确定性失败 ≤1 调用/例（同模型 0 重试，换路由单次逃生） |
| Gate4 收敛 | 1-2 轮早停 | 假阳性 1-2 轮收敛（辩论 72min/轮→0 已消除） |
| shadow 语义 | 单次+打标 | 单次+打标+豁免非空即 fail（无静默产出） |
| 审查质量 | 复用主 caller 污染 | REVIEW_SYSTEM 保留 + fallback 装饰器 |

## 四、实施顺序（4 个合并提交，详见 v2-code §5）

1. **提交 #1**：P0-A（3 项）+ 全部签名修订（review_and_repair_loop / _run_substantive_review / create_harness_caller / with_fallback）
2. **提交 #2**：P0-B（8 项）原子化——本提交后可实测小鹏（enable_debate=False 消除辩论 72min/轮）
3. **提交 #3**：P1（5 项，熔断统一）
4. **提交 #4**：清理（2 项，测试补齐）

**依赖对（必须同提交）**：loop 签名先于 gate4 调用（提交 #1 内）；_generate_chapter 短路需 v8 Gate3（gate3.py:164 复用 legacy）与 legacy 双路径同修（提交 #2）。
