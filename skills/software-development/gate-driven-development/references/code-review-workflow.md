# Code Review + Fix Workflow

## Process (verified 2026-07-10)

### Phase 1: Expert Review
1. Delegate to expert subagent with specific files + review dimensions (correctness, security, reliability, architecture, maintainability)
2. Expert outputs P0/P1/P2 issues with file, line number, description, fix suggestion
3. **Self-evaluate first** before reading expert findings — compare your assessment with theirs

### Phase 2: Respond + Fix
4. Respond to EACH finding (accept / partial accept / reject with justification)
5. Fix P0 immediately, then P1, then P2
6. Run tests after each batch of fixes
7. Update tests when behavior changes (e.g., NotImplementedError → VerificationResult)

### Phase 3: Re-review
8. Re-delegate to expert for verification
9. Expert finds NEW issues missed in round 1 (expected — fixes expose deeper problems)
10. Repeat Phase 2

### Phase 4: HeavySkill Final Review
11. Use HeavySkill K=8 for multi-trajectory final review
12. HeavySkill converges on score — use as quality gate
13. Residual issues below threshold can be deferred

## Pitfalls
- Tests passing does NOT mean bugs are fixed — tests may not cover the bug scenario
- Each fix round may introduce new issues (variable rename breaks tests, behavior change breaks assertions)
- Always check test failures after fixes — update tests to match new behavior
- Expert findings and HeavySkill findings are complementary — use both
- When fixing _verify_criteria from always-True to real logic, test fixtures need VerificationEngine injection
- When adding force parameter to reset_gate, both StateMachine and GateManager need the parameter
- GateStatus naming conflict between gate_types.py and state_machine.py — rename to GateExecutionStatus

## Score Progression Pattern
- Round 1 (expert): typically finds 30+ issues, score ~50
- Round 2 (re-review): finds 10-15 NEW issues exposed by fixes, score ~72
- Round 3 (HeavySkill K=8): finds 10-15 more, score ~85-90
- Final: residual P2 issues deferred, score ~90

## Testing Quality Root Causes (verified 2026-07-10)

Why tests don't catch bugs that expert reviews find:

| Root Cause | Description | Fix |
|------------|-------------|-----|
| Happy path only | Tests check "function runs" not "function correct" | Add semantic assertions |
| Weak assertions | `assert result` not `assert result == expected` | Require 2+ verification dimensions |
| Simple test data | Clean fixtures don't trigger edge cases | Add TestDataFactory with boundary data |
| No integration tests | Unit passes but module interaction fails | Add cross-module tests |
| No side-effect verification | Only check return values | Verify DB, logs, state changes |

### Assertion Density Target
- Minimum: 2 independent verification dimensions per test
- Dimensions: return value, state change, DB persistence, log output, error handling
- Average target: 3+ assertions per test (industry standard)

### Test Quality Metrics
| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Assertion density | 1.8/test | 3.0+ | Manual review |
| Boundary coverage | 0% | 30%+ | Count tests with edge keywords |
| Integration ratio | 0% | 20%+ | `pytest -m integration --collect-only` |
| Mutation kill rate | N/A | 80%+ | `mutmut run` |

## Technical Plan Review with HeavySkill (verified 2026-07-10)

When reviewing technical plans:
1. Inline ALL relevant code into HeavySkill query (subagents can't read local files)
2. Use K=8 for standard review, K=4 for quick check
3. Include: plan text + current code + test code
4. HeavySkill finds issues human reviewers miss (concurrency, mapping chains, tool names)
5. Run HeavySkill twice: once on initial plan, once on revised plan to verify improvements
6. Expected improvement: 78 → 85 after addressing findings
