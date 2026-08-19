# qual-analysis-workflow GitHub 项目

> 发布日期: 2026-07-01
> 仓库地址: https://github.com/feiyu169/qual-analysis-workflow

## 项目概述

投资分析质量保证框架，从 qual-analysis skill 的质量层代码中提取为独立项目。

## 项目结构

```
qual-analysis-workflow/
├── quality/                    # 核心代码
│   ├── __init__.py            # 模块导出
│   ├── types.py               # 类型定义（QualityContext、量化输出类型）
│   ├── exceptions.py          # 异常体系（7种异常）
│   ├── budget.py              # 预算控制（BudgetController+CircuitBreaker）
│   ├── interfaces.py          # 接口定义（4个ABC接口）
│   ├── formulas.py            # 标准化计算公式库
│   ├── data_mapping.py        # 数据口径映射表
│   ├── validators.py          # 自动校验机制
│   ├── dcf.py                 # DCF估值模块
│   ├── sensitivity.py         # 敏感性分析
│   ├── risk_quantification.py # 风险量化分析
│   ├── margin_of_safety.py    # 安全边际分析
│   ├── reasoning/             # 推理引擎
│   │   ├── causal_modeler.py  # 因果建模器（Granger+敏感性+模板）
│   │   ├── counter_validator.py # 反面论证验证
│   │   ├── causal_inference.py # 统一推理链（单链3阶段）
│   │   └── cold_start.py      # 冷启动策略
│   ├── scoring/               # 评分器
│   │   ├── engine.py          # 评分引擎
│   │   ├── dimensions.py      # 5维度评分（20/25/25/20/10权重）
│   │   └── market_adjuster.py # CN/HK市场调整器
│   ├── templates/             # 分析模板
│   │   └── management_incentive.py # 管理层激励分析
│   ├── docs/                  # 文档
│   │   └── data_mapping_spec.md # 数据口径规范
│   └── tests/                 # 测试
│       ├── test_integration.py # 集成测试
│       └── test_golden_set.py  # 黄金集测试
├── examples/                  # 报告示例
│   ├── wanhua-analysis-report.md # 万华化学报告
│   └── kuaishou-analysis-report.md # 快手报告
└── README.md                  # 项目说明
```

## 核心模块

| 模块 | 功能 | 关键接口 |
|------|------|----------|
| formulas.py | 标准化计算公式 | pe_ratio/pb_ratio/market_cap/growth_rate/roe |
| data_mapping.py | 数据口径映射 | DataMappingRegistry/get_default_mapping_registry |
| validators.py | 自动校验 | Validators.validate_pe/validate_pb/validate_market_cap |
| reasoning/causal_inference.py | 统一推理链 | CausalInferenceChain.run(evidence, config, budget) |
| scoring/engine.py | 评分引擎 | StandardScoringEngine.score(reasoning_result, context) |
| dcf.py | DCF估值 | DCFCalculator.calculate(inputs) |
| sensitivity.py | 敏感性分析 | SensitivityAnalyzer.one_way_sensitivity/two_way_sensitivity/scenario_analysis |
| risk_quantification.py | 风险量化 | RiskQuantifier.assess_risks/stress_test |
| margin_of_safety.py | 安全边际 | MarginOfSafetyAnalyzer.analyze |

## 评分权重

| 维度 | 权重 |
|------|------|
| 数据完整性 | 20% |
| 逻辑一致性 | 25% |
| 分析深度 | 25% |
| 结论可靠性 | 20% |
| 可操作性 | 10% |

## 证伪得分公式

```
证伪得分 = 反方论点强度(40%) + 证伪指标可操作性(40%) + 监控计划完整性(20%)
```

- 反方论点强度 = avg(counter_strengths) × 40
- 证伪指标可操作性 = (有measurement_method和threshold的指标数 / 总指标数) × 40
- 监控计划完整性 = 有triggers则20，否则0

## 强制降级规则

- 证伪得分 < 5分 → 强制D级
- 证伪得分 < 10分 → 降级到C级（仅S/A/B级）

## 依赖

```bash
pip install scipy numpy
```

## 使用示例

```python
from quality import Formulas, Validators

# 计算估值
pe = Formulas.pe_ratio(market_cap=2152, net_income=125.27)
pb = Formulas.pb_ratio(market_cap=2152, equity_attributable_to_parent=1083)

# 校验数据
result = Validators.validate_pb(pb.value, "parent", 2152, 1083)
assert result.is_valid
```

## 实测验证

| 公司 | PE | PB | 校验结果 |
|------|-----|-----|----------|
| 万华化学(600309.SH) | 17.18x | 1.99x | ✅ PASS |
| 快手(1024.HK) | 9.67x(GAAP) / 8.74x(Adjusted) | - | ✅ PASS |
