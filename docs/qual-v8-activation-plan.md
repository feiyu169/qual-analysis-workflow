# V8 引擎可运行化方案（qual_v8 Activation Plan）

> 目标：把 v8 从"设计文档级脚手架"变为**可运行的质控引擎**——9 个 Gate 全部调用 v2-v7 已验证的真实组件，
> 引擎机制（check_criteria/重试/flow_definition/模式）落地，DataAnchor 修复为真正生效的唯一数据源。
> 验收：用真实数据（wind_data.json + HKEX 年报 + harness llm 桥接）跑通 `QualWorkflow().execute()`，
> Gate0-8 全部 passed 且能抓到 R5 型问题（财年混用/数字矛盾/模板泄漏）。

---

## 阶段总览（依赖顺序）

| 阶段 | 内容 | 依赖 | 验证方式 |
|---|---|---|---|
| A | 引擎机制修复（workflow.py） | 无 | 单元：execute 空上下文跑通、check_criteria 被调用、enforce 可阻断 |
| B | DataAnchor 修复（data_anchor.py） | A | 单元：Wind 初始化→锚点生效→跨章校验能抓矛盾 |
| C | 逐 Gate 灌入真实组件（gate0-8） | B | 单元：每 Gate 用真实数据 execute |
| D | 端到端验证（run_qual_v8.py） | C | 集成：真实数据全链跑通，Gate 全 passed |

---

## 阶段 A：引擎机制修复（qual_v8/workflow.py）

**A1. 补全 `_get_flow_definition`**：gate_0~8 完整定义（当前只有 0/1，其余是注释）。
每个 Gate 定义含：name / preconditions / execution_steps / pass_criteria。
- gate_0 数据源验证（pre: 无；criteria: filing 存在 + Wind canonical 覆盖率≥0.95 + 3年范围）
- gate_1 类型推断+事实提取（pre: 0；criteria: 市场类型 + 必填字段 + 数值偏差≤2%）
- gate_2 数据收集+DCF（pre: 1；criteria: FCF≠0 + WACC∈[5%,15%] + 永续∈[1%,5%] + 增长∈[-30%,100%] + 税率∈[10%,35%]）
- gate_3 逐章写作（pre: 2；criteria: 11章完整 + 字数≥500 + 无占位符 + 数据一致）
- gate_4 审计修复（pre: 3；criteria: 格式错误=0 + 来源标注 + 日期锚点 + 币种统一 + 估值一致 + 矛盾≤2 + 风险覆盖≥8）
- gate_5 质量增强（pre: 4；criteria: 估值正确 + DCF 范围 + 组件集成 + 参数一致）
- gate_6 结论（pre: 5；criteria: 决策章≥1000字 + 概览章≥500字 + 评级有效 + 评级估值一致）
- gate_7 问题转化+记忆（pre: 6；criteria: 转化成功 + schema 有效 + 记忆存储）
- gate_8 最终验证（pre: 7；criteria: 全 Gate 通过 + 无 Critical + 人工确认 + 格式 + 大小50-500KB）

**A2. `execute` 真实化**：
- 每 Gate 执行后调用 `gate.check_criteria(context)`，结果并入 GateResult.details（`check_criteria_passed`）
- 重试真实化：`can_retry()` 时真正重新调用 `gate.execute(context)`（当前是 `increment_retry(); pass` 空操作），
  最多 `spec.max_retries` 次；重试前把上次 errors 注入 context 供 Gate 修正
- 模式支持：读取 `context["qual_mode"]`（shadow/soft/enforce）——
  - shadow：记录 check_criteria/supervisor 结果，不阻断
  - soft：记录 + 告警日志
  - enforce：check_criteria 或 supervisor 失败 → `ComplianceBlockedException` 阻断（当前 workflow 只记录）
- Gate 结果写入 `context["gate_{n}_result"]`，供后续 Gate（如 Gate7 收集问题）消费

**A3. 状态机集成**：workflow 的 `results` 与 `state_machine` 保持同步；
workflow 终态由"全部 passed"决定（现状正确，保留）。

---

## 阶段 B：DataAnchor 修复（qual_v8/data_anchor.py）

**B1. 修 `_extract_data` 死代码**（当前匹配数字后从不写入字典）：
- 提取 `(指标关键词, 数字, 单位)` 三元组写入 `data`，键为指标名
- 支持财年感知：识别行内 `FY20XX` / `2024年` 上下文，键格式 `指标@FY20XX`

**B2. 修 `init_from_wind_data` 键契约**（当前期望 `年营业收入` 等，canonical 键是 `营业收入` 等）：
- 走 canonical 键 + 别名表（`quality/wind_field_mapper.py` 或内置 FIELD_ALIASES）
- 不只看 `values[-1]`：3 年列表 + `_year_labels` 一起存入锚点 → 锚点带财年维度

**B3. DataPoint 加 `fiscal_year`**：
- `set_anchor(key, value, unit, source, fiscal_year=None)`
- `validate_chapter`：只校验"报告中出现且锚点有同财年"的数字，避免跨财年误报
- 1% 误差容忍保留；误差>1% 报错（P0 级）

**B4. CrossChapterValidator 保留**，改为消费修复后的 DataAnchor。

---

## 阶段 C：逐 Gate 灌入真实组件

| Gate | 占位现状 | 灌入真实实现（v2-v7 已验证组件） |
|---|---|---|
| 0 | `_fetch_*` 模拟 success；`_check_data_range` return True | 校验 `context["filing_data"].sections` 非空；Wind canonical 键覆盖率（收入/净利/现金流/总资产/净资产/负债全在且为 3 年列表）；`_year_labels` 长度≥3 |
| 1 | `_extract_facts` 硬编码 revenue=100.0 | `fact_extractor.extract_facts(sections, company_name, ticker, market, llm_caller, wind_data)`；`infer_market` 替换自定义推断；偏差校验改为与 Wind canonical 值比对 |
| 2 | 英文键取数 → FCF=0 | `workflow.extract_dcf_params(wind_data, shares)`（真实 DCF：OCF-Capex、CAPM WACC、3年 CAGR clamp）；参数范围校验保留 |
| 3 | `"第{i}章内容"*100` | 分章生成：`workflow._build_chapter_prompt(chapter_num, ctx, previous)` + `_generate_chapter(chapter_num, prompt, ctx, llm_caller)` 循环 11 章；一致性检查用 `quality.cross_chapter_consistency` |
| 4 | 全部"这里应该实现"注释 | `quality.review_and_repair_loop(chapters, ctx, llm_caller, wind_data, max_rounds=3, industry)`（含 deep+substantive 审查与修复循环）；`structural_check` + `semantic_audit` + `repair_chapter` |
| 5 | 错键估值；组件全 append | `quality_enhancer.enhance_report_quality(...)`（**修正硬编码**：shares/current_price/fiscal_year 从 context 强传，无默认）；`base_valuation.compute_base_valuation`；`stress_test.run_stress_test` |
| 6 | 正则评级（有实现） | 保留评级提取 + 评级-估值一致性；决策章/概览章生成接入 `workflow._generate_decision_chapter/_generate_overview_chapter`（真实 LLM） |
| 7 | 记忆存储占位 | 问题转化保留（ReviewIssue 结构化）；记忆存储调用 `workflow._store_memory(ctx, report)`（真实 MCP 指令生成） |
| 8 | Critical/人工/格式全占位 | **新增数字校验器**（报告内财务数字 ↔ Wind 锚点 ±容忍度，差异 P0）；**模板指纹检测**（组合构建/沪深300/元/股/买入/其他公司名黑名单）；结构校验（H1 唯一性/章节号连续）；报告大小保留 |

**C0. 通用适配层**（新增 `qual_v8/adapters.py`）：
- `build_data_context(ticker, company_name, market, wind_data, filing_data, facets)` →
  调 `workflow._collect_data` 返回 DataContext（Gate 间共享）
- `canonical_aliases()`：键别名表（`年营业收入→营业收入` 等），供 Gate0/2 与 DataAnchor 共用

---

## 阶段 D：端到端验证（run_qual_v8.py）

**D1. 脚本**：复用 run_qual_full.py 数据链路（wind_data.json + `fetch_filing` + `create_harness_caller`），
构造 context 调 `QualWorkflow().execute()`，输出每 Gate passed/score/errors + 总报告。
**D2. 断言**：
- Gate0-8 全部 passed（真实数据应通过）
- 数字校验器/模板指纹能抓到 R5 已知问题（用 R5 章节预填 context 的负向测试：应报 P0）
- `enforce` 模式下注入矛盾数据 → 应阻断
**D3. 回归**：`workflow.run_analysis`（v2-v7 单体）不受影响（v8 挂载仍 shadow，除非显式启用）。

---

## 风险与边界

1. **LLM 依赖**：Gate1/3/4/5/6 需要 `llm_caller`（harness 桥接）。阶段 C 单测用轻量 stub；阶段 D 用真实桥接（需 llm-bridge 插件运行）。
2. **时长**：Gate3 全量 11 章 LLM 生成 ~30-90min。阶段 D 提供 `--quick` 模式（章节预填 R5 现有内容，只跑 4/5/6/7/8 检查链）。
3. **不改 v2-v7 行为**：所有改动限定 `qual_v8/` 与新增适配层；`workflow.py:2256` 的 shadow 挂载保持默认不动，仅在显式 `QUAL_MODE=enforce` 时升级。
4. **人工确认（Gate8）**：默认 `human_confirmed=True`（自动化），保留接口供 GUI 触发。
