# Qual 工作流架构级归因（R5 报告问题根因分析）

> 结论先行：R5 暴露的"数据问题"与"内容问题"**不是 LLM 不听话，而是架构没有把数据当作约束、把财年当作一等公民、把审查当作带锚点的验证**。以下按"数据问题（R-D）"与"内容问题（R-C）"分列根因，每条给出证据位置（文件:行号）与修复方向。

---

## 一、数据问题根因（为什么 Wind 锚点没被守住）

### R-D1. 数据契约断裂：canonical 键 vs 检查器期望键不匹配 → 三层校验全部静默失效

**证据**：
- 生产侧键（`assemble_wind_data.py:41-52` FIELD_MAP 产出）：`营业收入`、`营业利润`、`归母净利润`、`净利润`、`总资产`、`归母净资产`、`年所有者权益合计`、`年负债合计`、`经营活动现金流量净额`
- 消费侧键（`quality/fact_checker.py:56-88`）：期望 `年营业收入`、`年净利润`、`年营业利润`、`年资产总计` → **在 wind_data 中永远取不到** → `_get_wind_value` 返回 None（`fact_checker.py:362-378`）→ 事实核查静默跳过
- `fact_extractor.py:443-459` `cross_validate_with_wind`：`income.get('年净利润')` / `income.get('年营业总收入')` → 同样 None → 提取结果与 Wind 的交叉验证**形同虚设**
- `data_repair.py:584-597` `_build_correct_values`：`['年净利润','净利润','归母净利润']` 部分匹配，但取 `vals[-1]` = FY2025（-7.76），而报告正文写 FY2024（+11.4）→ **修复基准本身就是错年**

**后果**：fact_extractor 交叉验证、data_repair 一致性审计、quality/fact_checker 事实核查三层校验全部失效，Wind 权威数字从未真正"卡"住报告。R5 的 83.6/80.0/81.2 三套 2024 收入、+11.4 vs -7.76 归母矛盾因此无人拦截。

**修复方向**：引入统一字段映射层（`quality/wind_field_mapper.py` 已存在但未被消费），所有检查器走同一 canonical 键；或在 `_collect_data` 后做一次 canonical 断言（缺失/类型错误即 fail-fast）。

### R-D2. 财年不是一等公民：事实提取器没有财年锚定机制

**证据**：
- `fact_extractor.py:122` `fiscal_year: int = 0` 默认值；`_merge_chunk_data`（763-826）**从不设置 fiscal_year** → 事实表输出 `FY0`
- `EXTRACTION_PROMPT`（468-525）只按字段提取，**不要求 LLM 标注"这是哪一年年报/哪个财年"** → LLM 把年报对比期数据（如"2024年"列）当当期
- `format_facts_as_context`（833-921）表头写 `FY{fy}` = `FY0`，但数据实际来自 FY2025 年报中的 FY2024 对比列 → 表格自称单财年，实际内容财年不明

**后果**：R5 事实表锚在 FY2024（83.6/16.2/11.4/18.5 亿），Wind 锚点 FY2025（-7.76 亿）→ 两套数字天然冲突且无仲裁。**根因是提取器从未被赋予"财年"概念**，下游"财年统一铁律"只是 prompt 文字。

**修复方向**：MinerU 解析时从年报元数据（报告期/封面页）提取 fiscal_year 与 report_type 传入 extract_facts；事实表每条记录强制携带 FY；无 FY 的数据拒绝进入表格。

### R-D3. 正负号/口径无程序化校验：正则不匹配负数

**证据**：
- `data_repair.py:273-290` CONSISTENCY_METRICS：`净利润[^\d]{0,10}(\d+\.?\d*)\s*亿` → **`\d` 不含负号** → `-7.76亿` 根本不被提取 → 负净利润一致性检查永远为空
- `quality/cross_chapter_consistency.py:49-72`：仅"经营现金流/净利润"的 pattern 带 `-?`，"总资产/营业收入/毛利率"无负号版本

**后果**：负数指标（亏损、净流出）跨章打架无法被程序发现（R1 的 +7.76 正负号丢失问题即源于此）。

**修复方向**：所有财务指标 pattern 统一 `(-?\d+\.?\d*)`；并在 `_build_correct_values` 中按 `_year_labels[-1]` 显式绑定财年。

### R-D4. 数据铁律只进 prompt，不进数据流

**证据**：
- `workflow.py:842-868` `data_anchor` 仅拼接成 prompt 文本（"禁止改动任何数字/单位/正负号"），生成后**无任何代码校验数字是否被改动**
- `workflow.py:846` `labels = (w._year_labels or {}).get("财年", [2023,2024,2025])` → 依赖 `_year_labels` 含"财年"键且硬编码 fallback；若 Wind 返回 2024/2025/2026 标签则错位

**后果**：LLM 在长文本中漂移数字没有任何兜底；`_year_labels` 硬编码 [2023,2024,2025] 一旦与真实数据错位，整个"最新财年"判定全错。

**修复方向**：报告生成后跑一次**程序化数字校验器**（正则提取全文财务数字 ↔ Wind 锚点 ± 容忍度，差异即 P0）；`_year_labels` 从 Wind 响应动态生成。

### R-D5. 估值/财务硬编码残留（快手模板）污染注入层

**证据**：
- `quality_enhancer.py:51-53`：`shares: float = 43.0`（快手总股本）、`current_price: float = 41.6`（快手股价）、`fiscal_year: int = 2025`（写死）
- `workflow.py:2546-2558` 调用 `enhance_report_quality(...)` **未传 current_price** → 默认 41.6 港元 → Stage 4 估值注入第7章（`quality_enhancer.py:233-240`）用错股价 → R5 ch7 "PE(TTM) 16.4/PB 1.20" 与 Wind 实际（PE -12.73/PB 1.086）不符
- `workflow.py:2574-2621` T9-T12：硬编码 `营收=80.07, 净利润=5.0, year=2024`、`price=41.6`、`base_revenue=80.07, net_debt=-127.81, shares=10.12`（快手数据）→ T9 还**重新赋值局部 `facts` 变量**（有覆盖 ctx.facts 的风险）
- `data_repair.py:230` `wrong_years=[2023,2024,2026]` 硬编码 + `:248` pattern2 硬编码"快手"字样

**后果**：质量增强层携带快手/示例数据，一旦启用即污染报告数字；`fix_source_annotations` 会把"来源：XX2023年/2024年/2026年"机械改写为 2025。

**修复方向**：所有默认参数改为 `None` + 调用处强制传值；删除 T9-T14 演示代码或改为从 ctx 取真实值；`fix_source_annotations` 改为白名单校验（只修"来源：财报原文摘要"→规范格式，不机械改年份）。

### R-D6. 行业判断硬编码"新能源汽车"

**证据**：
- `review_repair_loop.py:37` `industry: str = "新能源汽车"` 默认
- `workflow.py:2730-2736` 行业判定只覆盖 小鹏/蔚来/理想/腾讯/阿里/美团/京东 → 阅文落入默认"新能源汽车" → `assumption_checker` 以新能源行业假设审查网文公司

**后果**：审查视角错配（网文公司的合理毛利率/资本开支假设被新能源标准误判），修复 prompt 可能注入错误行业约束。

**修复方向**：industry 从 `facets`/Wind 行业字段推导，缺省时用中性"综合"视角而非默认行业。

---

## 二、内容问题根因（为什么模板泄漏/章节重号/口径混用发生）

### R-C1. 章节组装无结构校验：`_assemble_report` 只 strip 首行，不校验重复章节号/残留 H1

**证据**：
- `workflow.py:1791-1853` `_assemble_report`：对每章内容仅 `lstrip` + strip 首行 `# `，**内容中间嵌入的 `# 第5章...` 原样保留**
- ch4"七大变化"把 5 个变化写成 `# 第5章/第6章/第7章/第8章/第9章` 标题（R5 实锤）→ 与真实第5-9章重号

**后果**：R5 出现两组第5-9章标题，结构混乱。

**修复方向**：组装后跑结构校验器：H1 出现次数/唯一性断言、章节号连续性断言；内容内 H1 自动降级为 H2 或报错重写。

### R-C2. 模板泄漏无检测：quality 层无"内容归属/模板指纹"检查

**证据**：
- `auditor.py:41-60` 语义审计 6 维（契约覆盖30%/边界20%/视角15%/条件项15%/数据质量10%/逻辑10%）——**没有"内容是否属于本公司/本市场"检测**
- ch8"管理层、治理与激励"整章是组合构建模板（沪深300/夏普/组合配置）、ch9 整章是另一公司 DCF（80-95元/股/买入/WACC9.8% vs 实际 7.93%）——R5 实锤，审查循环全部放行

**后果**：跨公司模板整章混入，且与"中性"评级直接冲突的"买入"内容未被拦截。

**修复方向**：加模板指纹检测器（关键词黑名单：沪深300/组合构建/夏普/元/股/原材料/其他公司名；行业术语一致性检查）；审查 prompt 注入"禁止出现其他公司/其他市场内容"约束。

### R-C3. 审查修复循环不带数据锚点 → 修复即污染源

**证据**：
- `quality/review_repair_loop.py:248-263` `_repair_chapters` 修复 prompt：只有问题列表 + `当前内容 {content[:3000]}`，**不携带 wind_data/事实表/数据铁律**
- `quality/repairer.py`（repair_chapter）同样只传 issues+contract
- 语义审计的 `semantic_audit` 传入的是章节内容+契约，**无 Wind 锚点**（`workflow.py:1313-1315`）

**后果**：每次"修复"都是一次无锚点的重新生成 → R5 中 ch8/ch9 模板泄漏极可能正是审查修复循环引入/放大的。

**修复方向**：修复 prompt 强制注入 Wind 锚点表 + 事实表 + "只改问题所指，不得引入新内容/新数字"约束；修复后必须重跑数字校验器（R-D4）。

### R-C4. 事实表（FY0/FY2024）与数据铁律（FY2025）矛盾，无仲裁

**证据**：
- `workflow.py:778-784`：有 `ctx.facts` 时注入 `format_facts_as_context`（自称单财年、实际 FY2024 数据）
- `workflow.py:892-894`：同时注入"数据铁律：以最新财年（上表最后一个财年）为当期基准"
- **两者没有在进入 LLM 前做一致性仲裁** → LLM 收到两个互相矛盾的"权威"，各章自选 → 83.6/80.0/81.2 三套数字并存（R5 实锤）

**后果**：同一指标多套数字、财年锚定错位（评级用 FY2025，正文用 FY2024）。

**修复方向**：**在 `_collect_data` 之后做"事实表 ↔ Wind 锚点"对齐仲裁**：财务字段以 Wind 为准覆盖事实表对应字段（或标注"仅供参考，以 Wind 为准"并强制单财年）；两者财年不一致时显式标注"事实表为 FY2024 年报原文、Wind 为 FY2025"。

### R-C5. 断点恢复绕过数据修复与锚点更新

**证据**：
- `workflow.py:1167-1182` `_write_chapters`：`checkpoint.is_chapter_completed` 命中 → 直接复用缓存，**跳过 `_build_chapter_prompt`（含数据铁律与当前事实表）**
- `workflow.py:1288-1293` `_audit_and_fix`：`is_chapter_audited` 命中 → 跳过语义审计

**后果**：跨轮次修复（如数据铁律升级、Wind 数据更新）后，旧章节缓存仍被直接复用 → 新旧口径混在同一报告。

**修复方向**：checkpoint 缓存带"prompt 指纹/数据版本"；数据源或 prompt 模板变化时使缓存失效。

### R-C6. 质量增强 Stage 4/5 直接拼接估值文本，币种/股价无校验

**证据**：
- `quality_enhancer.py:233-240`：`chapters[7] = chapters[7] + val_text`（DCF每股价值 X 元、目标价区间）→ 用默认 current_price=41.6 算 upside
- 港股公司估值文本用"元"计价、无"港元"单位校验（`workflow.py:2849-2856` 只检测"港元+人民币混用"，不检测"元"单用）

**后果**：R5 ch7 估值数字与 Wind 实际不符，币种表述不规范。

**修复方向**：current_price/shares/fiscal_year 全部从调用处强传（无默认值）；估值注入文本按 market 生成（hk→港元）；单位断言（出现"元/股"且 market=hk → P0）。

---

## 三、汇总：一条主线

> **所有问题都可归结为：数据（Wind/财报）在进入 LLM 之前没有被规范化为"带财年、带口径、带正负号、canonical 键、单源"的强约束对象；生成之后没有程序化校验器兜底；审查修复没有锚点注入。** 架构把信任全部押在 prompt 文字纪律上，而 LLM 的长文本漂移与模板复用是统计必然——**必须把校验从 prompt 移到代码**。

### 修复优先级（R6）
1. **R-D1**：canonical 键统一 + 检查器走映射层（挡 83.6/80.0/81.2 三套数字）
2. **R-D2 + R-C4**：事实提取锚定财年 + 事实表↔Wind 仲裁（挡 FY2024/FY2025 混用）
3. **R-D4**：报告后程序化数字校验器（挡正负号/数字漂移）
4. **R-C2 + R-C3**：模板指纹检测 + 修复 prompt 注入锚点（挡 ch8/ch9 模板泄漏）
5. **R-C1**：组装结构校验（挡章节重号）
6. **R-D5/R-D6**：删除快手硬编码、行业从数据推导（挡污染源）

---

## 四、V8 引擎（qual_v8 Gate0-8）扫描结论（2026-08-18 新增）

> **结论先行：v8 引擎是"设计文档级的脚手架"，不是可运行的引擎。** 它承载了正确的架构意图（Gate 门禁、数据锚点、熔断、监督、人工确认），但 9 个 Gate 的实质检查逻辑几乎全部是占位符；且它继承了 v2-v7 同款键契约断裂、无财年维度问题，并新增 DataAnchor 死代码。**R5 实际跑的从来不是 v8 引擎**——`workflow.py:2256-2267` 只是以 shadow 模式"非侵入式挂载"（只记录不阻断），Gate0-8 状态机从未真正执行。

### V8-1. 引擎级：Gate 执行是"空转"，pass_criteria 从未真正校验
- `workflow.py:130-190`：顺序执行 Gate0-8，`gate_engine.execute_gate` 只调用 `gate.execute()`，**从不调用 `check_criteria()`**；重试逻辑是 `gate.increment_retry(); pass`（空操作）
- `_get_flow_definition`（`workflow.py:60-89`）**只定义了 gate_0 和 gate_1**，其余是 `# ... 其他Gate定义` 注释 → `supervisor.check_gate` 对 gate_2+ 返回"Gate 未在流程定义中找到"
- **后果**：即使 Gate 内部逻辑补全，状态机/监督层也不会真正拦阻断流程（shadow 模式默认不阻断）

### V8-2. 逐 Gate：实质检查全是"这里应该实现实际的 XXX 逻辑"占位
| Gate | 声明能力 | 实际实现 |
|---|---|---|
| 0 数据源验证 | 财报存在/Wind 覆盖率/必填字段/数值类型/3年范围 | `_fetch_filing`/`_fetch_wind_data` 返回模拟 success；`_check_data_range` 直接 return True（`gate0.py:153-154, 204`） |
| 1 类型推断+提取 | 市场推断/必填字段/数值偏差 | `_extract_facts` 返回**硬编码模拟数据**（revenue=100.0, net_income=10.0…，`gate1.py:126-136`） |
| 2 数据收集+DCF | FCF/WACC/永续/增长/税率范围 | 用**英文键**取数（operating_cash_flow/capex/total_assets/total_debt，`gate2.py:112-124`）→ canonical 键不匹配 → 取不到 → FCF=0、WACC 计算失真 |
| 3 逐章写作 | 大纲→分章→交叉验证→组装 | `_generate_chapters` 返回 `"第{i}章内容"*100`（`gate3.py:131-135`）；一致性检查空实现 |
| 4 审计修复+深审 | 格式/来源/日期/币种/估值/矛盾/风险 | **全部注释**"这里应该实现实际的…"（`gate4.py:161-240`），contradictions 恒为空列表 |
| 5 质量增强+估值 | DCF 估值/组件集成/交叉验证 | 估值依赖 Gate2 的错键 dcf_params；`_integrate_components` 直接全部 append（`gate5.py:166-183`）；交叉验证 pass |
| 6 结论+决策+概览 | 评级有效/评级与估值一致 | 评级提取有正则实现，但依赖 context 预填章节 |
| 7 问题转化+记忆 | 记忆存储 | `gate7.py:169` "这里应该实现实际的记忆存储逻辑" |
| 8 最终验证 | Critical/人工确认/格式/大小 | Critical/人工/格式全占位（`gate8.py:133-178`）；仅报告大小检查真实（50-500KB，R5 的 112.5KB 恰好通过） |

### V8-3. DataAnchor（v8 声称的"唯一数据源"机制）三大缺陷
- **死代码**：`data_anchor.py:101-123` `_extract_data` 匹配了数字却**从不写入 data 字典**（`value = float(match)*multiplier` 后无任何赋值）→ `validate_chapter`/`fix_chapter` 永远返回空 → **跨章数据校验形同虚设**
- **键契约断裂（同 R-D1）**：`init_from_wind_data`（`data_anchor.py:125-171`）期望 `年营业收入`/`年净利润`/`年资产总计`/`年归属母公司股东权益` → 与 canonical 键（`营业收入`/`归母净利润`/`总资产`/`年所有者权益合计`）不匹配 → 锚点根本设置不进去
- **无财年维度**：DataPoint 只有 value/unit/source/timestamp，**没有 fiscal_year** → 无法表达"FY2024 vs FY2025"，R-D2 财年问题在 v8 同样无解

### V8-4. 与 v2-v7 的关系：双轨并存，但都未真正实现数据约束
- **v2-v7 单体**（R5 实际路径）：有真实生成能力（fact_extractor/quality 链/repair），但无程序化校验（R-D1~R-D6 全中）
- **v8 引擎**：有校验意图（Gate/DataAnchor/CrossChapterValidator），但无实现（全占位）
- **结论**：R5 的问题不是"v8 没拦住"，而是 **v8 根本不可用 + v2-v7 没有校验**——两条路都通向同一根因：**数据契约、财年、校验从未在代码层落地**。

### V8 修复方向（若要把 v8 变为可用引擎）
1. 逐 Gate 用 v2-v7 已修好的真实组件填充（fact_extractor→Gate1、DCF→Gate2、quality 链→Gate4/5），删除全部"这里应该实现"占位
2. `_get_flow_definition` 补全 gate_2~8 定义；`execute` 调用 `check_criteria` 并在 enforce 模式下阻断
3. DataAnchor：修 `_extract_data`（写入 data）、键走 canonical 映射层、DataPoint 加 fiscal_year
4. 模式升级：`QUAL_MODE` 从 shadow → soft → enforce 渐进验证后再默认启用

### ✅ V8 可运行化完成状态（2026-08-18，方案见 `docs/qual-v8-activation-plan.md`）

**已完成改造**（全部编译通过 + 快速验证跑通 + v2-v7 回归正常）：
| 项 | 改造 |
|---|---|
| 引擎机制 | `workflow.py`：补全 gate_0~8 flow_definition；execute 真实重试（重执行 + 注入上次 errors）；每 Gate 调 `check_criteria`；enforce 模式关键 Gate（0/2/4/8）失败即阻断；Gate 结果写回 context 供后续 Gate 消费 |
| DataAnchor | `data_anchor.py`：修 `_extract_data` 死代码（真实提取指标+数字+单位）；canonical 键别名表（`年营业收入→营业收入` 等）；DataPoint 加 fiscal_year；多财年锚点（set_anchor 按财年覆盖/追加）；`validate_chapter`/`fix_chapter` 财年感知 |
| 适配层 | 新增 `adapters.py`：`build_data_context`（复用 workflow._collect_data）、`wind_coverage`/`has_3y_range`/`get_latest_wind_value`（canonical 键）、`industry_for`（替代硬编码"新能源汽车"）、`extract_rating_from_chapters` |
| Gate0 | 真实数据源验证：filing.sections 非空 + Wind canonical 键覆盖率≥95% + 3年范围 + 数值类型 |
| Gate1 | `infer_market` + `fact_extractor.extract_facts`（真实 LLM 提取）+ Wind canonical 偏差校验；无 LLM quick 模式 SKIPPED 不阻断 |
| Gate2 | `workflow.extract_dcf_params`（真实 DCF：OCF-Capex/CAPM/3年CAGR）+ DataAnchor 初始化 + 参数范围校验（FCF 负值放行：亏损是真实状态） |
| Gate3 | `workflow._build_chapter_prompt`+`_generate_chapter` 真实 11 章生成；跨章一致性（quality.cross_chapter_consistency）→ 转 warning 交 Gate8 收口 |
| Gate4 | 形式审查（占位符/币种/模板指纹/来源→warning）+ `review_and_repair_loop` 实质审查修复循环（锚点注入）+ `logic_consistency_check` 矛盾检测 + 风险覆盖检查 |
| Gate5 | `enhance_report_quality`（**参数强传消除快手硬编码**）+ `compute_base_valuation` + DataAnchor 准备（全文数字校验移交 Gate8） |
| Gate6 | 决策/概览章真实 LLM 生成 + 评级提取 + 评级-估值一致性 |
| Gate7 | `workflow._store_memory` 真实记忆 + ReviewIssue 结构化 |
| Gate8 | 全文数字校验器（报告数字 vs Wind 锚点，1% 容忍）+ 模板指纹 + 章节重号检测 + Gate4 形式问题收口 + 报告格式/大小 |
| 验证脚本 | `run_qual_v8.py --quick`：R5 报告预填 → Gate0-7 全 PASS，Gate8 **正确拒绝 R5 并定位 25 处数字错误**（现金流 18.5 vs -2.77、归母 11.4 vs -7.76、营收 80.0 vs 73.66 等） |

**验证证据（quick 模式，真实 wind_data.json + R5 章节）**：
```
Gate0: PASS cc=True | Gate1: PASS cc=True | Gate2: PASS cc=True | Gate3: PASS cc=True
Gate4: PASS cc=True | Gate5: PASS cc=True | Gate6: PASS cc=True | Gate7: PASS cc=True
Gate8: FAIL score=80 cc=True → 25 Critical：数字不一致（现金流/归母/营收 vs FY2025 锚点）——R5 财年混用机器级复现
```
- 负样本（R5 报告）→ Gate8 拒绝 ✅；正样本（与锚点一致的干净章节）→ 检查链通过 ✅（除风险覆盖 8 类的合理门禁）
- **验证链语义**：数据门禁(Gate0-2) → 生成(Gate3) → 审查修复(Gate4-5) → 决策(Gate6) → 转化(Gate7) → 最终验证(Gate8) 正确收口

### ✅ 红队审查层接入 Gate8（2026-08-18，buy_side_report_review skill 代码化）

**背景核实**：`skills/finance/buy_side_report_review/SKILL.md`（v2.0，红队审查工作流：六大 Phase + Phase 5.5 自纠闭环）
与 `tools/finance/quality/review_integrator.py`（633 行代码化实现）**此前从未被任何运行链路调用**（孤儿组件）——
R5 带着 25 处数据错误出厂的原因之一。

**本次改造**：
1. **修硬编码锚点**：`_build_review_prompt`/`_build_fix_prompt` 原硬编码**美团数据**（2767/3376/3649亿HKD、-234亿HKD、90.30HKD），
   `wind_data` 参数从未使用 → 新增 `_build_wind_anchor_table()` 动态生成 canonical 锚点表（阅文：营收70.12/81.21/73.66、归母8.05/-2.09/-7.76、现金流11.31/25.27/-2.77）
2. **新增 `review_report_text()`**：文本版审查入口（不依赖文件路径），供 v8 Gate8 直接调用
3. **修解析器 `_parse_review_result`**：原只匹配 `【致命】` 格式；LLM 实际输出 `F-1/I-1` 编号+表格 → 新增三方式兼容解析（实测 fatal=5、important=16 正确解析）
4. **harness_llm 支持 `max_tokens`/`system` 覆盖**：红队审查需 24000 tokens + 审查专用 system（原 12000 + 报告撰写格式会截断/约束）
5. **Gate8 新增 `_run_redteam_review()`**：有 llm_caller 时执行红队审查（专用 caller），【致命】→ Gate8 FAIL，【重要/建议】→ warning；无 LLM 时跳过（确定性校验已覆盖）

**实测**（宿主桥接 LLM 审 R5 报告前 12000 字符）：
- 红队审查产出 5 致命 + 16 重要：F-1 年份/数值系统性错乱（2024盈利 vs 2025亏损）、F-2 2023营收80亿 vs Wind 70.12亿（偏差14.1%）且与第3章矛盾、F-3 现金流错位（15.2亿 OCF/FCF 串位）、F-4 少数股东损益4.8亿不兼容、F-5 报告截断不完整；I-1~I-16 市占率矛盾/IFRS-NonIFRS混用/ARPPU不自洽/无目标价/ROIC vs WACC缺失/元裁决规则缺失等
- 审查报告落盘：`.pip-tmp/reviews/r5_redteam_test_review.md`

**遗留/边界**：
- Gate8 红队审查仅在**完整模式（--full，有 llm_caller + report 完整）**触发；quick 模式自动跳过
- 报告 >12000 字符会被截断（红队审查只见前段）——完整模式建议按章节分批或全量传入（24000 tokens 上限内）
- 审查只读不修：修复由 Gate4 审查修复循环 / 外部 ReviewIntegrator.fix_report 循环承担

**遗留/边界**：
- Gate3/4/5/6 的真实 LLM 路径（--full 模式）未在本轮验证（需 llm-bridge + 真实财报 + 30-90min）；quick 模式已覆盖检查链
- Gate7 记忆存储需 data_ctx（完整模式下由 build_data_context 提供）
- enforce 模式阻断已实现（workflow.py），未在 quick 验证中触发（shadow 模式）
- 正样本风险覆盖 8 类是合理门禁，报告须含市场/经营/财务/行业/估值/数据/流动性/汇率风险披露
