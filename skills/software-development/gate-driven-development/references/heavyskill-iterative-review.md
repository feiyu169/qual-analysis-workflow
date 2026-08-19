# HeavySkill Iterative Review Workflow

## Pattern: Document → Review → Fix → Re-review (3-5 rounds expected)

When using HeavySkill K=8 for technical document review, expect iterative cycles:

### Round Structure
1. **v1**: Initial document with all sections
2. **HeavySkill review**: Finds implementation errors, missing details
3. **v2**: Fix reported issues
4. **HeavySkill review**: Finds that fixes didn't apply correctly (common!)
5. **v3**: Re-apply fixes with correct syntax
6. **HeavySkill review**: May find new issues or verify fixes
7. **Continue until convergence** (score stabilizes)

### Common Failure Modes

1. **Fix didn't apply**: HeavySkill reports same issue in v2 as v1
   - Cause: String mismatch in patch/replace operations
   - Fix: Verify actual file content after patch, use `grep` to confirm

2. **Score decreases**: v2 scores lower than v1
   - Cause: Fixes introduced new errors, or original fixes were incomplete
   - Fix: Read full deliberation, check all 4 trajectories

3. **False positives**: HeavySkill reports issues that don't exist
   - Cause: Sub-agents can't read local files, analyze based on inline content only
   - Fix: Verify with actual tool execution, don't blindly accept findings

### Best Practices

1. **Inline ALL relevant content** in the HeavySkill query (sub-agents can't read files)
2. **Use `--include-file`** for documents > 5K chars
3. **Check all 4 trajectories** in deliberation, not just the final answer
4. **Verify fixes with `grep`** before re-submitting to HeavySkill
5. **Expect 3-5 rounds** for complex technical documents
6. **Score convergence** at 75-85/100 is typical for production-ready documents

### Example Score Progression
```
v1: 78/100 (initial)
v2: 70/100 (fixes didn't apply, new errors found)
v3: 68/100 (more issues discovered)
v4: 35/100 (cascading failures from bad patches)
v5: 73/100 (fixes finally applied correctly)
v6: 75/100 (converged, ready for implementation)
```

### Key Insight
HeavySkill's value is in **finding implementation-level errors** that design-level review misses. The iterative process catches:
- Syntax errors in code examples
- Incorrect API usage (e.g., `pytestmark = seed(42)` vs `@settings(seed=42)`)
- Data structure mismatches (e.g., coverage.py JSON format)
- Missing integration points (e.g., CI workflow not defined)
