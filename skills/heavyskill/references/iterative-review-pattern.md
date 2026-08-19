# HeavySkill 迭代审查模式

## 概述

当技术方案需要多轮审查时，使用 HeavySkill K=8 进行迭代审查，直到审查意见收敛。

## 流程

```
Round 1: 提出方案 → HeavySkill K=8 审查 → 记录问题清单
Round 2: 按审查意见修改 → 再次 K=8 审查 → 记录改进
Round N: 直到审查意见收敛（无新 P0 问题）
```

## 关键规则

1. **每轮必须修复所有 P0 问题后再提交**
2. **K=8 提供足够多样性**，4 摘要捕获共识
3. **子代理无法读取本地文件** → 必须将关键内容内联到 query 中
4. **审查结果可能被截断** → 需要读取完整 JSON 输出
5. **工时估算通常偏乐观 30-50%** → HeavySkill 会修正

## Query 模板

```bash
cd ~/.hermes/skills/heavyskill
python3 scripts/run_heavyskill.py \
  --query "请审查这份技术文档 v{N}（已修复 v{N-1} 审查发现的全部问题）。评估维度：1) ... 2) ... 3) ... 4) ..." \
  --include-file /path/to/document.md \
  --reason_k 8 \
  --summary_k 4 \
  --language cn \
  --output /tmp/heavyskill-review-v{N}.json \
  --quiet
```

## 读取审查结果

```python
import json
with open('/tmp/heavyskill-review-v{N}.json') as f:
    data = json.load(f)
final = data.get('deliberation', [{}])[0].get('deliberation_response', '')
print(final)
```

## 收敛轨迹示例

### HGF 工作流审查（2026-07-11）

| 版本 | 结果 | 核心问题 |
|------|------|----------|
| v1 | ❌ 不通过 | 4 项阻断性问题 |
| v2 | ❌ 不通过 | 4 项新问题 |
| v3 | 有条件通过 | 3 项代码级修正 |
| v4 | 通过 | 5 项细节需同步解决 |

### Qual 工作流改进审查（2026-07-11）

| 版本 | 结果 | 核心问题 |
|------|------|----------|
| v1.0 | ❌ 不通过 | EBITDA 字段缺失、净利润计算错误、单位混杂、毛利率硬编码 |
| v1.1 | ✅ 通过 | 5 项细节需在实施中同步解决 |

## 常见审查问题类型

1. **技术错误**：计算公式错误、字段类型错误、单位不一致
2. **逻辑缺陷**：条件分支遗漏、边界情况未处理、降级策略缺失
3. **架构问题**：职责不清、接口不一致、耦合过紧
4. **测试不足**：缺少边界测试、缺少回归测试、缺少集成测试
5. **文档缺失**：假设未说明、兼容性未标注、迁移指南缺失

## 审查后实施流程

1. 按审查意见修改技术文档
2. 重新提交 HeavySkill 审查
3. 审查通过后，按 HGF Gate-Driven 流程实施
4. 每个 Gate 完成后验证测试通过
