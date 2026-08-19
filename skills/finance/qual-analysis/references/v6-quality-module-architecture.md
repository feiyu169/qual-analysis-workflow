# v6.0 Quality Module Architecture

## Module Structure

```
quality/
├── __init__.py              # Package exports
├── types.py                 # Core type definitions (QualityContext, etc.)
├── exceptions.py            # Exception hierarchy (6 exceptions)
├── budget.py                # BudgetController + CircuitBreaker
├── interfaces.py            # ABC interfaces (4 interfaces)
├── formulas.py              # Standardized calculation formulas
├── data_mapping.py          # Data caliber mapping table
├── validators.py            # Auto-validation mechanism
├── dcf.py                   # DCF valuation module
├── risk_quantification.py   # Risk quantification analysis
├── margin_of_safety.py      # Margin of safety analysis
├── sensitivity.py           # Sensitivity analysis
├── reasoning/
│   ├── __init__.py
│   ├── causal_modeler.py    # Causal modeling (Granger + sensitivity + template)
│   ├── counter_validator.py # Counter-argument validator
│   ├── causal_inference.py  # Unified reasoning chain (3 stages)
│   └── cold_start.py        # Cold start policy
├── scoring/
│   ├── __init__.py
│   ├── engine.py            # Scoring engine
│   ├── dimensions.py        # 5-dimension scorers
│   └── market_adjuster.py   # CN/HK market adjusters
├── templates/
│   └── management_incentive.py  # Management incentive analysis
├── tests/
│   ├── __init__.py
│   ├── test_integration.py  # Integration tests
│   └── test_golden_set.py   # Golden set tests
└── docs/
    └── data_mapping_spec.md # Data caliber specification
```

## Core Interfaces

### ScoreDimensionCalculator
```python
class ScoreDimensionCalculator(ABC):
    @abstractmethod
    def get_dimension_id(self) -> str: ...
    @abstractmethod
    def get_max_score(self) -> float: ...
    @abstractmethod
    def get_weight(self) -> float: ...  # ⚠️ NOT get_max_score()
    @abstractmethod
    def calculate(self, reasoning_result, context) -> DimensionScore: ...
```

### ScoringEngine
```python
class ScoringEngine(ABC):
    @abstractmethod
    def register_dimension(self, calculator: ScoreDimensionCalculator) -> None: ...
    @abstractmethod
    def score(self, reasoning_result: ReasoningResult, context: QualityContext) -> ScoreReport: ...
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
    def get_seed_data(self) -> EvidenceBundle: ...
    @abstractmethod
    def get_min_data_threshold(self) -> dict[str, int]: ...
    @abstractmethod
    def get_fallback_output(self) -> ReasoningResult: ...
    @abstractmethod
    def is_cold_start(self, evidence: EvidenceBundle) -> bool: ...
```

## Scoring Weights

| Dimension | Weight | ID |
|-----------|--------|-----|
| Data Completeness | 20% | D1_data_completeness |
| Logic Consistency | 25% | D2_logic_consistency |
| Analysis Depth | 25% | D3_analysis_depth |
| Conclusion Reliability | 20% | D4_conclusion_reliability |
| Actionability | 10% | D5_actionability |

## Falsification Score Formula

```
falsification_score = (
    avg(counter_strengths) * 40 +      # Counter-argument strength (weighted)
    indicator_quality * 40 +            # Falsification indicator operability
    has_monitoring_plan * 20            # Monitoring plan completeness
)
```

**Forced Downgrade Rules**:
- falsification_score < 5 → Force grade D
- falsification_score < 10 → Downgrade to C (if S/A/B)

## CN/HK Market Adjuster Rules

### CN Market
- 扣非净利润: +2.0
- 经营现金流/净利润 > 80%: +3.0
- 关联交易 > 10%: -5.0
- 商誉 > 20%: -3.0
- 应收账款 > 30%: -2.0

### HK Market
- NAV: +2.0
- 核心盈利: +2.0
- 双币种: +1.0
- HKFRS: +1.0
- 南下资金: +1.0
- 做空 > 10%: -3.0

## Checkpoints (CP-1 to CP-5)

| Checkpoint | Threshold | Description |
|------------|-----------|-------------|
| CP-1 | 0.8 | Data completeness |
| CP-2 | 2 | Causal relations count |
| CP-3 | 1 | Scenario count |
| CP-4 | 2 | Counter-arguments count |
| CP-5 | 0.6 | Confidence level |

## Key Pitfalls

1. **get_weight() vs get_max_score()**: Weight and max score are independent concepts
2. **CounterResult丢失strength**: Must add `counter_strengths` field
3. **ColdStartPolicy未集成**: Must check in `run()` before reasoning
4. **增长率校验未接入**: Must implement + call + pass data
5. **情景分析缺置信区间**: Must calculate from scenario distribution
6. **CircuitBreaker HALF_OPEN**: Must limit probe count
7. **BudgetController阈值**: Must be configurable
8. **中文标点SyntaxError**: Only use ASCII in Python code

## Verification Commands

```bash
# Import verification
cd ~/.hermes/tools && python3 -c "from finance.quality import *; print('OK')"

# Golden set test
cd ~/.hermes/tools && python3 finance/quality/tests/test_golden_set.py

# Integration test
cd ~/.hermes/tools && python3 finance/quality/tests/test_integration.py
```
