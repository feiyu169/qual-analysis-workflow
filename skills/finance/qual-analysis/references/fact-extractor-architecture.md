# 方案 C：两阶段财报事实提取器 — 架构参考

## 问题背景

快手 2025 年报 725 章节、210 万字符。`_build_chapter_prompt()` 只传 50K 字符给 LLM，DAU/GMV/ARPU 等运营数据在后半部分被截断。

## 方案 C 架构

```
阶段1: fact_extractor.py (新增模块)
  财报全文 → 高价值章节选择 → 分批(30K×10, 5%重叠)
  → LLM 逐批提取 JSON → 三层JSON修复 → 合并去重
  → 结构化事实表 (~5K字符)

阶段2: workflow.py (修改)
  事实表 + Wind数据 + 相关原文片段 → LLM 写每章
```

## 关键文件

| 文件 | 说明 |
|------|------|
| `~/.hermes/tools/finance/fact_extractor.py` | 事实提取器 (数据结构+分批+JSON防护+合并+格式化) |
| `~/.hermes/tools/finance/data_context.py` | DataContext.facts 字段 |
| `~/.hermes/tools/finance/quality/checkpoint.py` | save_facts/load_facts |
| `~/.hermes/tools/finance/workflow.py` | Step 1.6 事实提取 + _build_chapter_prompt 使用事实表 |

## 数据结构

```python
ExtractedFacts
├── operational: OperationalFacts  # DAU, MAU, GMV, ARPU, 收入分部
├── financial: FinancialFacts      # 营收, 利润, 毛利率, 现金流
├── management: ManagementFacts    # CEO, 回购, 分红
├── business: BusinessFacts        # 业务分部, 战略重点
└── meta: ExtractionMeta           # 覆盖率, warnings, 耗时
```

## 多年份提取 (方案 C 完整版)

```
2023年报 → extract_facts() → facts_2023 (DAU=3.5亿, GMV=1.1万亿)
2024年报 → extract_facts() → facts_2024 (DAU=3.9亿, GMV=1.4万亿)
2025年报 → extract_facts() → facts_2025 (DAU=4.1亿, GMV=1.6万亿)
  → 合并为 3 年运营趋势表
  → Wind 财务数据交叉验证
  → 写入 checkpoint
```

## HeavySkill 审查要点 (v2.0)

1. chunk_size=30K × max_chunks=10, overlap=5%
2. JSON 三层防护: 直接解析 → 截取{...} → 正则修复
3. 合并策略: 任一有效值优先保留，后批覆盖同字段
4. 数值校验: DAU<100亿, GMV>0, 毛利率0-100%
5. Wind 交叉验证: 净利润/营收偏差<5%
6. facts 持久化到 checkpoint

## 已知限制

- 每份年报需要 10 次 LLM 调用 (~2元)
- 3 份年报 = 30 次调用 (~6元, ~15分钟)
- JSON 解析仍有失败风险 (三层防护缓解)
- 港股只有年报+中报，无季报
