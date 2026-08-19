# HeavySkill Optimization — HGF Execution Record

## Overview

Complete HGF execution for optimizing HeavySkill's conclusion accuracy and discovery rate.

## Phases Executed

### Phase 0: Infrastructure (7 Gates)
- G0-1: Requirements analysis
- G0-2: P0-5 fix (shadow mode exception protection)
- G0-3: ConclusionValidator implementation
- G0-4: ChecklistResultParser implementation
- G0-5: Config system with validation
- G0-6: 16 unit tests (all passing)
- G0-7: Integration test

### Phase 1: Expert Review (2 Gates)
- G1-1: Programming expert — conditional pass (2 P0, 4 P1, 4 P2)
- G1-2: Architecture expert — conditional pass (3 P2, 5 P3)

### Phase 2: HeavySkill Final Review (1 Gate)
- G2-1: HeavySkill review — conditional pass (all issues fixed)

### Phase 3: Report (1 Gate)
- G3-1: Final report generation

## Key Fixes Made (V1 → V3.1)

| Version | Issue | Fix |
|---------|-------|-----|
| V3 | P0-1: No false-positive handling | Confidence threshold + human review queue + shadow mode |
| V3 | P0-2: No fallback mechanism | Global switch + exception fallback |
| V3 | P0-3: Severity enum error | `Severity.from_str()` with fuzzy matching |
| V3 | P0-4: Disconnected modules | ChecklistResultParser bridge layer |
| V3.1 | P0-5: Shadow mode crash | try/except in shadow validation |
| V3.1 | min_confidence unused | Integrated into P0 veto logic |
| V3.1 | Bare except | Changed to specific exception types |
| V3.1 | Shallow copy | Changed to `copy.deepcopy()` |
| V3.1 | Issues inconsistency | Return `filtered_issues` not original |

## Checklist Injection Optimization

After rule engine implementation, added checklist injection to improve discovery rates:

```
Phase 0: Create enhancer module (DomainClassifier + ChecklistManager + QueryEnhancer)
Phase 1: Run 7 eval cases with checklist injection
Phase 2: Expert review of results
Phase 3: HeavySkill final review
```

**Results**: Average discovery rate 71% → 86% (+15%)

## Pitfalls Discovered

1. **Shadow mode must catch ALL exceptions** — otherwise crashes the pipeline
2. **Empty issues list causes ZeroDivisionError** in domain coverage calculation
3. **`_infer_llm_verdict` keyword order matters** — "附意见通过" contains "通过"
4. **Checklist injection can interfere** with already-good reviews (100% → 80%)
5. **Technical proposals need cross-domain checklists** — single-domain misses cross-cutting concerns
6. **Shallow copy modifies original data** — always use `copy.deepcopy()`
7. **Config field defined but never used** — verify all config fields are actually consumed in logic

## Files

```
~/.hermes/skills/heavyskill-optimize/
├── src/
│   ├── models.py          # Severity, Verdict, Issue, RuleResult, ValidationResult
│   ├── validator.py       # ConclusionValidator (4-rule engine)
│   ├── parser.py          # ChecklistResultParser (Markdown/JSON/plaintext)
│   ├── config.py          # YAML config loader + validator
│   ├── enhancer.py        # DomainClassifier + ChecklistManager + QueryEnhancer
│   ├── integration.py     # integrate_with_heavyskill()
│   └── utils.py           # infer_llm_verdict(), deduplicate_issues()
├── checklists/
│   ├── security.yaml      # 10 security checks
│   ├── architecture.yaml  # 10 architecture checks
│   └── performance.yaml   # 10 performance checks
├── heavyskill_enhanced.py   # V1 integration script
├── heavyskill_enhanced_v2.py # V2 with checklist injection
└── tests/
    └── test_validator.py  # 16 unit tests

~/.hermes/evals/
├── cases/case-004~010/    # 7 evaluation cases
├── scripts/
│   ├── run_heavyskill_7case_eval.py
│   └── run_heavyskill_enhanced_v2_eval.py
└── scores/
    ├── heavyskill-7case-eval-results.json
    └── heavyskill-enhanced-v2-eval-results.json
```
