# Quality System Architecture (v6.0) — 2026-07-01

## 模块结构

```
~/.hermes/tools/finance/quality/
├── types.py              # QualityContext, CounterResult, ReasoningResult等核心类型
├── exceptions.py         # InferenceError层次结构(6个异常类)
├── budget.py             # BudgetController(软限制) + CircuitBreaker(硬阻断)
├── interfaces.py         # ScoreDimensionCalculator/ScoringEngine/ReasoningChain/ColdStartPolicy
├── formulas.py           # 标准化计算公式库(PE/PB/ROE/growth等)
├── data_mapping.py       # 数据口径映射表(GAAP/adjusted/core/deducted)
├── validators.py         # 自动校验机制(PE/PB/market_cap/growth_rate)
├── risk_quantification.py # 风险量化分析(RiskFactor/RiskAssessment/StressTest)
├── margin_of_safety.py   # 安全边际分析(ValuationRange/SafetyMarginResult)
├── sensitivity.py        # 敏感性分析(1-way/2-way/scenario with CI)
├── dcf.py                # DCF估值(WACC/Gordon/exit-multiple/sensitivity)
├── reasoning/
│   ├── causal_modeler.py     # 因果建模(Granger检验+敏感性+模板匹配)
│   ├── counter_validator.py  # 反面论证验证(角色切换→论点→证伪指标→监控)
│   ├── causal_inference.py   # 统一推理链(单链3阶段+5检查点)
│   └── cold_start.py         # 冷启动策略(数据不足时降级输出)
├── scoring/
│   ├── engine.py             # 标准评分引擎(5维度加权+证伪+强制降级)
│   ├── dimensions.py         # 5维度评分器(权重20/25/25/20/10)
│   └── market_adjuster.py    # CN/HK市场调整器(策略模式)
├── templates/
│   └── management_incentive.py # 管理层激励分析模板
└── tests/
    ├── test_integration.py   # 端到端集成测试
    └── test_golden_set.py    # 黄金集测试(万华化学+快手)
```

## 关键接口签名

```python
# 评分维度
class ScoreDimensionCalculator(ABC):
    def calculate(content, context) -> ScoreDimensionResult
    def get_max_score() -> float
    def get_weight() -> float  # 必须实现，不能用get_max_score替代
    def get_dimension_id() -> str

# 评分引擎
class ScoringEngine(ABC):
    def score(reasoning_result, context) -> ScoreReport

# 推理链
class ReasoningChain(ABC):
    def run(evidence, config, budget) -> ReasoningResult

# 冷启动
class ColdStartPolicy(ABC):
    def get_seed_data() -> EvidenceBundle
    def get_min_data_threshold() -> dict
    def get_fallback_output() -> ReasoningResult
    def is_cold_start(evidence) -> bool
```

## 评分权重

| 维度 | 权重 | 子维度 |
|------|------|--------|
| D1 数据完整性 | 20% | 源覆盖40%+时效30%+交叉验证30% |
| D2 逻辑一致性 | 25% | 因果链40%+数据距离30%+估值一致性30% |
| D3 分析深度 | 25% | 维度覆盖30%+横纵对比30%+正反论证40% |
| D4 结论可靠性 | 20% | 投资建议40%+催化剂30%+风险矩阵30% |
| D5 可操作性 | 10% | 目标价40%+仓位30%+止损30% |

## 证伪得分公式

```
falsification_score = (
    avg(counter_strengths) * 40 +   # 反方论点强度
    indicator_quality * 40 +         # 证伪指标可操作性
    (20 if monitoring.triggers else 0)  # 监控计划完整性
)
```

强制降级规则：
- falsification_score < 5 → 强制D级
- falsification_score < 10 → 降级到C级（原S/A/B级）

## CN/HK市场调整规则

**CN市场**:
- 扣非净利润 → +2.0
- 经营现金流/净利润>80% → +3.0
- 关联交易>10% → -5.0
- 商誉>20% → -3.0
- 应收账款>30% → -2.0

**HK市场**:
- NAV → +2.0
- 核心盈利 → +2.0
- 双币种 → +1.0
- HKFRS → +1.0
- 南下资金 → +1.0
- 做空>10% → -3.0

## Checkpoints

| 检查点 | 含义 | 阈值 |
|--------|------|------|
| CP-1 | 数据完整性 | 0.8 |
| CP-2 | 因果关系数量 | 2 |
| CP-3 | 情景数量 | 1 |
| CP-4 | 反方论点数量 | 2 |
| CP-5 | 置信度 | 0.6 |

## 关键修复记录

1. **PB必须用归母净资产**: 万华化学PB从1.79x修正为1.99x
2. **CounterResult需strength字段**: 否则证伪得分退化为计数
3. **ColdStartPolicy需集成到推理链**: 否则定义了但未使用
4. **CircuitBreaker HALF_OPEN需探测限制**: 否则无限探测
5. **get_weight()不能用get_max_score()替代**: 否则权重退化为等权
6. **增长率校验需三处生效**: 实现+调用+数据传递
7. **情景分析需置信区间**: 否则D5维度评分无数据来源
8. **Granger检验用scipy替代statsmodels**: 避免依赖冲突
