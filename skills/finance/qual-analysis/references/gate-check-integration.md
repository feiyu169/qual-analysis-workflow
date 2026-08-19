# Gate Check Integration Pattern for qual-analysis

## Context
When integrating automated quality gates (Gate Checks) into the qual-analysis workflow, follow this pattern.

## Integration Point

```
qual-analysis Step 4 (审计修复) → [Gate Check] → HeavySkill审查
```

**Why here**: Gate Checks verify structural integrity and calculation hygiene BEFORE semantic review. This prevents wasting HeavySkill tokens on reports with fundamental data issues.

## Two-Layer Gate Design

### Gate 1: Structural Integrity (结构完整性)
- `_year_labels` exists and aligns with data arrays
- Key financial fields present (market-specific: HK/US/CN)
- Chapters are non-Placeholder (content > 200 bytes)
- Audit JSON has required fields

### Gate 2: Calculation Hygiene (计算卫生)
- DCF parameters non-empty
- Array lengths match
- Quantity-level sanity (WARN only, not blocking)

## Exception Grading

| Level | Behavior | Examples |
|-------|----------|----------|
| FATAL | Hard block, cannot proceed | `_year_labels` missing, key chapter empty |
| ERROR | Block but retryable | DCF params missing, array mismatch |
| WARN | Flag but continue | WACC outside 6%-18%, FCF/OCF unusual |

## Output Format

```json
{
  "gate_check_report": {
    "timestamp": "...",
    "ticker": "...",
    "structural_integrity": {"all_passed": true/false, "checks": [...]},
    "calculation_hygiene": {"all_passed": true/false, "checks": [...]},
    "overall_verdict": "PASS/FAIL",
    "warnings": [],
    "critical_issues": []
  }
}
```

## Integration with P4 Rule

Gate Check reports are the **automated executor** of P4 (execution logs must be based on evidence):
- Auto-inject into P4 evidence chain
- Include data fingerprint and timestamp
- Human override requires written justification

## Configuration

Gate Check thresholds and field lists should be externalized to YAML config:
- `~/.hermes/config/gate_check_config.yaml`
- Market-specific field mappings (HK/US/CN)
- Threshold ranges (WACC, FCF/OCF) as WARN, not blocking

## References

- `references/gate-check-design-patterns.md` — Full design patterns and threshold anti-patterns
- `references/financial-technical-review-pattern.md` — How to use HeavySkill to review Gate Check designs
