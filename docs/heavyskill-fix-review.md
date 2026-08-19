# HeavySkill 审查报告：qual-loop-fix-design.md 修复方案

日期：2026-08-19
方法：HeavySkill 多轨迹推理（K=8 独立轨迹 + 综合审议）
审查对象：`docs/qual-loop-fix-design.md`（P0 止血 + P1 重构，8 项改动）

---

## 一、最终判定

# 需修改后通过

- **终止性成立**：修复方案能把 6 小时死循环压成有界失败（for 上界 + 每调用硬超时），"不再死循环"可达
- **但 30-40 分钟验收不达标**：辩论组件未关 + 缺模型-任务匹配，且存在多处必须修正的实施缺陷
- **8/8 条独立轨迹 + 综合审议一致同意此判定**（0 条直接通过）

---

## 二、综合审议的独立实证（对照源码，非采信轨迹）

| # | 实证 | 结论 |
|---|---|---|
| 1 | 5b 流程 R3 豁免剔除后 `not round_issues → passed=True` | 豁免 fail-open 确认，复现 D8 静默产出（轨迹"已解决 D8"自相矛盾） |
| 2 | `gate4.py:226-228` `llm_caller=None → passed=True` | **第二条 fail-open 实证存在**，不在原 16 项清单，新增为 P0-A#2 |
| 3 | `workflow.py:1183-1241` `except Exception` 吞 DeterministicLLMFailure 并重试 3 次 | 外层格式重试使"确定性不重试"失效，新增 P0-B#4 |
| 4 | run_xpev_full 改动6 用 DeterministicLLMFailure 无 import | NameError 确认；run_qual_full.py:92-113 同款 fallback 未同步确认 |
| 5 | llm-bridge.js:56-64 已返回 finishReason | 改动7 确认 no-op |
| 6 | 熔断双重死因：枚举跨类恒 False + 8a/8b/8c 全落地后 enforce 2次×BUSINESS 0.5=1.0<3 | 熔断修复后仍不触发 |
| 7 | review_repair_loop.py:180-181 注释明示审查专用 system 动机 | 5c 复用主 caller 丢 REVIEW_SYSTEM 确认 |
| 8 | 签名归一化去"第N章"+去数字 | 跨章同形 issue 合并 → 误豁免确认 |

---

## 三、五个设计问题裁决

| 问题 | 裁决 |
|---|---|
| (a) 豁免机制通过语义 | **豁免不允许 passed=True**；只降级 + 证据护栏 + 审计可见 |
| (b) D9 辩论 | **纳入 P0**；`enable_debate` 参数默认 False |
| (c) 确定性失败路由 | **直连/换模型单次重试** → 仍失败则降级+打标；禁止同模型重试 |
| (d) 墙钟预算粒度 | **下沉调用级 deadline 注入 + Gate 级双保险**；并修 3b break 后 results 缺条目/打标失效 |
| (e) 单调守卫实现 | **签名差集 + 前后同口径 + deepcopy 快照** |

---

## 四、修正清单（18 项，按优先级）

### P0-A：fail-open 堵漏（3 项，必须最先）
| # | 缺陷 | 修正 | 文件/验收 |
|---|---|---|---|
| 1 | 豁免 fail-open：R3 豁免后 passed=True | 豁免项计入 remaining_issues，强制 passed=False + 降级标记；签名保留章节号 | review_repair_loop.py 5b；验收：豁免后报告带"未修复"标 |
| 2 | gate4.py:226-228 第二条 fail-open（llm_caller=None→passed） | 改为 passed=False + 错误信息 | gate4.py；验收：无 caller 时 Gate4 失败 |
| 3 | 豁免学习无证据护栏 | 豁免需 ≥3 轮 + 无修复迹象 + 审计记录 + 报告注明豁免数 | review_repair_loop.py；验收：豁免清单可审计 |

### P0-B：止血修正（8 项）
| # | 缺陷 | 修正 |
|---|---|---|
| 4 | `_generate_chapter` 外层重试吞确定性失败 | except 分支对 DeterministicLLMFailure 立即终止重试 |
| 5 | D9 辩论无条件运行 | review loop 加 `enable_debate=False` 参数（默认关） |
| 6 | `_budgeted_caller` 死代码 | budgeted caller 透传进 `_run_substantive_review` 全链 |
| 7 | 墙钟只查 Gate 边界 | deadline 传入 loop 轮首检查 + 单调用前检查 |
| 8 | 确定性失败无逃生 | 切直连/换模型单次重试，仍败降级+打标 |
| 9 | `shadow_skip_repair` 无消费方 | gate4 读标志跳过 loop 或删除该字段 |
| 10 | fallback 切换只查成功分支 | 移入两个 except 分支（全故障场景可切换） |
| 11 | run_xpev_full 缺 import | 补 `from finance.llm_errors import DeterministicLLMFailure`；同步 run_qual_full |

### P1：架构修正（5 项）
| # | 修正 |
|---|---|
| 12 | `LLM_EMPTY_OUTPUT` 补入 ERROR_CODE_MAPPING（permanent/retry=False） |
| 13 | 熔断阈值降至 2 或持久化失败计数；BUSINESS 不计入熔断 |
| 14 | 审查 caller 保留 REVIEW_SYSTEM（外层包 fallback，不裸复用主 caller） |
| 15 | 单调守卫：签名差集 + 前后同口径 + deepcopy 快照 |
| 16 | 实施步骤 4/5 调序（先改 loop 签名，再改 gate4 调用）+ 新逻辑单测 |

### 清理（2 项）
| # | 修正 |
|---|---|
| 17 | 改动7 删除或标注"验证性，无需重建插件" |
| 18 | 统一 enforce/soft 重试语义为单一常量表 |

---

## 五、16 个专家问题覆盖性（综合结论）

- **已解决**：D1（harness 分类）/ D3（早停有界化）/ D4（单调守卫方向）/ D8（shadow 单次+打标）/ D10（caller 复用）/ K1（审查走 fallback）
- **部分解决**：D2（契约重构推迟 P1）/ D5（熔断方向对但不可达）/ D6（墙钟方向对但不彻底）/ D11（fail-closed 一半）/ K2（豁免替代清单）/ K3（早停兜底）
- **未解决**：D7（检查点推迟）/ D9（P0 裁决后纳入）/ D12（指标无实现）

---

## 六、关键教训（HeavySkill 审查发现的方法论问题）

1. **独立轨迹发现优于单次审查**：8 条轨迹独立交叉验证，发现了单次审查易漏的缺陷（gate4 第二条 fail-open、外层格式重试、fallback 切换回归）
2. **"已解决"判定需独立实证**：多条轨迹声称 D8 已解决，但综合审议独立复现了豁免 fail-open 路径 → 判定矛盾被纠正
3. **方案代码与实际源码的接线是最大风险**：3 处悬空接线（shadow_skip_repair、_budgeted_caller、LLM_EMPTY_OUTPUT）都是"设计写了但代码没接"的典型
4. **验收标准需与机制自洽**：30-40 分钟验收与 debate 72min/轮、60×300s 调用上限直接矛盾
