# Iterative HeavySkill Review Pattern (V1→V5)

## Pattern

For complex architectural proposals, iterate through multiple HeavySkill reviews:

```
V1 (Initial Draft) → HeavySkill → 6 issues found → Fix
V2 (Revised) → HeavySkill → 5 issues found → Fix  
V3 (Refined) → HeavySkill → 3 issues found → Fix
V4 (Polished) → HeavySkill → 2 issues found → Fix
V5 (Final) → HeavySkill → "通过" → Implement
```

## Step-by-Step

### 1. Write proposal to file
```bash
cat > /tmp/proposal-v1.md << 'EOF'
# Proposal Title
## Core Principles
...
EOF
```

### 2. Run HeavySkill review
```bash
cd ~/.hermes/skills/heavyskill
python3 scripts/run_heavyskill.py \
  --query "请审查方案，从6个维度：完整性/不可绕过性/可行性/集成性/可扩展性/风险控制" \
  --include-file /tmp/proposal-v1.md \
  --reason_k 6 --summary_k 3 --language cn \
  --output /tmp/review-v1.json
```

### 3. Parse review results
```python
import json
with open('/tmp/review-v1.json') as f:
    data = json.load(f)
trajectories = data['reasoning']['trajectories']
# trajectories[0..2] contain full analysis
# Extract P0/P1/P2 improvement items
```

### 4. Revise and re-run
- Fix ALL P0 issues before re-running
- Fix P1 issues if feasible
- Document what changed between versions

### 5. Convergence signals
- Trajectories give consistent judgments
- Consensus Answer stabilizes
- No new P0 issues found

## Example: Workflow V2→V5

| Version | Issues Found | Key Fixes |
|---------|-------------|-----------|
| V2 | 6 | Risk assessment mismatch, missing non-code flows |
| V3 | 5 | Safety guardrail, mixed change types |
| V4 | 3 | Emergency channel, IAC governance |
| V5 | 0 | All reviews passed |

## Pitfalls

1. **Don't stop after V1**: First review typically catches 60-80% of issues
2. **Don't just relabel**: Actually fix the issues between iterations
3. **Track deltas**: Document what changed V2→V3→V4→V5
4. **Stop when passed**: Don't over-iterate once reviews pass

## Critical Lesson: Described vs Implemented Fixes (verified 2026-07-10)

HeavySkill K=8 distinguishes between:
- **Described fix**: "改用 functions 字段" (but code still uses file-level check)
- **Implemented fix**: Actual code that works correctly

When fixes are only described, HeavySkill scores DROP (78 → 70 → 68 → 35) because it detects the implementation doesn't match the claim.

**Rule**: Always provide working code in the document, not pseudocode or descriptions. HeavySkill will verify the code actually does what you claim.

## Score Progression Pattern

Typical pattern for technical document reviews:
```
v1: 78 (initial, good direction)
v2: 70 (fixes found to be superficial - score drops!)
v3: 68 (more superficial fixes detected)
v4: 35 (fatal: patches didn't apply correctly)
v5: 73 (real fixes finally applied)
```

The non-monotonic progression is a SIGNAL that fixes need to be verified before re-submitting.
