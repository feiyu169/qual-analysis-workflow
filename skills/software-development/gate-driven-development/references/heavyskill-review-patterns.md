# HeavySkill Review Cycle Patterns (Verified 2026-07-10)

## Pattern: Iterative Review Convergence

When using HeavySkill K=8 for technical document review, expect 2-3 rounds:

| Round | Typical Score | Focus |
|-------|---------------|-------|
| v1 | 70-78 | Direction correct, implementation gaps |
| v2 | 78-85 | Implementation details, edge cases |
| v3 | 85-92 | Polish, robustness, CI integration |

**Key insight:** Score DECREASES between rounds when fixes introduce new errors.
- v1=78 → v2=70 means the "fixes" had implementation bugs
- This is NORMAL — HeavySkill catches what you miss

## Pitfall: Description vs Implementation Gap

HeavySkill reviewers specifically look for:
1. **Pseudocode disguised as code** — "使用 @settings(seed=42)" without actual decorator
2. **Scripts that won't work** — wrong API, wrong paths, missing imports
3. **Configuration that's incorrect** — wrong directory, wrong format
4. **Missing integration** — defined a whitelist but didn't wire it into CI

**Defense:** Every technical claim must have executable code. Run the code mentally before writing it.

## Pitfall: Coverage Measurement Must Be Precise

HeavySkill will catch:
- File-level coverage claimed as method-level
- "30% coverage" without defining what 100% means
- Coverage scripts that count wrong things

**Defense:** Define the denominator explicitly. Use `ast` module to extract actual method counts.

## Pitfall: Tool Configuration Cross-References

HeavySkill will catch:
- `tests_dir` pointing to wrong directory
- Missing markers on test classes
- Cache keys that don't include all relevant files

**Defense:** After writing config, mentally trace the execution path. Will the tool find what it needs?

## Review Response Template

When responding to HeavySkill findings:

```
| # | 问题 | 级别 | 回复 |
|---|------|------|------|
| 1 | [issue] | P0/P1/P2 | **接受** / **部分接受** / **不接受** [理由] |
```

**Rule:** Accept rate should be >80%. If you're rejecting >20% of findings, you're probably wrong.

## When to Stop Reviewing

| Condition | Action |
|-----------|--------|
| Score ≥ 85 | Proceed to implementation |
| Score < 85 but all P0 fixed | Proceed with caution |
| Score decreasing between rounds | Stop, re-examine approach |
| 3+ rounds with same issues | Fundamental design problem, redesign |
