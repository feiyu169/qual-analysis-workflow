# 方案C: 两阶段财报事实提取管线 — 设计摘要

**状态**: HeavySkill 审查通过 (需落实6个补强后实施)
**日期**: 2026-06-30

## 问题

财报 210万字符，截断 50K 仅覆盖 2.4%。运营数据 (DAU/GMV/ARPU) 在后半部分被截断。

## 方案

```
阶段1: 事实提取 (新增 fact_extractor.py)
  财报 725 章节 → 切 10 批 × 30K 字符 → LLM 逐批提取 JSON
  → 合并去重 → ExtractedFacts 结构体 (~5K 字符)

阶段2: 章节写作
  ExtractedFacts + Wind 数据 + 前序章节 → LLM 写每章
```

## HeavySkill 审查的 6 个必修补强

| # | 缺陷 | 修复 |
|---|------|------|
| 1 | chunk_size=40K×6=24万, 覆盖11% | 改为 30K×10, 覆盖>90% |
| 2 | JSON仅靠重试1次 | 截取{...}修复 + jsonschema校验 + 低温度 |
| 3 | 合并"取最后一批值"丢失数据 | 改为"任一有效值优先,后批覆盖同字段" |
| 4 | facts未持久化checkpoint | ExtractedFacts序列化写入checkpoint |
| 5 | 缺数值合理性校验 | 范围约束 + Wind交叉验证 |
| 6 | 批次边界割裂 | 切分保留5-10%重叠 |

## 数据结构

```python
@dataclass
class ExtractedFacts:
    operational: OperationalFacts  # DAU/MAU/GMV/ARPU/使用时长
    financial: FinancialFacts      # 财报原文财务数据(交叉验证Wind)
    management: ManagementFacts    # CEO/回购/分红
    business: BusinessFacts        # 分部收入/战略重点/风险
    meta: ExtractionMeta           # 提取元数据
```

## 成本

- LLM调用: +5-6次 (提取阶段)
- Token消耗: +200K
- 耗时: +2-3分钟
- 费用: ~1元RMB

## 工时

HeavySkill 修正: 8-10小时 (非原估5小时)
