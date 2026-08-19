# HeavySkill v2 审查报告：修订方案二次审查结论

日期：2026-08-19
方法：HeavySkill K=8 独立轨迹 + 综合审议（审议者亲自执行正则验证裁决分歧）
审查对象：`docs/qual-loop-fix-design-v2.md`（+ v2-arch / v2-code）

---

## 一、最终判定

# 需修改后通过

- **"不再死循环"目标已达成**：终止性四重有界（RETRY_POLICY + 300s 硬超时 + 60 次/Gate + 5400s deadline）+ 确定性失败不重试 + debate 关闭，全部经源码实证
- **但 3 项自带测试必红 + deadline 上界验收不成立 + arch/code 互斥矛盾 + 预算错配**，实施前必须修正
- 8/8 轨迹全部"需修改后通过"；综合审议独立验证后维持

---

## 二、综合审议的独立裁决（亲自执行验证，非采信轨迹）

### 裁决 1：缺陷 16 签名保留章节号 → **未解决（5/8 轨迹正确）**
python 实跑正则链：
```
第4章 营收增长100亿无解释 → 第@N章 营收增长N亿无解释
第5章 营收增长100亿无解释 → 第@N章 营收增长N亿无解释
```
**两条签名完全相等**（第 2 条 `re.sub(r"\d+\.?\d*","N")` 把占位符 `第@4章` 的 "4" 也归一化）。test_signature_keeps_chapter 断言不相等 → **必红**。声称"已解决"的 #3/#4/#6 未实际执行该正则链。
**修正**：先 findall 捕获章节号 → 归一化所有数字 → 再 replace("第N章", f"第@{ch}章") 还原（对 4/5/12 章均正确）。

### 裁决 2：缺陷 1 豁免 PASS 判据 → **部分解决，绕过存在（#1/#3/#8 正确）**
P0-A-1 判据查 `exempted_tracked`（仅本轮豁免**再次出现**时非空），而豁免学习只置 `entry["exempted"]=True` 不写入该集 → 已豁免签名后续轮不再报出时 `passed=True` 静默放行。test_exemption_failclosed（第 4 轮返回空）**必红**。
**修正**：判据改查累积豁免 `not any(e["exempted"] for e in exempted.values())`。

### 裁决 3：其余分歧（全轨迹共识 + 独立验证确认）
- **缺陷 6 单调守卫**：`fixed_count=0` 后才 `issues_fixed -= fixed_count` → no-op 计数虚高（test_monotonic_guard 必红）；before_sigs 过滤后 vs after_sigs 原始口径不对称
- **deadline**：code 分册 create_harness_caller 签名无 deadline 参数、_deadline_guard 全文未出现 → "deadline+300s 可证明上界"验收不成立（Gate3 主链路无调用级检查）
- **arch/code 三处矛盾**：review_caller 构造互斥（arch 注入 vs code 内部自建）；enable_debate 链（arch config 驱动 vs code gate4 硬编码 False）；异常命名漂移（DeadlineExceeded vs WallClockDeadlineExceeded）
- **熔断功能性死亡**：enforce gate_attempts=2 与阈值 2 同步耗尽 → can_execute() 永不返回 False；文本兜底 UNKNOWN_ERROR → 默认 TRANSIENT → "BUSINESS 不计入"被绕过
- **N5 预算错配**：实读 depth_reviewer/conclusion_validator/repair → 每轮真实 27-50 次调用 vs 上限 60 → "需第 2 轮"的报告大概率 T_BUDGET 早停打降级标（arch §8.2"3-5 次/轮"与代码矛盾）

---

## 三、已解决确认（8 轨迹共识 + 审议实读背书）

缺陷 2/3/4/5/7/9/10/11(功能)/12/13/14/17/18 已解决：
- gate4 两条 fail-open → passed=False ✓
- 检查器吞异常 → 白名单 raise + 默认 50 分删除 ✓
- _generate_chapter 短路（v8+legacy 双路径）✓
- with_fallback 换模型单次逃生闭环 ✓
- _budgeted_caller 全链真实接线（非死代码）✓
- enable_debate=False 全覆盖（4 路）✓
- shadow_skip_repair 消费 ✓
- REVIEW_SYSTEM 保留 ✓
- RETRY_POLICY 三模式 ✓ / LLM_EMPTY_OUTPUT 映射 ✓ / 熔断枚举统一 ✓ / 改动7 no-op ✓ / 15 测试 ✓
- legacy workflow.py:2942 兼容（keyword-only 默认值 + v3 re-export 实证）✓

---

## 四、必须修正清单（实施前，按优先级）

| 优先级 | 缺陷 | 修正方案 | 文件 | 验收 |
|---|---|---|---|---|
| P0-A-1 | 缺陷16 签名章节号 | findall 捕获→归一化→还原（注意多数字节） | `_issue_signature` | 第4/5章不同签；第12章不破损；test 绿 |
| P0-A-2 | 缺陷1 豁免 PASS 绕过 | 判据查累积豁免清单 | P0-A-1 | 第4轮空仍 passed=False |
| P0-A-3 | 缺陷6 单调守卫 | 先减后置零；before 取原始集 | P0-B-6 | test_monotonic_guard 绿 |
| P0-B-1 | deadline L4 缺失 | _deadline_guard 包主 caller 或 harness 加 deadline 参数 | workflow/harness_llm | deadline 后调用被拒 |
| P0-B-2 | arch/code 三处矛盾 | 二选一裁决并同步另一册 | v2-arch/v2-code | 两册一致 |
| P0-B-3 | 熔断功能性死亡 | 阈值<attempts 或跨 run 持久化；文本兜底不默认计入 | circuit_breaker/error_classifier | can_execute 真能返回 False |
| P1-1 | N5 预算 60 错配 | 上限提至 ≥200 或 S5 不计预算；修 arch §8.2 | WorkflowConfig/arch | 正常 2 轮不触发 T_BUDGET |

---

## 五、结论

v2 相比 v1 有质的进步：18 项中 15 项实质解决、行号锚点全部属实、终止性四重有界成立。但 **3 项自带测试必红（16/1/6）暴露"修订未经验证闭环"**，加上 deadline 上界失实、arch/code 互斥、预算错配，按 P0/P1 清单修正后（预计 <100 行）方为可靠实施基础。

**核心判断**：v2 的止血方向已验证正确——即使不修正，下一轮运行也不会死循环；修正清单解决的是"报告质量可接受"与"验收可证明"问题。
