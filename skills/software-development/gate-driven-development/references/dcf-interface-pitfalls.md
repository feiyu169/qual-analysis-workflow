# DCF Module Interface Pitfalls (Verified 2026-07-29)

## DCFInputs Field Names

Existing `quality/dcf.py` DCFInputs dataclass uses these field names (NOT what you'd expect):

| Expected | Actual | Type | Default |
|----------|--------|------|---------|
| `wacc` | ❌ N/A — must calculate from components | - | - |
| `g` or `terminal_growth` | `terminal_growth_rate` | float | 0.02 |
| `shares` | `shares_outstanding` | float | 1.0 |
| `net_debt` | ❌ N/A — use `debt_ratio` | float | 0.0 |
| `fcf` | `fcf_projections` | list[float] | [] |

### WACC Calculation Components

```python
inputs.risk_free_rate    # float, default 0.03
inputs.equity_risk_premium  # float, default 0.06
inputs.beta             # float, default 1.0
inputs.cost_of_debt     # float, default 0.05
inputs.tax_rate         # float, default 0.25
inputs.debt_ratio       # float, default 0.0
```

### WACC Formula

```python
ke = risk_free_rate + beta * equity_risk_premium
kd = cost_of_debt * (1 - tax_rate)
wacc = ke * (1 - debt_ratio) + kd * debt_ratio
```

## DCFResult Field Names

| Field | Type | Notes |
|-------|------|-------|
| `equity_value` | float | NOT `ev` |
| `per_share_value` | float | |
| `current_price` | float | |
| `upside` | float | |
| `wacc` | float | |
| `cost_of_equity` | float | |
| `terminal_value` | float | |
| `terminal_value_pv` | float | Present value of terminal value |
| `fcf_pv` | float | PV of FCF projections |
| `sensitivity` | dict | |
| `yearly_data` | list | |
| `warnings` | list | |

## DCFService Integration Pattern

```python
from finance.quality.dcf import DCFCalculator, DCFInputs, DCFResult

class DCFService:
    def __init__(self, calculator=None, config=None):
        self._calculator = calculator or DCFCalculator()
        self._config = config or DCFServiceConfig()
    
    def _calculate_wacc(self, inputs: DCFInputs) -> float:
        ke = inputs.risk_free_rate + inputs.beta * inputs.equity_risk_premium
        kd = inputs.cost_of_debt * (1 - inputs.tax_rate)
        return ke * (1 - inputs.debt_ratio) + kd * inputs.debt_ratio
    
    def run_full_analysis(self, inputs: DCFInputs) -> DCFAnalysisResult:
        wacc = self._calculate_wacc(inputs)
        if wacc <= inputs.terminal_growth_rate:
            warnings.append(f"WACC({wacc:.2%}) must exceed g({inputs.terminal_growth_rate:.2%})")
        result = self._calculator.calculate(inputs)
        return DCFAnalysisResult(dcf=result, warnings=warnings)
```

## Common Errors

```
AttributeError: 'DCFInputs' object has no attribute 'wacc'
→ Use _calculate_wacc(inputs) method

AttributeError: 'DCFResult' object has no attribute 'ev'
→ Use result.equity_value

AttributeError: 'DCFInputs' object has no attribute 'g'
→ Use inputs.terminal_growth_rate
```
