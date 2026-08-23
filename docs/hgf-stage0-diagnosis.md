# HGF 阶段 0: 快速诊断报告（2026-08-22）

## P5 跨章一致性 28-77 issues 诊断

### 根因分析
CrossChapterConsistencyChecker 的 issue 来源有 3 类：
1. **财务数据冲突** (_check_financial_consistency)：同指标同财年跨章比较，1%容差外标 conflict
   - 真冲突：LLM 在不同章节写了同一财年同一指标的不同值（幻觉/四舍五入/口径混用）
   - 假冲突：regex 提取精度问题（如"营收767.20亿" vs "营收约767亿" → 767.20 vs 767.0 差0.026%，<1%容差→跳过）；但如果 LLM 写"767亿"（整数）vs "767.20亿"（两位小数），767.0 vs 767.20 = 0.026%，<1% → 跳过
   - **最可能的真冲突**：LLM 在不同章节对同一指标引用了不同财年值（如 ch5 引 FY2025 营收 767.20，ch4 引 FY2024 营收 408.66），但 checker 已做多财年感知（_extract_financial_data 按财年分组），**同财年比较**不会误报

2. **结论冲突** (_check_conclusion_consistency)：同主题同财年结论正负冲突
   - 如"现金流首次转正" vs "现金流持续为负" → fatal
   - 三财年报告中不同章节对同一财年的结论可能矛盾

3. **时间冲突** (_check_time_consistency)：时间点不一致

### 诊断结论
- 28→77 的增长来自**审查修复循环中 LLM patch 引入新问题**
- 真冲突占比需要拿到具体 issue 列表才能确定
- **初步判断**：多数可能是**结论冲突**（LLM 对同一财年在不同章节给出矛盾结论），而非数据冲突（数据冲突的 checker 已做多财年感知 + 1% 容差）

### 建议
1. 先跑一次完整报告，收集完整 issue 列表按类型分类
2. 如果主要是结论冲突：需要程序化跨章结论同步（或放宽结论冲突的严重性）

---

## P6 事实核查 score=0, 19 issues 诊断

### 根因分析
**关键发现**：conclusion_validator._check_by_llm (line 401) 的 LLM 审查响应解析极其粗糙：

```python
if "矛盾" in response or "不一致" in response or "问题" in response:
    issues.append(ConclusionIssue(severity="important", ...))
```

1. **"问题"是高频中文词**：prompt 里就有"如果存在问题，请指出具体问题"——LLM 响应几乎必然包含"问题"二字 → 每次 LLM 调用都产出 1 个 important issue
2. **score=0 = 全部 19 个 issue 都是 important**：100 - 19×15 = -185 → max(0, -185) = 0
3. **循环放大**：审查修复循环每轮调用 _check_by_llm → 每次产出 ≥1 个 important → 累积 19 个

### 诊断结论
**P6 的根因是标准过粗糙 + 循环放大，不是真正的事实错误。**  LLM 审查的响应解析（关键词匹配→issue）质量极差，"问题"这种通用词不应该触发 issue。

### 建议
1. **短期**：_check_by_llm 的响应解析改为**结构化输出**（要求 LLM 返回 JSON 格式的 issue 列表）
2. **中期**：降级 LLM 审查为 warning 级（不影响 pass/fail），或单独评分
3. **长期**：事实核查与 DataAnchor 锚点做程序化比对（而非依赖 LLM 审查）

---

## P12 Gate3 gate_issues=1 诊断

### 根因分析
numeric_guard.FINANCIAL_CHAPTERS = {5, 6}，check_shell 要求这两章有 ≥3 个小数数字。

第5章"经营表现与核心驱动"：
- 内容以运营数据为主（交付量、门店数、用户数等），这些数据通常是**整数**（如"交付37万辆"）
- 财务数字是辅助引用（营收/利润占位符回填后会有小数）
- PGNB v4 修复后，bind_bare_numbers 替换 + bind_placeholders 回填会注入小数数字（如 FY2025 767.20）
- 但**第5章 LLM 重试后**可能仍不满足 ≥3 个小数数字的要求

第6章"财务质量与资本配置"：
- 纯财务章节，应该有充足的小数数字
- 但如果 LLM 重试后内容被精简，小数数字可能不足

### 诊断结论
**FINANCIAL_CHAPTERS = {5, 6} 把运营章节（ch5）和纯财务章节（ch6）用同一 ≥3 小数标准是过度严格**。第5章是"经营表现与核心驱动"，大量运营数据是整数（交付量/门店数），不应要求 ≥3 个小数数字。

### 建议
1. **FINANCIAL_CHAPTERS 改为 {6}**：只有纯财务章节才要求 ≥3 个小数数字
2. 或者为第5章设置更低的阈值（MIN_CH5_NUMBERS = 1）

---

## P4 日期锚点循环诊断

### 根因分析
FiscalSemantics 日期锚点检查 + 单调性守卫的组合导致死循环：
1. LLM 生成/修复时不可避免使用"当前/目前/近期"等模糊时间词
2. 日期锚点检查期望 "FY2025 业绩" 而非 "当前业绩"
3. 修复 patch 引入 "当前" → 日期检查失败 → 单调性守卫回滚

### 诊断结论
这是**文本规范化问题**，不是数据问题。需要类似 bind_bare_numbers 的程序化替换（bind_fuzzy_dates），但必须上下文感知（"当前宏观环境"不能改）。

### 建议
见 heavyskill 审查结论方案 A（上下文感知的日期规范化）

---

## P7 Gate1 FY2023 NoneType 诊断

### 根因分析
fact_extractor 在 FY2023 sections 调用时，_parse_chunk_response 或 normalize_values 内部某处 `.get()` 在 None 上调用。

最可能位置：_merge_chunk_data (line 860) 或 resolve_financial_from_wind 对 FY2023 wind_data 取值。

### 建议
1. 添加 traceback 到 gate1.py:248 的 except 块（当前只打 {e}，缺堆栈）
2. 防御性 get：在 fact_extractor 关键路径增加 None 检查

---

## 总结：优先级与实施顺序

| 阶段 | 问题 | 方案 | 复杂度 |
|------|------|------|--------|
| **阶段 1** | P6 | 修复 _check_by_llm 响应解析（关键词→结构化） | 低 |
| **阶段 1** | P12 | FINANCIAL_CHAPTERS 从 {5,6} 改为 {6} | 低 |
| **阶段 1** | 收敛 | 方案 C：max_repair_rounds=3 + Gate8 终局兜底 | 中 |
| **阶段 2** | P4 | 方案 A：bind_fuzzy_dates 上下文感知 | 中 |
| **阶段 3** | P5 | 方案 D：跨章一致性先检测后高置信替换 | 高 |
| **阶段 0+** | P7 | 添加 traceback + 防御性 get | 低 |
