# ConclusionValidator — 优化 HeavySkill 结论准确率

## 问题背景

HeavySkill 的结论准确率仅 14%：即使发现多个 P0 问题，仍倾向于给出「通过」结论。

## 解决方案

设计一个确定性规则引擎，在 LLM 输出之后强制覆盖错误结论。

## 核心规则

1. **P0 一票否决**：任何 P0 问题（置信度 ≥ 0.8）→ 直接 REJECT
2. **P1 累计阈值**：P1 ≥ 3 → REJECT
3. **加权评分**：P0×10 + P1×5 + P2×2 + P3×1，超过阈值触发
4. **领域覆盖率**：安全/架构/性能等领域覆盖率 < 60% → REJECT

## 关键设计

- **置信度过滤**：低置信度 P0 问题自动降级为 P1
- **影子模式**：只记录不覆盖，用于灰度测试
- **异常回退**：规则引擎异常时回退到 LLM 结论
- **人工确认队列**：P0 否决时标记 human_review_required

## 代码位置

```
~/.hermes/skills/heavyskill-optimize/
├── src/
│   ├── models.py          # 数据模型（Severity、Verdict、Issue）
│   ├── validator.py       # 结论校验引擎
│   ├── parser.py          # 检查清单解析器
│   ├── config.py          # 配置系统
│   └── integration.py     # HeavySkill 集成指南
└── tests/
    └── test_validator.py  # 16 个测试用例
```

## 集成方式

```python
from src.integration import integrate_with_heavyskill

# 增强 HeavySkill 输出
enhanced = integrate_with_heavyskill(heavyskill_output)

# 检查验证结果
print(enhanced['validation']['verdict'])  # PASS/CONDITIONAL/REJECT
print(enhanced['validation']['rules_applied'])  # 规则执行详情
```

## 预期效果

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 结论准确率 | 14% | ≥95% |
| 安全/架构发现率 | 40% | ≥85% |
| 改进建议可执行率 | 20% | ≥80% |

## 审查流程

V1 → V2 → V3 迭代审查模式：
- V1: 初始方案，HeavySkill 发现 4 个 P0 问题
- V2: 修订未整合，审查不通过
- V3: 完整整合版，附意见通过
- V3.1: 修复专家审查问题，最终通过
