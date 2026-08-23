# P5/P6/P12 代码级诊断报告（2026-08-22）

## 问题1: P5 跨章一致性 28-77 issues

### 代码位置
`tools/finance/quality/cross_chapter_consistency.py`

### 诊断：最大的 issue 来源 = **数据冲突（data_conflict）**，且大部分是**假冲突**

**根因分析：**

1. **`_extract_financial_data` 的多财年提取存在"同章多值"缺陷**（line 145-209）
   - 三财年报告中，同章会合法引用 FY2023/2024/2025 三个值
   - `data[indicator]` 收集了**该章所有财年的所有值** `[(fy, value), ...]`
   - 但 `_check_financial_consistency`（line 227-282）对同一 indicator 的**所有 (fy, value) 点**做两两比较，**不要求每章只取一个值**

2. **`by_fy` 桶内"一章多值覆盖"缺陷**（line 232-237）
   ```python
   for ch_num, data in chapter_data.items():
       points = data.get(indicator) or []
       for fy, value in points:
           bucket = fy if fy is not None else _latest
           by_fy.setdefault(bucket, {})[ch_num] = value  # ← 后值覆盖前值
   ```
   - 若一章内 FY2025 出现两次（767.20 和另一个值），**后者覆盖前者**
   - 若一章同时引用 FY2024（408.66）和 FY2025（767.20），两个值落入不同 bucket，**不会冲突**——这没问题
   - 但若 `fy=None`（无法归因）的引用被归到 `_latest` bucket，与 FY2025 显式引用**同桶比较**，若两处引用不同值（如一处 767.20、一处 PGNB 回填前的 767 或四舍五入）→ 假冲突

3. **核心假冲突场景（实测）**：
   - **场景A（四舍五入）**：767.20 vs 767 → 1% 容差内**已豁免**（line 253），不是问题
   - **场景B（FY 归因失败）**：某章"营业收入 408.66 亿"（FY2024）但 FY 标注被 regex 漏掉 → 归因到 FY2025 bucket → 与另一章"营业收入 767.20 亿"比较 → **假冲突**（跨财年误比）
   - **场景C（regex 误提取）**：`r"营业收入.*?(\d+\.?\d*)\s*亿"` 中 `.*?` 跨过长文本，可能把"营业收入增长至 408.66 亿（2024年），2025年达 767.20 亿"整个截取，`(\d+)` 捕获 408.66 但 FY 归因基于**数字位置**（m.start() 在 408.66 处），`_year_before` 找到 2024 → 正确。但若写成"FY2025 营业收入 767.20 亿，较上年 408.66 亿"→ 两值都在，第二个 408.66 归因到 2024（数字前 150 字符有 2025）→ 其实 408.66 前的 150 字符是"较上年"→ 无年份 → `_attributed_fy` 归因到 FY2024 → 正确

4. **结论冲突（conclusion_conflict）**: `_extract_conclusions` 用 `_year_before_conclusion`（150 字符内找年份），无年份则 None。`_check_conclusion_consistency` 按 fy 分组，None 组内比较。**"现金流首次转正"（FY2025）vs "现金流持续为负"（FY2024）**若都在 None 组 → 假冲突 fatal。但这是"三财年合法叙事"，`_extract_conclusions` 未做财年区分（只取最近 150 字符年份）→ **FY2024 的"为负"可能被误归到 FY2025 组** → 与"转正"冲突

5. **时间冲突（time_conflict）**: `_extract_data_for_time` 用 `time_pattern + .{0,80}? + pattern`，跨 80 字符匹配可能错位

### 28 vs 77 的差异来源
- 28 = 首次检查（部分章节 PGNB 已回填锚点值，一致）
- 77 = 修复循环后（LLM patch 引入了新数字/新表述，增加了不一致）
- 单调性守卫只拦"引入新问题签名"，**没拦"同指标数值漂移"**

### 结论
- **最大来源：data_conflict（财务数据冲突）**，其中**跨财年误比（场景B）是最大假冲突源**
- 次要：conclusion_conflict 的财年归因错误（"转正 vs 为负"跨年误比）
- 真冲突（同财年同指标不同值）存在但占比低——需要 sample 确认

---

## 问题2: P6 事实核查 score=0, 19 issues

### 代码位置
`tools/finance/quality/fact_checker.py`（注意：**不是 conclusion_validator.py**——那是"结论合理性审查"，review_repair_loop.py:501 调用的 `check_facts` 才是"事实核查"）

### 事实核查器检查什么
1. **直接引用数据**（`_check_direct_data`）: 营业收入/净利润/营业利润/总资产/经营现金流 5 个指标，regex 提取报告值 vs Wind 最新值，5-10% 容差
2. **计算结果**（`_check_calculated_data`）: 毛利率/营收增长率/净利润增长率，report 值 vs Wind 计算值，2-5% 容差
3. **同比变化**（`_check_yoy_changes`）: 所有"同比增长 X%" vs Wind 计算营收增长率，10% 容差

### score=0 意味着什么
`score = 100 - fatal×40 - important×15 - suggestion×5`，clamp 到 [0,100]。
**score=0 需要 ≥7 个 important 或 ≥1 fatal+4 important 或 ≥3 fatal。**
19 issues 中大部分是 important（偏差>20%）或 fatal（偏差>50%）。

### 19 issues 最可能的分类（按概率排序）

1. **【最大头】多财年误比（估计 10-14 个）—— 系统性假阳性**
   - `_extract_value` 取 **`matches[0]`（章内第一个匹配）**（line 357）
   - `_get_wind_value` 取 **Wind 列表最后一个（= FY2025）**（line 376）
   - 三财年报告中，章节可能先提 FY2023（306.76）或 FY2024（408.66）再提 FY2025
   - 例：第6章"FY2023 营收 306.76 亿 → FY2025 767.20 亿" → `matches[0]` = 306.76 → 与 Wind FY2025 767.20 比 → 偏差 60% → **fatal 假阳性**
   - 这是 19 issues 的最大贡献者（5 个指标 × 11 章，只要章内先出现历史年值就会触发）

2. **【次大头】毛利率/增长率计算字段缺失（估计 2-4 个）**
   - `_check_calculated_data` 的 `_get_wind_value(wind_data, "年营业成本")` —— Wind 数据里**没有"年营业成本"**（xpev-wind.json income 只有 归母净利润/营业收入/营业利润）
   - `_get_wind_value(wind_data, "年营业收入")` —— canonical 别名可能找不到（实际键是"营业收入"）
   - 找不到 → `actual_value = None` → `return None`（**不报 issue**，这是静默跳过）
   - 所以毛利率实际不产生 issue，但 **营收增长率/净利润增长率** 若 report 有值而 Wind 计算失败 → 也不报（None 跳过）

3. **【真实问题】同比数据不匹配（估计 3-5 个）**
   - `_check_yoy_changes` 对所有 "同比增长 X%" 都按**营收增长率**比对（line 326-328 硬编码营收）
   - 若报告写"净利润同比增长 45%"或"交付量同比增长 82%"，会被错误地与营收增长率 87.73% 比 → 假阳性 important
   - 小鹏 2025 营收同比 = (767.20-408.66)/408.66 = 87.73%，报告若写"同比增长 87.7%"则通过；若写净利润同比（-11.39 vs -57.90 = -80%）→ 偏差 >10% → important

4. **【可能】报告引用 FY2025 但值经 PGNB 回填**：PGNB 回填后值=锚点值，**不会误报**（一致）

### 结论
- **score=0 的核心：`matches[0]` + Wind 最新值 = 多财年误比**，产生大量 fatal/important 假阳性
- 19 issues 中 **绝大多数（估计 13-16 个）是假阳性**，真问题（如净利同比被当营收同比）约 3-5 个
- 事实核查器**没有财年感知**——这是与 DataAnchor/跨章检查器的根本差距

---

## 问题3: P12 Gate3 gate_issues=1

### 代码位置
`tools/finance/quality/numeric_guard.py`

### gate_issues=1 最可能是哪个闸门？

`check_chapter_gates` 依次跑 5 道闸门：
1. `check_numeric`（量级校验）: 数字与锚点 >10 倍 → 违规
2. `check_empty`（空章）: 去空白 <800 字符 → 违规
3. `check_shell`（空壳）: **仅 FINANCIAL_CHAPTERS={5,6}**，长度达标但小数数字 <3 → 违规
4. `check_fiscal`（财年）: ch5 严格（须锚 FY2025）、ch6 宽松豁免、ch7 严格
5. `check_currency`（币值）: 仅 ch7

**第5章 gate_issues=1 最可能是 `check_fiscal`（财年一致性）**，理由：
- 第5章在 `FISCAL_STRICT_CHAPTERS = {5, 7}`，须锚定 FY2025 当期
- PGNB v4 已消除空壳章（小数数字 ≥3），所以 `check_shell` 不再是主因
- 但 PGNB 回填后内容含 "FY2025 -44.16" 等，FY2025 引用应该存在……
- **更可能：`check_fiscal` 检测到"历史财年引用未带豁免语境"**——第5章是"经营表现与核心驱动"，天然会大量引用 FY2024/FY2023 对比数据（"较 FY2024 增长""FY2023 营收 306.76 亿"），若某处历史引用附近 80 字符内无 `FISCAL_HISTORICAL_CONTEXT` 词（对比/趋势/同比等）→ 违规
- 但 PGNB 回填后是 "FY2025 -44.16"，如果原文写 "较上年 FY2024 的 -74.82" → "上年"在豁免词表 → 通过
- **另一种可能：`check_numeric`**——PGNB 回填的占位符值（如 767.20）若匹配锚点则通过；但若章节中有**运营数据**（交付量 38.9 万辆、门店 700 家）与财务锚点量级不同 → `_extract_amounts` 提取"38.9万"→ 0.00389 亿 → <0.1 跳过；"700家"→ 单位后是"家"→ 跳过。所以 numeric 概率低

**结论：gate_issues=1 最可能是 `check_fiscal`（ch5 财年错位），次可能是 `check_shell` 残留（若 PGNB 回填前小数不足）。** 需要看具体 payload 确认。

### FINANCIAL_CHAPTERS 包含第5章是否合理？

**不合理。** 理由：
- 第5章"经营表现与核心驱动"是**运营为主、财务为辅**——核心是交付量/门店/毛利率/客户增长
- 第6章"财务质量与资本配置"是**纯财务**——核心是资产负债/现金流/资本回报
- 两者用同一 `MIN_FINANCIAL_NUMBERS=3` 标准不合理：
  - 第5章若运营数据丰富但财务数字仅 1-2 个（PGNB 回填前），会被误判空壳
  - 但 PGNB v4 后财务数字必被回填（占位符→锚点值），`check_shell` 反而不该再触发
- **更重要的偏差**：`check_fiscal` 对 ch5 严格（须锚 FY2025）是对的（经营表现应聚焦当期），但对 ch6 宽松豁免历史引用——**这反了**！第6章财务分析更应锚定当期 FY2025，历史引用才应严格标注

### 调整建议
1. **FINANCIAL_CHAPTERS 保留 {5,6}** 但调整 `MIN_FINANCIAL_NUMBERS`：ch5 降至 1（运营章有财务数字即可），ch6 保持 3
2. **FISCAL_STRICT_CHAPTERS 应包含 6**（财务章更应锚当期），`FISCAL_LENIENT_CHAPTERS` 只保留 {4}
3. **给 ch5 增加运营数据闸门**：核心是交付量/门店数等运营指标的存在性，而非纯财务小数计数
4. **gate_issues=1 的具体 payload 应记录**：日志只显示 count，不显示哪个闸门——应增强日志

---

## 关联: P4 日期锚点循环（date_anchor_check.py）

虽然用户只问了 P5/P6/P12，但 P4 与三者强关联，补充诊断：
- `_check_ambiguous_dates`（line 242-277）把"当前/最新/近期/目前"**所有无具体日期的出现**都报为 suggestion
- 每个 chapter 可能报 2-5 个 → 11 章 = 22-55 个 suggestion
- 35 issues 中大部分是 **suggestion 级模糊时间词**（每个 -5 分，7 个就 score=0）
- **根因**：`ambiguous_patterns` 是**纯词匹配**，没有财务语境判断——"当前宏观环境""目前行业竞争"这些非财务语境也被报
- **修复方向**（与 heavyskill 方案 A 一致）：上下文感知——仅财务业绩语境（有指标/FY/同比）才替换，非财务语境豁免

---

## 总结表

| 问题 | 根因 | 最大贡献 | 严重性 | 修复方向 |
|------|------|---------|--------|---------|
| P5 | `by_fy` 桶内覆盖 + FY 归因失败跨年误比 + 结论跨年误比 | data_conflict 假冲突（跨财年误比） | P0 | 多财年感知：每章每指标每财年取**最新一个**值再比较；结论按 FY 严格分组 |
| P6 | `matches[0]` + Wind 最新值 = 无财年感知 | 多财年误比（历史年值 vs FY2025） | P0 | 事实核查器接入 DataAnchor 财年归因；同比按指标分类（营收/净利/运营分离） |
| P12 | ch5/ch6 同标准 + ch5 运营章被当财务章 | check_fiscal（ch5 财年错位） | P1 | FINANCIAL_CHAPTERS 分级阈值；FISCAL_STRICT 含 ch6；ch5 加运营闸门 |
| P4 | 纯词匹配无财务语境 | "当前/目前"非财务语境误报 | P1 | 上下文感知日期替换（heavyskill 方案 A） |
