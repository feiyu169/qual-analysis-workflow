# 深度审查架构确认（Deep Review Architecture）

> 确认当前"深度审查"体系的完整架构：从"发现问题"到"修复"到"最终验证"的每一层、每个组件、
> 每个数据流。回答：审查体系由什么构成、如何避免引入新矛盾、边界在哪。

---

## 一、架构总览（三层防线）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 第一层：生成期即时校验（L1 - 每章生成后）                                 │
│   structural_check（H1 唯一性/固定小节/占位符/must_answer）                │
│   → 不合格 → 重试（≤3 次，格式修正 prompt）                               │
├─────────────────────────────────────────────────────────────────────────┤
│ 第二层：审查修复循环（L2 - 全部章节生成后）                                │
│   Gate4 审计修复（v8） / Step4 审计修复（v2-v7）                           │
│   ├─ 形式审查：占位符/币种/模板指纹/来源 → warning（交 L3 收口）            │
│   ├─ 实质审查：review_and_repair_loop（deep + substantive）               │
│   └─ 修复：PATCH 模式（最小侵入 + 锚点 + 校验回滚）                        │
├─────────────────────────────────────────────────────────────────────────┤
│ 第三层：最终验证（L3 - 报告组装后）                                        │
│   v8 Gate8 双层校验：                                                     │
│   ├─ 确定性：DataAnchor 数字校验（报告数字 vs Wind 锚点 1% 容差）           │
│   │         + 模板指纹 + 章节重号/自造 H1 + 占位符 + 格式/大小              │
│   └─ 红队审查：buy_side_report_review（LLM 五维审读 + Phase 5.5 自纠闭环） │
│       → 致命问题 → Gate8 FAIL（阻断交付）                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 二、审查组件清单（现状）

| 组件 | 位置 | 作用 | 状态 |
|---|---|---|---|
| `structural_check` | quality/structural_check.py | 结构预检：H1 唯一性/三小节/占位符/must_answer/证据 | ✅（本轮加 H1 唯一性） |
| `semantic_audit` | quality/auditor.py | LLM-as-Judge 语义审计（契约覆盖/边界/视角/数据/逻辑） | ✅ |
| `repair_chapter` | quality/repairer.py | 章节修复（**PATCH 模式**，本轮改） | ✅ |
| `review_and_repair_loop` | quality/review_repair_loop.py | 审查修复循环（deep+substantive，**PATCH 修复**，本轮改） | ✅ |
| `cross_chapter_consistency` | quality/cross_chapter_consistency.py | 跨章数字/结论一致性 | ✅ |
| `logic_consistency_check` | quality/logic_consistency_check.py | 逻辑矛盾检测（Gate4 用） | ✅ |
| `date_anchor_check` | quality/date_anchor_check.py | 日期锚点检查 | ✅ |
| `data_reasonableness_check` | quality/data_reasonableness_check.py | 数据合理性（vs Wind） | ✅ |
| `fact_checker` | quality/fact_checker.py | 事实核查（canonical 键，本轮修） | ✅ |
| `DataAnchor` | qual_v8/data_anchor.py | 唯一数据锚点：canonical+财年+1% 校验 | ✅ |
| `ReviewIntegrator` | quality/review_integrator.py | 红队审查（buy_side_report_review skill 代码化） | ✅ |
| `patch_applier` | quality/patch_applier.py | **PATCH 应用器**：唯一匹配/预算/校验回滚 | ✅（本轮新增） |

---

## 三、审查如何避免引入新矛盾（本轮核心成果）

### 3.1 修复最小侵入（Patch 模式）—— 替代整章重写

```
旧：LLM 输出"完整章节/完整报告" → 未点名内容可能被改坏 → 引入新矛盾
新：LLM 只输出 patch [{"target": 唯一锚串, "replacement": 新文本}]
    → 程序唯一匹配 + 应用 → 未点名内容物理不变 → 不可能引入新矛盾（局部）
```

三条修复路径全部 patch 化：
- `review_repair_loop._repair_chapters`（v2-v7 Gate4 实质审查的修复）
- `repairer.repair_chapter`（v2-v7 审计修复的修复子代理）
- `review_integrator.fix_report`（红队审查后的外部修复循环）

### 3.2 修复带锚点（杜绝自由发挥）

每条修复 prompt 注入：
1. **Wind canonical 锚点表**（`_build_wind_anchor_table` / DataAnchor 动态表）
2. 指令："修复后的财务数字必须与锚点一致；禁止引入锚点外的新数字/新事实/新观点"

### 3.3 修复后校验闭环（失败回滚）

`apply_patches` 内置校验器链：
```
structural_check（H1 唯一性/固定小节/占位符）
  + cross_chapter_consistency（跨章数字）
  + DataAnchor 数字校验（报告数字 vs Wind 锚点 1% 容差）
任一失败 → 回滚到修复前版本（不接受部分修复）
```

### 3.4 修复预算 + 单调性

- 每轮 ≤5 patch（报告级 ≤15）；超限拒绝
- 单调性守卫：修复后校验分 ≥ 上轮；下降 → 回滚（待补全实现）

### 3.5 边界：patch 治局部，重写治整章

- **局部问题**（数字错/口径混/缺来源）→ Patch 模式（最小侵入）
- **整章问题**（模板泄漏 ch8/ch9 整章是别的公司）→ 检测模板指纹命中 → 专用重写路径
  （注入锚点+权威契约+骨架，单章重写）——两者分开

---

## 四、数据流（一次完整审查）

```
报告生成（Gate3/v2-v7）
  → L1 structural_check（每章即时，不合格重试）
  → L2 Gate4 审计修复
       形式审查（占位/币种/模板指纹/来源）→ warning
       实质审查 review_and_repair_loop
         深度审查（跨章一致/逻辑/数据合理/估值仲裁/日期锚点）
         实质审查（事实核查/分析深度/结论合理/假设合理）→ 问题清单
         PATCH 修复（锚点注入 + 校验回滚）→ 循环 ≤3 轮
  → L3 Gate8 最终验证
       确定性：DataAnchor 数字校验 + 模板指纹 + 章节重号/自造H1 + 占位符
       红队审查（ReviewIntegrator）：五维审读 + 自纠闭环
       致命 → FAIL（阻断交付）；重要 → warning
  → 报告（合格）或 返工（FAIL + 问题清单）
```

---

## 五、审查体系的能力边界（诚实说明）

| 能力 | 现状 | 说明 |
|---|---|---|
| 数字一致性 | ✅ 机器级 | DataAnchor 1% 容差，报告任何数字 vs Wind 锚点 |
| 结构固化 | ✅ 机器级 | H1 唯一性/固定小节/章节重号/自造 H1 |
| 模板泄漏 | ✅ 机器+LLM | 关键词指纹（Gate4/8）+ 红队审读 |
| 逻辑矛盾 | ✅ LLM | logic_consistency_check + 红队 |
| 估值自洽 | ⚠️ 部分 | DCF 一致性检查存在，但无"重算 DCF"能力 |
| 财年/口径 | ✅ 机器+LLM | 财年锚定（P0-B1）+ 仲裁（P0-B2）+ 红队 Phase1 |
| 自纠闭环 | ✅ LLM | 红队 Phase 5.5（字段完整/正文闭环/时效性） |

**剩余风险**：
1. Patch 模式依赖 LLM 正确输出唯一 target（失败时降级整章，需人工抽查）
2. 单调性守卫（校验分下降回滚）尚未完全实现
3. 红队审查（L3 LLM 层）对 >12000 字符报告会截断（完整模式建议分批）
4. 审查本身是"发现-修复"闭环，若问题在 Wind 锚点之外（如行业判断错误），红队 LLM 是唯一防线

---

## 六、结论

**深度审查架构已成型**：三层防线（L1 即时 / L2 循环 / L3 最终）+ 五条纪律（Patch 最小侵入/锚点/校验回滚/预算/审计）。
核心创新是把"修复"从"整章重写"改为"Patch 应用"——**从机制上杜绝了审查引入新矛盾**（未点名内容物理不变），
并配以锚点注入 + 校验闭环 + 回滚，确保每次修复只会修正、不会破坏。
