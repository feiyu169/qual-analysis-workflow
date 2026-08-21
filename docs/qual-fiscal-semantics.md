# FiscalSemantics——财年语义单源化（架构级长效方案，2026-08-21）

## 问题（Gate4 失败根因，跨章历史引用误报）

小鹏运行 Gate4 失败：`总资产(最新财年) 第3章=1031.63亿 vs 第6章=841.63亿`。

**本质**：ch6 写"总资产841.63亿"（FY2023 历史值）但未标注财年 → 跨章检查器把
**未标注引用一律视为"最新财年"** → 841.63 与 1031.63（FY2025）同桶 → 误判矛盾。

**深层架构缺陷**（非单点 bug）：
1. **财年语义分散三层**：写作 prompt（LLM 自觉）→ check_fiscal（文本模式）→ 跨章检查器（_year_before 启发式）——无单源
2. **检查器无归因能力**：未标注数字引用无法知道它属于哪个财年
3. **写作端无程序化财年校验**：LLM 写错历史引用到 Gate4 才被发现（晚、成本高）

## 方案：三层防线 + 单源归因（FiscalSemantics）

### 单源：DataAnchor 归因服务（`attribute_value` / `attribute_text_value`）
- 锚点（canonical 键 × 多财年值）是**数值→财年的权威映射**
- `attribute_value(metric, value, tolerance=1%)`：数值命中哪年锚点 → 返回财年
- 未命中 → None（调用方按最新财年语境处理）

### L1 归因（DataAnchor，已实现）
```python
anchor.attribute_value("总资产", 841.6254)  # → (2023, 841.6254)
anchor.attribute_text_value("总资产", 1031.6263)  # → {fiscal_year: 2025, is_historical: False}
```

### L2 跨章检查器归因分桶（cross_chapter_consistency，已实现）
- `_extract_financial_data`：无年份标注的数字引用 → `attribute_text_value` 归因
  - 命中历史财年 → 进该财年桶（841.63→FY2023 桶，与 1031.63 的 FY2025 桶不碰 → 不误报）
  - 未命中 → None（默认最新语境）
- **None 桶与最新财年合并**：未标注引用视为当期，与命中最新锚点的值同桶比较
  （否则 999（未命中）与 1031.63（FY2025）不碰 → 真实冲突漏报——归因不掩盖真错误）
- 未标注的历史引用记入 `unattributed_historical`（写作遵从度可观测）

### L3 生成时校验（`validate_fiscal_references`，问题前移）
- `_generate_chapter` 生成后扫描：命中历史财年锚点的引用若无 FY 标注/对比语境 → 记问题
- 并入格式验证循环（all_issues）→ **不达标重试**（修复 prompt 补标注）
- 历史引用标注问题在**写作阶段拦截**，不再到 Gate4 才暴露

### 接线
- `check_cross_chapter_consistency(chapters, wind_data=None)`——gate3/review_repair_loop 传 wind_data
- `_generate_chapter` 的 fiscal_issues 并入验证循环

## 方法论（长期规避）

1. **财年语义唯一源 = DataAnchor**（含归因服务）——检查器/写作校验一律从锚点归因，不各自发明财年理解
2. **问题前移**：写作时校验（L3）→ 组装时归因比较（L2）→ Gate8 最终（后置）——三层防线
3. **"未标注历史引用"是写作缺陷**：L3 拦截（生成时），不是审查时发现
4. **归因不掩盖真错误**：未命中值仍按最新语境比较，同财年真冲突照常拦截

## 测试（test_fiscal_semantics.py，9 用例）

| 用例 | 验证 |
|---|---|
| attribute_value 归因（841.63→2023 / 1031.63→2025） | L1 |
| attribute_value 未命中 → None | L1 |
| attribute_text_value 历史/最新标记 | L1 |
| 跨章历史引用归因不误报（ch6 841.63 vs ch3 1031.63） | L2 |
| 同财年真冲突仍拦截（999 vs 1031.63） | L2 |
| validate_fiscal_references 拦截未标注历史引用 | L3 |
| FY 标注历史引用通过 | L3 |
| 无 wind_data 跳过 | L3 |
| _generate_chapter 接线 fiscal_issues | L3 接线 |

## 验收对照（重跑小鹏）

预期：ch6 的 841.63 归因 FY2023 → 跨章不误报；Gate4 失败项中"总资产最新财年矛盾"
消除；未标注历史引用在生成时被拦截重试（写作质量提升）。
