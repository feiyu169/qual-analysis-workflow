# v4→v5 快手评估修复记录 (2026-06-30)

## v4 评估结果 (52/100)

7个根因问题:
1. ch00/ch10 Placeholder (0分)
2. 事实性错误×4 (投资京东拼多多/宿华仍任CEO/P-E标亏损/分红回购矛盾)
3. 财报原文使用极弱 ("约XX%")
4. lens视角全部缺失
5. must_not_cover违反×3
6. ch04只有3个变化(要求5个)
7. 第7章有未填写的占位符

## 修复方案 (9项)

代码修复 (workflow.py):
- LENS_DESCRIPTIONS字典(6个lens: platform/tech/growth/dividend/regulatory/asset_light)
- filing_summary[:4000]→[:8000]
- ch04 contract改为"至少5个"
- Step 1.5自动fetch_filing
- mark_chapter_audited传入semantic数据
- save_repair_history()新增方法

Prompt修复 (write-prompt.md + audit-prompt.md):
- 事实核查红线(5条)
- 数据精确性要求
- 事实准确性审计维度(15%)
- 边界遵守度检查规则

## v5 评估结果 (83.8/100)

| 章节 | v4 | v5 | 改善 |
|------|----|----|------|
| ch00 | 0 | 88 | +88 |
| ch10 | 0 | 88 | +88 |
| ch05 | 50 | 82 | +32 |
| ch06 | 45 | 83 | +38 |
| ch07 | 55 | 85 | +30 |

5/7根因完全修复, 2/7大幅改善
HeavySkill预估80-85, 实际83.8, 落在区间内

## 仍存在的不足

1. lens视角深度不足(ch02/ch03较好,其他一般)
2. 2处must_not_cover轻微越界
3. 部分数据仍标注"数据不足"
4. LLM生成的过渡文字需后处理清理
