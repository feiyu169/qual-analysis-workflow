# qual框架报告质量提升 — 最终技术方案 v6.0

> 基于HeavySkill审查v5.0优化
> 生成时间: 2026-07-01

## 核心改进

1. 完整接口签名：ScoreDimensionCalculator、ScoringEngine、ReasoningChain
2. BudgetController+CircuitBreaker职责分离
3. 细分异常体系：InferenceError→6个子异常
4. 量化输出类型：ConfidenceLevel枚举+QuantifiedEffect/ScenarioProbability/CausalStrength
5. 因果建模方法论：Granger检验+敏感性分析+模板匹配
6. 证伪指标计算公式：反方论点强度40%+证伪指标可操作性40%+监控计划完整性20%
7. 强制降级规则：证伪<5分→D级，证伪<10分→C级
8. ColdStartPolicy协议+DefaultColdStartPolicy实现
9. 可观测性：TraceContext+结构化日志
10. ADR：4个架构决策记录

## 模块清单

| 模块 | 文件 | 功能 |
|------|------|------|
| 类型定义 | quality/types.py | QualityContext、量化输出类型、推理结果 |
| 异常体系 | quality/exceptions.py | 7种自定义异常 |
| 预算控制 | quality/budget.py | BudgetController+CircuitBreaker |
| 接口定义 | quality/interfaces.py | 4个ABC接口 |
| 因果建模器 | quality/reasoning/causal_modeler.py | Granger+敏感性+模板 |
| 反面论证验证器 | quality/reasoning/counter_validator.py | 角色切换→反方论点→证伪指标→监控 |
| 统一推理链 | quality/reasoning/causal_inference.py | 单链3阶段+CP-1~CP-5 |
| 冷启动策略 | quality/reasoning/cold_start.py | DefaultColdStartPolicy |
| 评分引擎 | quality/scoring/engine.py | 5维度评分+证伪得分+强制降级 |
| 5维度评分器 | quality/scoring/dimensions.py | D1~D5权重20/25/25/20/10 |
| CN/HK Scorer | quality/scoring/market_adjuster.py | 策略模式 |
| 计算公式库 | quality/formulas.py | PB/PE/ROE/增速标准化 |
| 数据口径映射 | quality/data_mapping.py | 净利润/净资产/股本口径 |
| 自动校验 | quality/validators.py | PE/PB/市值/增长率校验 |

## 评分维度权重

| 维度 | 权重 | 子维度 |
|------|------|--------|
| D1 数据完整性 | 20% | 数据源覆盖度/时效性/交叉验证 |
| D2 逻辑一致性 | 25% | 因果链条/数据-结论距离/估值一致性 |
| D3 分析深度 | 25% | 维度覆盖/横纵对比/正反论证 |
| D4 结论可靠性 | 20% | 投资建议/催化剂/风险矩阵 |
| D5 可操作性 | 10% | 目标价/仓位/止损 |

## 证伪得分公式

```
证伪得分 = 反方论点强度(40%) + 证伪指标可操作性(40%) + 监控计划完整性(20%)

反方论点强度 = avg(counter_strengths) × 40
证伪指标可操作性 = (有measurement_method且有threshold的指标数 / 总指标数) × 40
监控计划完整性 = 有triggers ? 20 : 0
```

## 强制降级规则

- 证伪得分 < 5分 → 强制D级
- 证伪得分 < 10分 → 降级到C级（仅对S/A/B级生效）

## 实测验证

### 万华化学(600309.SH)
- PB估值：1.99x（使用归母净资产1083亿）
- 评分：92分/A级
- 主要问题：缺DCF估值、管理层激励细节不足

### 快手(1024.HK)
- 经调整净利润：206亿（Non-IFRS口径）
- 总股本：43.5亿股
- 评分：92分/A级
- 主要问题：缺DCF估值、行业数据支撑偏弱

### 代码实现评分
- 综合评分：93/100
- 核心架构与v6.0技术方案高度一致
