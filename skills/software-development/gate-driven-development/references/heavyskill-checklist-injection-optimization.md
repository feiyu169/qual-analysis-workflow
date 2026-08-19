# HeavySkill Checklist Injection Optimization

## Problem

HeavySkill (multi-trajectory reasoning engine) had weak discovery rates in specific domains:
- Technical proposal review: 20%
- Architecture review: 40%
- Security review: 40%

## Solution: Single-Stage Checklist Injection

Inject domain-specific checklists into the HeavySkill query BEFORE running the review.

### Architecture

```
User Request → Domain Classifier → Checklist Manager → Query Enhancer → HeavySkill → Enhanced Output
```

### Components

1. **DomainClassifier** — Identifies domains (security/architecture/performance/database/api/deployment) via keyword matching
2. **ChecklistManager** — Manages YAML checklists per domain, merges when multiple domains detected
3. **QueryEnhancer** — Injects checklist into HeavySkill query as "必须检查" items

### Results (2026-06-20, 7 cases)

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Average discovery rate | 71% | 86% | **+15%** |
| Architecture review | 40% | 100% | **+60%** |
| Security review | 40% | 100% | **+60%** |
| API design review | 100% | 80% | **-20%** |

### Code Location

```
~/.hermes/skills/heavyskill-optimize/
├── src/enhancer.py              # DomainClassifier + ChecklistManager + QueryEnhancer
├── checklists/security.yaml     # 10 items (S-01 to S-10)
├── checklists/architecture.yaml # 10 items (A-01 to A-10)
├── checklists/performance.yaml  # 10 items (P-01 to P-10)
└── heavyskill_enhanced_v2.py    # CLI entry point
```

## Failed Approach: Two-Stage Injection

Tested but rolled back. Average discovery rate dropped to 60%.

### Why it failed
- Stage2 checklist coverage was extremely low (1/30, 1/40 items matched)
- Keyword matching logic was too strict
- Stage2 results not effectively integrated into final output

### Root cause (expert analysis)
1. **Attention dilution**: Checklist expanded query from 13 chars to 710+ chars (×55)
2. **Exploration → Verification mode**: Checklist switched model from active exploration to passive checklist-following
3. **Trajectory convergence**: All K trajectories became similar (all followed checklist)
4. **Shallow matching**: Model found any mention of checklist keyword → marked as "covered" without deep analysis

## Pitfalls

1. **Checklist length matters**: 10 items per domain is too many. Keep to 3-5 priority items.
2. **"是否有X" is weak**: Use "验证X是否满足Y条件" instead — forces deeper analysis.
3. **API review is fragile**: Checklist injection can REDUCE discovery rate for API design reviews (100% → 80%).
4. **Domain classifier accuracy**: 2+ keyword matches to trigger a domain. May miss edge cases.
5. **Single evaluation is noisy**: Run 5-10 times for statistical significance.
