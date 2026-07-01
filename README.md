# Qual Analysis Workflow

一个基于AI的投资分析质量保证框架，用于生成结构化的投资分析报告。

## 🎯 项目目标

解决AI生成投资分析报告时的常见问题：
- 数据口径不一致
- 计算公式错误
- 缺乏质量校验
- 分析深度不足

## 📁 项目结构

```
qual-analysis-workflow/
├── quality/                    # 核心代码
│   ├── __init__.py            # 模块导出
│   ├── types.py               # 类型定义
│   ├── exceptions.py          # 异常体系
│   ├── budget.py              # 预算控制
│   ├── interfaces.py          # 接口定义
│   ├── formulas.py            # 标准化计算公式
│   ├── data_mapping.py        # 数据口径映射
│   ├── validators.py          # 自动校验机制
│   ├── dcf.py                 # DCF估值模块
│   ├── sensitivity.py         # 敏感性分析
│   ├── risk_quantification.py # 风险量化分析
│   ├── margin_of_safety.py    # 安全边际分析
│   ├── reasoning/             # 推理引擎
│   │   ├── causal_modeler.py  # 因果建模器
│   │   ├── counter_validator.py # 反面论证验证
│   │   ├── causal_inference.py # 统一推理链
│   │   └── cold_start.py      # 冷启动策略
│   ├── scoring/               # 评分器
│   │   ├── engine.py          # 评分引擎
│   │   ├── dimensions.py      # 5维度评分
│   │   └── market_adjuster.py # CN/HK市场调整
│   ├── templates/             # 分析模板
│   │   └── management_incentive.py # 管理层激励
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

## 🚀 快速开始

### 安装依赖

```bash
pip install scipy numpy
```

### 基本使用

```python
from quality import (
    StandardScoringEngine,
    CausalInferenceChain,
    ReasoningBudget,
    QualityContext,
    EvidenceBundle,
    ScenarioConfig,
    Formulas,
    Validators,
)

# 1. 计算估值指标
pe = Formulas.pe_ratio(market_cap=2152, net_income=125.27)
pb = Formulas.pb_ratio(market_cap=2152, equity_attributable_to_parent=1083)

# 2. 校验数据
result = Validators.validate_pb(
    pb_value=pb.value,
    equity_type="parent",
    market_cap=2152,
    equity=1083
)

# 3. 执行推理
chain = CausalInferenceChain()
budget = ReasoningBudget()
evidence = EvidenceBundle(
    financial_data={"revenue": [100, 110, 120]},
    news_data=[{"title": "公司业绩增长"}],
    industry_data={"growth": 0.15},
    filing_data={"sections": {}}
)
reasoning_result = chain.run(evidence, ScenarioConfig(), budget)

# 4. 评分
engine = StandardScoringEngine()
# ... 注册维度计算器
report = engine.score(reasoning_result, context)
```

## 📊 核心功能

### 1. 标准化计算公式

避免计算错误，提供标准化的估值计算：

```python
from quality import Formulas

# PE计算（支持多种口径）
pe_gaap = Formulas.pe_ratio(market_cap, net_income, net_income_type="GAAP")
pe_adjusted = Formulas.pe_ratio(market_cap, net_income, net_income_type="adjusted")

# PB计算（强制使用归母净资产）
pb = Formulas.pb_ratio(market_cap, equity_attributable_to_parent)

# 市值计算（含单位检查）
mc = Formulas.market_cap(share_price, total_shares)  # total_shares单位：亿股
```

### 2. 数据口径映射

统一投资分析中的数据口径：

```python
from quality import get_default_mapping_registry

registry = get_default_mapping_registry()

# 获取净利润口径定义
definition = registry.get_definition("net_income", "adjusted")
print(f"名称: {definition.name}")
print(f"说明: {definition.description}")
print(f"来源: {definition.source}")
```

### 3. 自动校验机制

自动校验PE/PB/市值/增长率等关键指标：

```python
from quality import Validators

# 校验PB（必须使用归母净资产）
result = Validators.validate_pb(
    pb_value=1.99,
    equity_type="parent",  # 必须是"parent"
    market_cap=2152,
    equity=1083
)

if not result.is_valid:
    print(f"校验失败: {result.errors}")
```

### 4. 推理引擎

单链3阶段推理：数据预处理→因果-情景建模→结论合成

```python
from quality import CausalInferenceChain, ReasoningBudget

chain = CausalInferenceChain()
budget = ReasoningBudget()

result = chain.run(evidence, config, budget)
print(f"置信度: {result.confidence}")
print(f"检查点通过: {len(result.checkpoints_passed)}")
```

### 5. 评分引擎

5维度加权评分：数据完整性(20%)、逻辑一致性(25%)、分析深度(25%)、结论可靠性(20%)、可操作性(10%)

```python
from quality import StandardScoringEngine

engine = StandardScoringEngine()
# 注册5个维度计算器
engine.register_dimension(DataCompletenessCalculator())
engine.register_dimension(LogicConsistencyCalculator())
engine.register_dimension(AnalysisDepthCalculator())
engine.register_dimension(ConclusionReliabilityCalculator())
engine.register_dimension(ActionabilityCalculator())

report = engine.score(reasoning_result, context)
print(f"总分: {report.total_score}")
print(f"等级: {report.grade}")
```

### 6. DCF估值

完整的DCF估值模块：

```python
from quality import DCFCalculator, DCFInputs

inputs = DCFInputs(
    fcf_projections=[100, 110, 120, 130, 140],
    risk_free_rate=0.03,
    equity_risk_premium=0.06,
    beta=1.0,
    terminal_growth_rate=0.02,
    shares_outstanding=43.5,
    current_price=41.60
)

calculator = DCFCalculator()
result = calculator.calculate(inputs)
print(f"每股价值: {result.per_share_value:.2f}元")
print(f"上行空间: {result.upside:.1f}%")
```

## 📋 数据口径规范

详见 [data_mapping_spec.md](quality/docs/data_mapping_spec.md)

### 关键提醒

| 问题 | 公司 | 正确做法 |
|------|------|----------|
| PB计算 | 万华化学 | 使用归母净资产1083亿，PB=1.99x |
| 口径标注 | 快手 | 明确标注Non-IFRS口径，与GAAP差异10-30% |
| 总股本单位 | 快手 | 43.5亿股，不是4.35亿股 |

## 🧪 测试

### 运行集成测试

```bash
cd quality/tests
python test_integration.py
```

### 运行黄金集测试

```bash
cd quality/tests
python test_golden_set.py
```

## 📝 报告示例

- [万华化学(600309.SH)](examples/wanhua-analysis-report.md)
- [快手(1024.HK)](examples/kuaishou-analysis-report.md)

## 🔧 技术方案

### 核心架构

```
┌─────────────────────────────────────────────────────────┐
│                    Quality Layer                        │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  Reasoning  │  │   Scoring   │  │  Validation │    │
│  │   Engine    │  │   Engine    │  │   Layer     │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
│         │               │               │              │
│         ▼               ▼               ▼              │
│  ┌─────────────────────────────────────────────────┐  │
│  │              Formulas & Data Mapping            │  │
│  └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 📊 质量保证

### 评分维度

| 维度 | 权重 | 说明 |
|------|------|------|
| 数据完整性 | 20% | 数据源覆盖度、时效性、交叉验证 |
| 逻辑一致性 | 25% | 因果链条、数据-结论距离、估值一致性 |
| 分析深度 | 25% | 维度覆盖、横纵对比、正反论证 |
| 结论可靠性 | 20% | 投资建议、催化剂、风险矩阵 |
| 可操作性 | 10% | 目标价、仓位、止损 |

### 强制降级规则

- 证伪得分 < 5分 → 强制D级
- 证伪得分 < 10分 → 降级到C级

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 📄 许可证

MIT License

## 🙏 致谢

- Wind API 提供金融数据
- Snowball (雪球) 提供社区平台
- 所有提出批评意见的投资者

---

**免责声明**：本框架生成的分析报告仅供参考，不构成投资建议。投资有风险，入市需谨慎。
