# 小鹏(9868.HK) v8 分析运行死循环——根因分析

日期：2026-08-19
运行：pwsh-18（`run_xpev_full.py`，v8 QualWorkflow，qual_mode=shadow）
现象：运行 6+ 小时未完成，卡在 Gate4 审查修复循环，无收敛，被迫终止。

## 一、运行事实（日志实测）

| 指标 | 数值 |
|---|---|
| 运行时长 | 01:00 → 07:10+（6+ 小时，终止时仍在 Gate4） |
| LLM 调用总数 | 223 次开始 / 201 完成 / 108 失败（失败率 48%） |
| 失败类型 | **106/108 = max-tokens 空输出**（桥接返回 ok=False + text="" + finish=max-tokens） |
| 失败耗时 | 每次 70-120s 超时（3 次尝试 × ~90s = 单次调用最坏 ~5 分钟） |
| 跨章一致性 issues | Gate3: 58 → 50 → 61 → 88 → 81（**无收敛**，且含大量假阳性） |
| 修复结果分布 | 大量"patch 解析为空/保留原文"+"patch 校验失败/回滚" |

## 二、核心问题：三层嵌套重试 × LLM 空输出 = 指数级耗时

### 层级 1：LLM 调用层（harness_llm.py）
- `create_harness_caller(max_retries=2)`：每次调用失败重试 2 次（共 3 次尝试），间隔 sleep 2s/4s
- 桥接高频返回 `ok=False + text="" + finish=max-tokens`（宿主 LLM 路由 deepseek-v4-flash 在长 prompt 下频繁空输出）
- 单次"成功"调用（含 2 次失败重试）最坏耗时 = 3 × 90s ≈ 4.5 分钟

### 层级 2：Gate4 审查修复循环（review_repair_loop.py）
- `review_and_repair_loop(max_rounds=3)`：每轮 = 深度审查 + 实质审查 + patch 修复
- 每轮对每个有问题章节调用 repair_patch（LLM 生成 patch JSON）
- 跨章一致性 50-88 项问题大部分是**假阳性**（详见第三节）→ 修复循环空转：
  - 假问题 → LLM 返回 `{"patches":[]}`（空 patch）→ "保留原文" → 下轮同样问题再现
  - 真问题（如 ch6 总资产 173.3 vs 锚点 1031.63）→ patch 应用后校验失败 → 回滚 → 下轮同样问题再现
- 3 轮 × 每轮 10 章 × 每章多次 LLM 调用 × 每调用 3 次尝试 = 数百次 LLM 调用

### 层级 3：Gate 级重试（qual_v8/workflow.py + gate_engine.py）
- `WorkflowConfig.max_retries=3` → `max_attempts = 1 + 3 = 4`
- Gate4 `spec.max_retries=3`，`spec.timeout=1200`（20 分钟）
- Gate4 每失败一次（check_criteria 不通过）→ `can_retry()` 为真 → 整个 Gate4 重新执行
- 即 Gate4 最多执行 **4 次完整审查修复循环**（每次 3 轮 × 10 章）

### 总复杂度
```
Gate4 执行次数(≤4) × 修复轮数(3) × 章节数(10) × LLM调用(每章2-4) × 尝试次数(3) × ~90s
≈ 4 × 3 × 10 × 3 × 3 × 90s ≈ 9720 分钟 ≈ 162 小时（理论最坏）
```
即使乐观估计（部分成功），6 小时不收敛完全符合此结构。

## 三、审查假阳性的具体来源（已修复 16 项，仍残余）

### 已修复（本次会话累计 16 处）
1. `cross_chapter_consistency` 财务一致性：首匹配 → 多财年分组（108 假冲突 → 消除）
2. `cross_chapter_consistency` 结论一致性：按章节 → 按财年分组
3. `cross_chapter_consistency` 时间一致性：指标张冠李戴 → 按指标匹配
4. `cross_chapter_consistency` 财务/时间比较：无容差 → 1% 容差跳过
5. `date_anchor_check`：章节间年份不同 → 只报"主引用历史且无最新财年"
6. `numeric_guard`：万亿单位、价格带、细分市场、计数词、万元级豁免
7. `data_anchor.validate_chapter_any_fy`：最新财年 → 任一财年命中
8. `gate4` 传 `_year_labels`（FYNone 修复）
9. `structural_check` set 下标 bug
10. `harness_llm` finishReason 字段 + 直连 fallback

### 残余（Gate3 仍 50-88 项）
- 跨章一致性检查器对**章节内部多口径表述**（如"约767亿"vs"767.20亿"vs"767.2亿"）仍有少量假阳性
- `_check_time_consistency` 的 `_extract_data_for_time` 对同一年份的多个指标值取最近匹配，可能与财务一致性重复报
- 深度审查（depth_review）每轮都报 11-13 项——部分是真实质量建议，但**每轮修复后重新审查必然再现**（审查是静态规则，不因修复降级）

## 四、架构级根因（三层问题叠加）

### A. 重试策略无"幂等失败"识别（最致命）
- LLM 空输出（max-tokens）被当作"瞬时错误"重试 3 次，但**该错误是确定性的**（deepseek-v4-flash 长 prompt 空输出的模式稳定）
- 无"连续 N 次同类失败 → 熔断降级"的机制（circuit_breaker 只在 Gate 级，不在 LLM 调用级）

### B. 审查-修复循环无收敛判定
- `review_and_repair_loop` 只看"问题数是否归零"作为通过标准
- 假阳性问题**永远修不掉**（LLM 无从下手 → 空 patch）→ 3 轮必然跑满
- 无"问题数比上轮减少 X% 才继续，否则提前终止"的收敛检查
- 无"同一问题跨轮重复出现 N 次 → 标记为检查器假阳性并豁免"的机制

### C. 嵌套重试无总量上限
- 3 层重试（LLM 层 × Gate4 内循环 × Gate 级）各自独立设上限，但**乘积无上限**
- 无全局超时（整个 workflow 无总时长预算）
- Gate4 spec.timeout=1200s 只约束单次 execute，不约束 4 次重试总时长

### D. 质量闸门在 shadow 模式下的悖论
- qual_mode=shadow：Gate4 失败不阻断报告产出
- 但 v8 引擎**仍然执行全部重试**后才放弃 → shadow 模式没省时间，反而把"应直接失败"变成"4 次完整重试后失败"

## 五、代码级根因（具体文件）

| 文件 | 问题 |
|---|---|
| `workflow.py:260` | `max_attempts = 1 + config.max_retries`（=4），Gate4 失败全量重跑 |
| `gate4.py:72` | `max_retries=3`（GateSpec），与 WorkflowConfig.max_retries 叠乘 |
| `review_repair_loop.py` | `max_rounds=3` 固定，无收敛早停；假阳性问题无豁免 |
| `harness_llm.py:101-123` | 空输出重试 2 次，无"空输出即永久失败"分支 |
| `bridge`(宿主) | deepseek-v4-flash 长 prompt 空输出（finish=max-tokens, text=""），不可靠 |
| `cross_chapter_consistency.py` | 残余假阳性（多口径数字、时间/财务重复报） |

### 关键代码缺陷（评审前补充确认）

**K1 — 审查 caller 绕过直连 fallback（最重要）**
- `review_repair_loop.py:185-194`：`_run_substantive_review` 用 `create_harness_caller()` **新建审查专用 caller**（max_tokens=8000, system=REVIEW_SYSTEM）
- 该 caller **未经过** run_xpev_full 的 `_llm_with_fallback` 包装（桥接连续失败 3 次切直连）
- 本轮审查类调用占 50%+（depth_review ×10 章、conclusion_validation、辩论 bull/bear/pm ×3 章）
- 桥接空输出时：审查 caller 3 次重试全失败 → raise → 被 gate4.py:276 `except` 吞掉（"实质审查失败"）→ 下轮重跑同样失败
- **结果：直连 fallback 形同虚设，审查阶段在桥接故障时必然反复空转**

**K2 — 审查每轮无状态重复**
- `review_repair_loop.py:59-68`：每轮**重新执行全量审查**（`_run_deep_review` + `_run_substantive_review`），而非"问题清单驱动"
- 深度审查（depth_review）是 LLM 调用 → 每轮 10 章重复审查 → 修复后**必然**再次触发同样问题（静态规则）
- 上轮已修复/已豁免的问题，下轮重新出现 → 无收敛可能

**K3 — patch 空/回滚不改变问题清单**
- `_repair_chapters`（review_repair_loop.py:267+）：patch 空 → "保留原文"；patch 校验失败 → 回滚
- 问题清单原样传入下一轮（`chapters` 未变）→ 下轮 LLM 面对同样 prompt → 同样空/回滚 → 死循环

**K4 — `_llm_with_fallback` 计数被成功重置**
- run_xpev_full.py `_llm_with_fallback`：`_fail_count` 在每次成功时清零
- 桥接故障**间歇性**（非持续）→ 计数反复清零 → 永不达 3 次阈值切直连

## 六、修复方向（供专家评审）

### 短期（止血）
1. **LLM 层**：`harness_llm` 空输出（ok=False 且 text 为空）→ 不重试，直接抛"确定性失败"
2. **Gate4 收敛**：`review_and_repair_loop` 加收敛判定——本轮问题数 ≥ 上轮 90% 且修复成功数=0 → 提前终止；同一问题跨轮出现 ≥2 次 → 标记检查器假阳性，从后续轮次豁免
3. **Gate 级**：Gate4 失败后仅重试 1 次（而非 3 次）；或 shadow 模式下失败直接跳过重试
4. **全局**：Workflow 加总时长预算（如 90 分钟），超时强制产出当前状态

### 中期（架构）
5. LLM 调用级熔断器：连续 3 次同类失败 → 切直连 API（已有雏形，但未覆盖 harness_llm 内部重试）
6. 审查-修复循环改"问题清单驱动"：修复前冻结问题清单，修复后只验证清单内问题，不重新跑全量审查
7. 假阳性自学习：patch 空/回滚累计 N 次的问题 → 自动加入检查器豁免列表

## 七、本次会话已实施的修复清单（16 项，全部测试通过）
见 PROGRESS.md"第五/六/七轮修复"节；单测 30+ passed，各验证器场景实测通过。
