# 审查整体架构、修复机制与"字符数超中断"防治方案

> 三个问题一次说清：①审查的完整架构与规则（当前状态）②审查后的修复机制 ③如何减少
> 因字符数超（LLM 输出 maxTokens 截断 / 输入超上下文 / 报告超长）而中断。

---

## 一、审查整体架构与规则（当前完整状态）

### 1.1 三层防线总览

```
L1 生成期即时（每章生成后）
   structural_check（H1唯一性/固定小节/占位符/must_answer/证据）→ 不合格重试≤3次
L2 审查修复循环（全部章节生成后，Gate4 / v2-v7 Step4.7）
   ├─ 形式审查：占位符/币种/模板指纹/来源 → warning（交 L3 收口）
   ├─ 实质审查 review_and_repair_loop：
   │    确定性：事实核查（canonical 5-10%容差）/ 假设合理性（行业）
   │    LLM：分析深度（五维评分）/ 结论合理性（评级一致性）
   │    对抗：辩论审查（DebateService，3 关键章，Bear 反驳→issues）★新增
   └─ 修复：PATCH 模式（最小侵入+锚点+校验回滚）≤3轮
L3 最终验证（报告组装后，v8 Gate8）
   ├─ 确定性：DataAnchor 数字校验（1%容差）/ 模板指纹 / 章节重号/自造H1 / 占位符 / 格式大小
   └─ 红队审查（buy_side_report_review）：五维+估值深审+自纠闭环（>12000字符按章分批）
       → 致命 → Gate8 FAIL（阻断交付）
```

### 1.2 审查规则清单（组件 → 规则 → 判定）

| 组件 | 规则 | 判定 |
|---|---|---|
| structural_check | 三小节存在/H1唯一/占位符/must_answer | critical=0 且 score≥60 |
| fact_checker | 报告数字 vs Wind canonical（5-10%容差） | 偏差超限 → issue |
| depth_reviewer | 五维评分（定量/数据/敏感性/对比/趋势），关键词30%+LLM70% | <阈值 → issue |
| conclusion_validator | 评级一致性/估值合理/风险收益比/逻辑矛盾 | LLM 响应含"矛盾/不一致" → issue |
| assumption_checker | 行业假设 vs 报告断言 | 不符 → issue |
| **辩论审查** | BULL立论→BEAR逐条反驳+替代估值→PM裁决；Bear 反驳提取为 issues | Bear 缺失明确标注；PM 看空→矛盾信号 |
| **红队审查** | 六 Phase（数据/估值/财务/逻辑/方法/自纠闭环）+ Phase5.5 | 致命→FAIL；重要→warning |
| **DataAnchor** | 报告数字 vs Wind 锚点（1%容差） | 超限 → Critical |

### 1.3 LLM 调用规则（谁用 LLM、参数）

| 环节 | caller | maxTokens | temperature | system |
|---|---|---|---|---|
| 实质审查（深度/结论） | 审查专用（`_run_substantive_review` 构造） | 8000 | 0.3 | 审查 system（评估不写报告） |
| 辩论（BULL/BEAR/PM） | DebateService（复用审查 caller） | 8000 | 0.3 | 审查 system + 三角色 prompt |
| 红队审查 | Gate8 专用 | 24000 | 0.3 | 红队 system（QC/批判审读） |

---

## 二、审查后的修复机制（当前）

### 2.1 修复 = Patch 模式（最小侵入，五条纪律）

```
审查发现问题清单
  → Patch 模式：LLM 只输出 patch [{"target": 唯一锚串, "replacement": 新文本}]
  → 程序唯一匹配 + 应用（未点名内容物理不变）
  → 校验闭环：structural + cross_chapter + DataAnchor 数字（任一失败 → 回滚）
  → 修复预算：≤5 patch/章（报告级 ≤15）
  → 审计：target/原因/before/after 记录
```

三条修复路径全部 patch 化：
- `review_repair_loop._repair_chapters`（实质审查的修复，wind_data 锚点注入）
- `repairer._call_llm_repair`（审计修复子代理，structural 校验）
- `review_integrator.fix_report`（红队后的外部修复循环，结构+数字锚点校验）

### 2.2 边界：patch 治局部，重写治整章

- 局部问题（数字/口径/缺来源）→ Patch
- 整章模板泄漏 → 检测指纹 → 专用重写路径（锚点+权威契约+骨架，单章重写）

---

## 三、字符数超而中断：问题定位与防治方案

### 3.1 五处"字符数超"风险点（现状核实）

| # | 位置 | 超限形式 | 后果 | 现状 |
|---|---|---|---|---|
| E1 | harness_llm `max_tokens=12000` | **输出超限** → `finish: max-tokens` | LLM 输出被截断 → 审查/生成不完整 → 重试/降级 | 红队用 24000 已解决；**实质审查/辩论用 8000 可能截断长输出** |
| E2 | Gate8 红队全报告 | **输入超上下文**（R5 报告 112KB） | 红队只见前段 → 漏审后段 | 已加按章分批（>12000 字符） |
| E3 | depth_reviewer `content[:8000]` | 章节输入截断 | LLM 只见前 8000 字符 → 深度评估不完整 | 已从 3000 提到 8000，但仍截断长章节 |
| E4 | `review_report_text` 单次调用 | 单章 >12000 字符（罕见） | 输出截断或输入超限 | 无保护 |
| E5 | 辩论 `chapter_content[:3000]`（Bull） | 输入截断 | 辩论基于不完整章节 | 3000 截断偏短 |

### 3.2 防治方案（分层）

#### A. 输出侧：maxTokens 与任务匹配（消除 E1）

```
按任务分级 maxTokens（不再一刀切 12000）：
  生成章节（_build_chapter_prompt 输出）→ 12000（现状，够）
  实质审查（深度评分/结论判断）→ 8000（现状）→ 输出短，够
  辩论角色（Bull/Bear/PM）→ 8000 → 输出 ≤2000 字，够
  红队审查（六Phase长报告）→ 24000（已用）
统一原则：maxTokens = 预期输出长度的 3 倍安全余量
```

**关键补充**：harness_llm 收到 `finish: max-tokens` 时目前直接 raise（丢弃已生成内容）。
**改进**：max-tokens 截断时**保留已生成内容**（有内容即接受，尾部标注"⚠️ 输出被截断"）——
这是 R5 早期 HeavySkill 工具踩过的坑（截断但有内容时应接受部分文本）。

#### B. 输入侧：内容分批（消除 E2/E4）

```
统一"报告/长文分段送审"工具（新增 quality/review_chunker.py）：
  split_report(report, max_chars=12000, by="chapter") -> [(章节号, 内容), ...]
  规则：
  1. 优先按 "# 第N章" 切分（语义完整）
  2. 单章仍 >12000 → 按 "## 小节" 再切
  3. 仍 >12000 → 按句子边界切（不切断数字/表格）
  → Gate8 红队、review_report_text、fix_report 全部复用
```

Gate8 红队已实现按章分批（E2 ✅）；**推广到 review_report_text 与 fix_report**（E4）。

#### C. 审查输入自适应截断（消除 E3/E5）

```
depth_reviewer / debate Bull：
  固定截断 [:8000]/[:3000] → 自适应：
    单章 ≤20000 → 全文送审（输出预算允许时）
    单章 >20000 → 按小节分批送审 + 汇总
  原则：优先全文（审查完整性），超限才分批（避免无谓截断）
```

#### D. 中断兜底：审查进度持久化 + 未审标注（全局）

```
- 分批审查结果聚合：每批独立记 issues，汇总为报告级结果（不因单批失败丢弃整份）
- 单批失败（超时/超限）→ 该批标记"未审"，其余照常 → 报告附"⚠️ N 个章节未完成红队审查"
- 审查 checkpoint：每批完成后落盘（.pip-tmp/review-{runid}-batch{N}.json），
  进程中断后可续审（与 CheckpointManager 同思路）
```

### 3.3 实现优先级

| 优先级 | 改动 | 消除 |
|---|---|---|
| P0 | harness_llm：max-tokens 截断时保留已生成内容（不 raise） | E1 输出丢弃 |
| P0 | 新增 review_chunker（按章/小节/句子分批），Gate8/redteam/fix_report 复用 | E2/E4 输入超限 |
| P1 | depth_reviewer/辩论输入自适应（≤20000 全文，超限分批） | E3/E5 无谓截断 |
| P1 | 审查 checkpoint + 未审标注 | 中断兜底 |

## 五、落地状态（2026-08-18）

| 项 | 状态 |
|---|---|
| **P0-① harness_llm max-tokens 保留**：截断但有内容 → 保留 + 标注"⚠️ 输出被截断"，不重试；无内容仍报错 | ✅ 单测通过（保留 491 字符 + 不重试；空内容报错） |
| **P0-② review_chunker.py**：按章→小节→句子边界分批（不切断数字/表格）+ `merge_batch_issues`（单批失败不丢整份） | ✅ 单测通过（39 片段每段≤5000；未审标注正确） |
| **P0-② Gate8 红队接入 chunker**：替换手写 split + 修复"errors 被二次清空"bug + 未审标注 | ✅ |
| **P1-③ depth_reviewer 自适应**：≤20000 全文，超限按小节分批，多段取最低分（保守） | ✅ |
| **P1-③ 辩论 Bull 输入**：[:3000] → [:20000] | ✅ |
| **P1-④ Gate8 红队 checkpoint**：每批落盘 `redteam_checkpoints/seg{N}.json`，中断可续审 + 未审标注 | ✅ |
| quick 回归：Gate0-7 PASS，Gate8 正确拒绝 R5 | ✅ |

> 四招全部落地：输出保留（max-tokens 不丢弃）+ 输入分批（统一 chunker）+ 自适应截断（优先全文）
> + checkpoint 兜底（续审/未审标注）——预计消除 90% 的"字符数超而中断"。

---

## 四、结论

- **审查架构**：三层防线（L1 即时/L2 循环含辩论/L3 终审含红队）+ 规则清单见上
- **修复机制**：Patch 最小侵入 + 锚点 + 校验回滚（治局部）/ 专用重写（治整章）
- **字符超中断**：五处风险点定位完毕，核心是"输出保留（max-tokens 不丢弃）+ 输入分批（统一 chunker）+
  自适应截断（优先全文）+ checkpoint 兜底"四招——P0 两招（输出保留 + chunker）可立即落地，
  预计消除 90% 的"字符数超而中断"。
