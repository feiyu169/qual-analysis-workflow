# v6.0 Implementation Details — Quality Module

> Verified: 2026-07-01
> Files: `~/.hermes/tools/finance/quality/`

## Module Architecture

```
quality/
├── types.py              # QualityContext,量化输出类型,推理结果
├── exceptions.py         # 7种异常(层次结构)
├── budget.py             # BudgetController + CircuitBreaker + ReasoningBudget
├── interfaces.py         # 4个ABC接口
├── formulas.py           # 标准化计算公式库(13个公式)
├── data_mapping.py       # 数据口径映射表(5个指标)
├── validators.py         # 自动校验机制(6个校验规则)
├── dcf.py                # DCF估值模块
├── sensitivity.py        # 敏感性分析(单变量/双变量/情景)
├── templates/
│   └── management_incentive.py  # 管理层激励分析模板
├── reasoning/
│   ├── causal_modeler.py       # 因果建模器(Granger+敏感性+模板)
│   ├── counter_validator.py    # 反面论证验证器
│   ├── causal_inference.py     # 统一推理链(单链3阶段)
│   └── cold_start.py           # 冷启动策略
├── scoring/
│   ├── engine.py               # 评分引擎(含ReportValidator集成)
│   ├── dimensions.py           # 5维度评分器
│   └── market_adjuster.py      # CN/HK Scorer策略模式
└── tests/
    └── test_integration.py     # 集成测试
```

## Key Interface Contracts

### ScoreDimensionCalculator
```python
class ScoreDimensionCalculator(ABC):
    @abstractmethod
    def calculate(self, reasoning_result: ReasoningResult, context: QualityContext) -> DimensionScore: ...
    @abstractmethod
    def get_max_score(self) -> float: ...
    @abstractmethod
    def get_weight(self) -> float: ...  # ⚠️ 必须实现，不能用get_max_score替代
    @abstractmethod
    def get_dimension_id(self) -> str: ...
```

### ReasoningChain
```python
class ReasoningChain(ABC):
    @abstractmethod
    def run(self, evidence: EvidenceBundle, config: ScenarioConfig, budget: ReasoningBudget) -> ReasoningResult: ...
```

### ColdStartPolicy
```python
class ColdStartPolicy(ABC):
    @abstractmethod
    def is_cold_start(self, evidence: EvidenceBundle) -> bool: ...
    @abstractmethod
    def get_fallback_output(self) -> ReasoningResult: ...
```

## Scoring Weights (must match)

| Dimension | ID | Weight | Sub-dimensions |
|-----------|-----|--------|----------------|
| 数据完整性 | D1 | 0.20 | 源覆盖40%+时效30%+交叉验证30% |
| 逻辑一致性 | D2 | 0.25 | 因果链40%+数据距离30%+估值一致性30% |
| 分析深度 | D3 | 0.25 | 维度覆盖30%+横纵对比30%+正反论证40% |
| 结论可靠性 | D4 | 0.20 | 投资建议40%+催化剂30%+风险矩阵30% |
| 可操作性 | D5 | 0.10 | 目标价40%+仓位30%+止损30% |

## Falsification Score Formula

```
score = avg(counter_strengths) × 40  # 反方论点强度(使用strength加权)
      + indicator_quality × 40       # 证伪指标可操作性
      + (20 if monitoring.triggers)   # 监控计划完整性
```

**强制降级规则**: score<5→D级, score<10→C级(仅S/A/B降级)

## CN/HK Scorer Rules

### CN Market
- 扣非净利润优先: +2.0
- 经营现金流/净利润>80%: +3.0
- 关联交易>10%: -5.0
- 商誉>20%: -3.0
- 应收账款>30%: -2.0

### HK Market
- NAV/核心盈利: 各+2.0
- 双币种/HKFRS/南下资金: 各+1.0
- 做空>10%: -3.0

## DCF Module

```python
from finance.quality.dcf import DCFCalculator, DCFInputs

inputs = DCFInputs(
    fcf_projections=[100, 110, 120, 130, 140],
    risk_free_rate=0.03, equity_risk_premium=0.06, beta=1.0,
    cost_of_debt=0.05, tax_rate=0.25, debt_ratio=0.2,
    terminal_growth_rate=0.02,
    shares_outstanding=43.5, current_price=41.60
)
result = DCFCalculator().calculate(inputs)
# result.per_share_value, result.wacc, result.sensitivity
```

## Real-World Test Results (2026-07-01)

### 万华化学 (600309.SH)
- Wind数据匹配率: 28/28 (100%)
- 发现问题: PB计算错误(1.79x→1.99x, 使用总权益而非归母净资产)
- 修正后PB: 1.99x

### 快手 (1024.HK)
- Wind数据匹配率: 基础财务数据100%
- 发现问题:
  - 经调整净利润口径不一致(Non-IFRS vs 扣非, 偏差10-30%)
  - 总股本单位错误(4.35亿→43.5亿)
  - 经营利润增速计算错误(33.5% vs 41.4%)
- 报告评级: 92分/A级(修正后)

### Integration Test Output
```
✅ 推理链执行成功: 置信度=0.78, 因果关系=1条, 反方论点=2条
✅ 评分引擎执行成功: 总分=72.6, 等级=B, 证伪=80.0
✅ CN市场调整: 72.6→77.6
✅ HK市场调整: 72.6→77.6
✅ 冷启动判断: 数据不足时正确触发
```
