# Conclusion Validator Design Pattern

## Overview

A deterministic rule engine that post-processes LLM output to enforce consistent conclusions. Used when LLM tends to give overly lenient verdicts (e.g., "通过" even when P0 issues exist).

## When to Use

- LLM conclusion accuracy is low (< 50%)
- LLM tends to give "pass" even when critical issues exist
- Need auditable, reproducible verdict logic
- Need to enforce domain-specific rules (e.g., "any security P0 = reject")

## Architecture

```
LLM Output (trajectories)
    ↓
Issue Extraction (parser)
    ↓
Conclusion Validator (deterministic rules)
    ↓
Final Verdict (overrides LLM if needed)
```

## Core Rules

### Rule 1: P0 Veto
Any P0 issue → REJECT (configurable min_count and min_confidence)

### Rule 2: Threshold Rule
P1 ≥ N → REJECT (configurable per severity level)

### Rule 3: Weighted Score
P0×10 + P1×5 + P2×2 + P3×1, exceeds threshold → REJECT

### Rule 4: Domain Coverage
Required domains coverage < 60% → REJECT

## Key Features

### Confidence Threshold
Low-confidence P0 issues are downgraded to P1:
```python
if issue.confidence < config.confidence_threshold:
    issue.severity = Severity.P1  # Downgrade
```

### Shadow Mode
Record rule decisions without overriding LLM verdict:
```python
if config.shadow_mode:
    return ValidationResult(verdict=llm_verdict, shadow_log=rule_result)
```

### Fallback on Error
If rule engine throws, fall back to LLM verdict:
```python
try:
    return self._validate_internal(issues, llm_verdict)
except Exception as e:
    if config.fallback_to_llm:
        return ValidationResult(verdict=llm_verdict, fallback=True)
```

### Human Review Queue
When P0 veto triggers, mark for human review:
```python
if p0_veto_triggered and config.human_review_queue:
    result.human_review_required = True
```

## Data Model

```python
class Severity(str, Enum):
    P0 = "P0"  # Fatal
    P1 = "P1"  # Major
    P2 = "P2"  # Minor
    P3 = "P3"  # Suggestion
    
    @classmethod
    def from_str(cls, s: str) -> 'Severity':
        """Safe conversion with fuzzy matching and default P2"""
        mapping = {
            "CRITICAL": cls.P0, "P0": cls.P0, "致命": cls.P0,
            "MAJOR": cls.P1, "P1": cls.P1, "重大": cls.P1,
            "MINOR": cls.P2, "P2": cls.P2, "一般": cls.P2,
            "INFO": cls.P3, "P3": cls.P3, "建议": cls.P3,
        }
        return mapping.get(s.upper(), cls.P2)
```

## Integration Points

1. **HeavySkill**: Post-process trajectories to enforce conclusion rules
2. **hermes-eval**: Use as judge logic for automated evaluation
3. **workflow-gates**: Use as gate decision logic

## Configuration Template

```yaml
conclusion_validator:
  enabled: true
  shadow_mode: false          # true = record only, don't override
  fallback_to_llm: true       # true = fall back on engine error
  human_review_queue: true    # true = mark P0 rejections for review
  confidence_threshold: 0.8   # P0 issues below this are downgraded
  
  p0_veto:
    enabled: true
    min_count: 1
    min_confidence: 0.8
  
  threshold_rule:
    enabled: true
    thresholds:
      P0: 1
      P1: 3
      P2: 10
  
  weighted_score:
    enabled: true
    weights: { P0: 10, P1: 5, P2: 2, P3: 1 }
    reject_threshold: 15
    warn_threshold: 8
  
  domain_coverage:
    enabled: true
    required_domains: [安全, 架构, 性能]
    min_coverage: 0.6
```

## Anti-Patterns

1. **Shadow mode without try/except**: Shadow mode must catch all exceptions internally, never propagate
2. **Modifying Issue objects in-place**: Create new objects to avoid side effects
3. **Empty required_domains**: Division by zero in coverage calculation
4. **Confidence threshold without fallback**: If all issues are below threshold, verdict may be wrong
