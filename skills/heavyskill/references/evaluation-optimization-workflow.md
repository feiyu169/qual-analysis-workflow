# HeavySkill Evaluation & Optimization Workflow

## Overview

Systematic workflow for evaluating HeavySkill's review quality and optimizing its performance through rule-based post-processing.

## Problem Statement

HeavySkill (LLM-based multi-trajectory reviewer) has inherent biases:
- **Conclusion bias**: LLM tends to say "PASS" even when significant issues exist
- **Discovery gaps**: Some domains (security, architecture) have lower discovery rates
- **Inconsistent grading**: Same proposal may get different conclusions across runs

## Solution: Rule-Based Post-Processing

Add a deterministic `ConclusionValidator` that overrides LLM verdicts based on extracted issues.

### Architecture

```
HeavySkill Output (trajectories)
    ↓
ChecklistResultParser (extract issues from text)
    ↓
ConclusionValidator (4 rules)
    ├── P0 Veto (any P0 → REJECT)
    ├── Threshold Rule (P1≥3 → REJECT)
    ├── Weighted Score (score≥15 → REJECT)
    └── Domain Coverage (coverage<60% → REJECT)
    ↓
Enhanced Verdict (override LLM if needed)
```

### Key Design Decisions

1. **Deterministic rules override LLM** — Rules are applied AFTER LLM produces verdict
2. **Shadow mode for safe rollout** — Record corrections without applying them
3. **Confidence-based filtering** — Low-confidence P0 issues get downgraded to P1
4. **Fallback to LLM on error** — If rule engine fails, use original LLM verdict

## Evaluation Methodology

### Test Case Design

Each test case has **intentionally missing issues** (5 per case):
- Create realistic but flawed technical proposals
- Document expected missing issues (ground truth)
- Cover multiple domains: security, architecture, performance, API, database, deployment

### Metrics

| Metric | Definition | Target |
|--------|-----------|--------|
| Discovery Rate | % of missing issues found by HeavySkill | ≥80% |
| Conclusion Accuracy | % of defective proposals correctly judged as REJECT | ≥95% |
| Rule Override Rate | % of cases where rule engine overrides LLM | Track only |

### 7-Case Evaluation Protocol

Run 7 test cases to get statistical significance:
1. Technical proposal review
2. Code architecture review
3. Security vulnerability review
4. Performance bottleneck review
5. API design review
6. Database design review
7. Deployment architecture review

## Optimization Loop

```
V1 (Initial) → Run 7 cases → Collect metrics → Identify patterns
    ↓
V2 (Optimize) → Add rule engine → Re-run 7 cases → Compare metrics
    ↓
V3 (Validate) → Expert review → HeavySkill final review → Deploy
```

## Verified Results (2026-06-20)

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Conclusion Accuracy | 14% | 100% | +86% |
| Discovery Rate | 74% | 80% | +6% |

## Pitfalls

### P1: Discovery rate ≠ Conclusion accuracy
- Discovery rate: "did we find the issues?"
- Conclusion accuracy: "did we give the right verdict?"
- A reviewer can find issues but still say "PASS" (common LLM bias)

### P2: Test cases must have known ground truth
- Without ground truth, you can't measure accuracy
- Each test case needs documented "expected missing issues"

### P3: Rule engine must be deterministic
- Same input → same output (no randomness)
- Rules applied AFTER LLM, not instead of LLM
- Shadow mode for safe rollout

### P4: Don't overfit to test cases
- 7 cases is minimum for statistical significance
- Need both positive (should PASS) and negative (should REJECT) cases
- Current evaluation only has negative cases (limitation)

## Integration with HeavySkill Pipeline

```python
# Enhanced HeavySkill usage
cd ~/.hermes/skills/heavyskill-optimize
python3 heavyskill_enhanced.py \
  --run-heavyskill \
  --query "审查方案" \
  --file /tmp/proposal.md \
  --output /tmp/enhanced.json \
  --report
```

## Code Location

```
~/.hermes/skills/heavyskill-optimize/
├── src/
│   ├── models.py          # Severity, Verdict, Issue, ValidationResult
│   ├── validator.py       # ConclusionValidator (4 rules)
│   ├── parser.py          # ChecklistResultParser (Markdown/JSON/text)
│   ├── config.py          # YAML config loader + validator
│   └── integration.py     # integrate_with_heavyskill()
├── tests/
│   └── test_validator.py  # 16 unit tests
├── heavyskill_enhanced.py # CLI integration script
└── batch_evaluation.py    # 7-case batch evaluation
```
