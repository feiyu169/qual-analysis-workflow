# 实质审查 vs 红队审查：LLM 调用规则与审查规则对照

> 精确梳理两个"LLM 审查"环节的调用契约（caller 参数、prompt 结构、输出解析）与审查规则
> （维度、判定、收敛）。基于代码逐项核实（2026-08-18）。

---

## 一、定位与触发时机

| | 实质审查（Substantive Review） | 红队审查（Red-Team Review） |
|---|---|---|
| 归属层 | L2 审查修复循环（Gate4 / v2-v7 Step4.7） | L3 最终验证（v8 Gate8） |
| 触发 | 全部章节生成后，审查修复循环内 | 报告组装完成后，Gate8 确定性校验后 |
| 目的 | 发现问题 → **触发修复**（Patch 模式） | 终审 → 致命则**阻断交付**（FAIL） |
| 修复 | ✅ 是（同循环内 patch 修复） | ❌ 否（只读不修，修复走外部循环） |

---

## 二、LLM 调用规则对照

### 2.1 实质审查（`review_repair_loop._run_substantive_review`）

| 子项 | LLM 调用 | caller 参数 |
|---|---|---|
| 事实核查 `check_facts` | **无 LLM**（确定性正则 + canonical 比对） | — |
| 分析深度 `check_depth` | ✅ `llm_caller("depth_review_ch{n}", prompt)` | 复用主流程 caller（workflow 的 llm_caller，即 harness_llm 默认：maxTokens=12000, temp=0.2, 报告撰写 system） |
| 结论合理性 `check_conclusion` | ✅ `llm_caller("conclusion_validation", prompt)` | 同上 |
| 假设合理性 `check_assumptions` | **无 LLM**（确定性，按行业关键词） | — |

**实质审查的 LLM 调用特征**：
- **复用主流程 caller**（`llm_caller(chapter_name, prompt)` 签名，即 harness_llm 的 `llm_caller`）
- 未单独设置 maxTokens/temperature/system → **默认 maxTokens=12000, temp=0.2, 报告撰写 system**（含"必须用 H2/禁止 H3"等格式约束——对审查任务其实不必要）
- prompt 输入：`content[:3000]`（depth_reviewer 截断）/ `_get_content_summary(chapters)`（conclusion 摘要）
- **每章一次调用**（depth_reviewer 逐章；conclusion 一次全报告摘要）

### 2.2 红队审查（`review_integrator.review_report_text` ← Gate8 `_run_redteam_review`）

| 参数 | 值 | 说明 |
|---|---|---|
| caller 构造 | `create_harness_caller(max_tokens=24000, temperature=0.3, system=REVIEW_SYSTEM)` | **专用 caller**（Gate8 内建） |
| system | `"你是资深买方投资分析师（Research QC/红队）。你的任务是批判性审读研究报告，不做报告撰写格式约束。"` | 明确不做格式约束（与实质审查的"报告撰写 system"相反） |
| maxTokens | 24000 | 红队长输出（实质审查 12000） |
| temperature | 0.3 | 略高（实质审查 0.2） |
| 调用签名 | `llm_caller("buy_side_report_review", prompt)` | 单次全报告调用 |
| 输入 | 完整 `report_text` + Wind canonical 锚点表 | 非截断（但 >12000 字符有截断风险，见边界） |

---

## 三、审查规则对照

### 3.1 实质审查（4 子项）

| 子项 | 规则（维度/判定） | 输出 |
|---|---|---|
| 事实核查 | 报告财务数字 vs Wind canonical（营业收入/归母净利/营业利润/总资产/现金流，5%-10% 容差） | issues → `[事实核查]` |
| 分析深度 | 五维：定量分析/数据支撑/敏感性分析/行业对比/历史趋势；关键词初评 + **LLM 评分（0-100）**，综合 = 关键词30% + LLM70%；<阈值 → issue | issues → `[分析深度]` |
| 结论合理性 | LLM 评估：评级与分析一致/估值合理/风险收益比合理/逻辑矛盾；响应含"矛盾/不一致/问题" → issue | issues → `[结论合理性]` |
| 假设合理性 | 确定性：行业假设（毛利率/资本开支）与报告断言比对（按 industry 关键词） | issues → `[假设合理性]` |

**判定**：`passed = 无 issue`；有 issue → 进入 `_repair_chapters`（Patch 模式修复）。

### 3.2 红队审查（buy_side_report_review skill，六 Phase + 自纠闭环）

| 维度 | 规则要点 |
|---|---|
| Phase0 结构识别 | 建 canonical 数据基准表（年报各年营收/净利/现金流…）；标记自评模块待验证 |
| Phase1 数据准确性 | 跨章钩稽、年份锚点校验（增长率反推）、口径一致性（归母vs净利）、币种；**跨章数据集唯一性【致命】**、亏损年份唯一、占位符扫描 |
| Phase2 估值与目标价 | 可比公司正确性、DCF 自洽（**两矛盾 DCF 直接致命**）、目标价三数自洽、情景分析、估值非负性【致命】、多方法收敛【致命】、关键假设有锚【致命】、DCF 算术复核、净负债桥接 |
| Phase3 财务质量 | FCF 定义（含 ΔWC）、ROIC vs WACC、现金流质量 |
| Phase4 投资逻辑 | 局部结论发散（须元裁决）、首尾矛盾【致命】、否决项处理、元裁决规则可推导【致命】（防 override 伪闭环） |
| Phase5 方法论 | 预期差/合理估值断言、辩论结构是否产出裁决、自检模块真实性（100分自评必验） |
| Phase5.5 自纠闭环 | 自纠附录字段完整【致命】、正文闭环【致命】、漏检重跑、过期自纠块【致命】 |
| 严重级别 | 【致命】=阻断 / 【重要】=定稿前 / 【建议】=优化 |

**判定**：`_parse_review_result`（兼容 `F-1/I-1` 编号 + `【致命】` 标签）；`fatal>0` → Gate8 FAIL。

---

## 四、关键差异总结

| 维度 | 实质审查 | 红队审查 |
|---|---|---|
| caller | 复用主流程（maxTokens 12000/temp 0.2/**报告撰写 system**） | 专用（maxTokens 24000/temp 0.3/**审查 system**） |
| 调用粒度 | 逐章/摘要多次 | 全报告单次 |
| 输入 | 章节内容（3000 字截断） | 完整报告 + Wind 锚点表 |
| 锚点 | 部分子项带（fact_checker canonical） | 全带（Wind canonical 锚点表） |
| 输出 | 问题列表 → Patch 修复 | 致命/重要/建议 → 阻断/告警 |
| 修复 | ✅ 同循环 | ❌ 只读 |
| 覆盖 | 深度/结论/事实/假设 | 五维 + 估值深审 + 自纠闭环 |

---

## 五、发现的问题与建议（评审输出）

### 问题 1（重要）：实质审查复用"报告撰写 system"，审查语义被污染
`depth_reviewer`/`conclusion_validator` 用主流程 caller——system 是"撰写报告：必须 H2 禁止 H3/结论要点小节"，对"评估深度/结论合理性"的审查任务不匹配（LLM 可能被引导去产出格式而非判断）。
**建议**：实质审查子项改用与红队一致的审查 system（最小改动：`create_harness_caller(system=审查prompt, max_tokens=8000)`）。

### 问题 2（重要）：实质审查 prompt 无 Wind 锚点注入
`depth_reviewer` 的 prompt 只有 `{content}`；`conclusion_validator` 只有评级+摘要——LLM 评估"数据支撑/估值合理"时**没有标准答案可对照**（红队已修，实质审查未修）。
**建议**：`_run_substantive_review` 的 prompt 注入 Wind canonical 锚点表（复用 `_build_wind_anchor_table`）。

### 问题 3（轻微）：实质审查输入截断
`content[:3000]` 丢弃长章节后半段（R5 章节平均 4000+ 字）——LLM 只见前段。
**建议**：提到 8000 或按骨架小节分段送审。

### 问题 4（轻微）：红队 >12000 字符截断风险
maxTokens 24000 但 harness_llm 的 `_call_bridge` 无输入长度保护；完整 R5 报告 112KB 超上下文。
**建议**：Gate8 红队改为"逐章送审 + 汇总"或按章节分批（红队规则不变，输入分批）。

---

## 六、结论

- **实质审查**：L2 内、复用主 caller、逐章/摘要、4 子项（2 LLM + 2 确定性）、发现问题即 Patch 修复——**是"过程内质检"**
- **红队审查**：L3 终审、专用 caller（24000/0.3/审查 system）、全报告单次、六 Phase + 自纠闭环、致命即阻断——**是"交付前终审"**
- 两者互补：实质审查抓"生成质量问题"并就地修复，红队抓"终稿硬伤"并阻断交付

## 七、改进点落地（2026-08-18）

| 改进 | 落地 |
|---|---|
| ① 实质审查审查 system | `review_repair_loop._run_substantive_review` 构造审查专用 caller（max_tokens=8000/temp=0.3/审查 system "评估深度与结论，不写报告不受格式约束"）传 check_depth/check_conclusion |
| ② 实质审查锚点注入 | `depth_reviewer`/`conclusion_validator` 加 wind_data 参数，prompt 注入 Wind canonical 锚点表；截断 3000→8000；prompt 加"数据是否与 Wind 锚点一致"维度 |
| ③ 红队分批送审 | Gate8 `_run_redteam_review`：报告 >12000 字符时按 `# 第N章` 切分逐章红队补审（每章 ≤12000），批次致命汇总进 errors、重要进 warnings |

验证：全文件编译 ✅；quick 回归 Gate0-7 PASS、Gate8 正确拒绝 R5 ✅
