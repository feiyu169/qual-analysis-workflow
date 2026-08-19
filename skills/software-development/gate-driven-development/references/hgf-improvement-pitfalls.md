# HGF 流程改进 — Pitfalls

## P1: Gate 0 Pre-Review Missing (Verified 2026-07-01)

**Symptom**: P0 issues found in Gate 1 and Gate 5+6 should have been caught in design phase.

**Fix**: Implement Gate 0 pre-review with checklist:
- A-01: Module interface clarity
- A-02: Data flow completeness
- A-03: Error handling completeness
- T-01: Testing strategy clarity

## P2: Evaluation Standards Not Unified (Verified 2026-07-01)

**Symptom**: 72-point conditional pass vs 52-point reject, threshold unclear.

**Fix**: Unified thresholds:
- Direct pass: ≥80 score, P0=0, HIGH=0
- Conditional pass: 60-79 score, P0=0, HIGH≤2
- Reject: <60 score or P0>0

## P3: Inter-Gate Dependency Checking Missing (Verified 2026-07-01)

**Symptom**: Cross-Gate issues遗漏.

**Fix**: GateDependencyTracker for recording and checking prerequisites.

## P4: Automated Checkpoints Missing (Verified 2026-07-01)

**Symptom**: Manual evaluation is subjective.

**Fix**: GateAutoChecker for syntax/import/None checks.

## P5: Regression Testing Missing (Verified 2026-07-01)

**Symptom**: Fixes may introduce new problems.

**Fix**: GateRegressionTester for running tests and verifying fixes.

## Implementation Files

All 5 modules implemented in `~/.hermes/tools/finance/quality/`:
- gate0_reviewer.py
- gate_evaluator.py
- gate_dependency.py
- gate_auto_check.py
- gate_regression.py

## HeavySkill Review

8/8 trajectories passed. Expected improvement: first-pass rate from 67% to 85%+.
