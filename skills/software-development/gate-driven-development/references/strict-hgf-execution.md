# Strict HGF Execution Mode

When the user says "严格按照HGF流程", "不允许跳过", or "有偏差通知我":

## Execution Rules

1. **Phase-by-phase execution**: Define Gate table upfront, execute each Phase sequentially
2. **Deviation notification**: If ANY implementation differs from the technical spec, STOP and notify the user before proceeding. Do not silently adapt.
3. **No deception**: If something doesn't work as designed, report it honestly. Never fabricate results or skip verification.
4. **Gate verification**: Each Phase must have a concrete verification step (py_compile, pytest, import check). Gate must pass before proceeding.
5. **One-at-a-time**: Complete one Phase fully before starting the next. No parallel Phases.

## HeavySkill Review for Technical Documents

When reviewing a technical design document against a reference implementation:

### Query construction
- Include the full feature checklist from the reference (numbered items with line references)
- Include explicit review points (numbered)
- Use the principle: "对照[reference]实现的功能，一一核对，以满足功能实现为前提，全面审慎，不得隐瞒欺骗"

### Known limitation
HeavySkill subagents CANNOT access local filesystem. If HeavySkill returns "cannot access local files":
- Execute the review yourself by reading both files and doing the comparison manually
- Do NOT re-run HeavySkill expecting different results

### Iteration pattern
- v1.0 → HeavySkill finds issues → v1.1 → HeavySkill finds more → v1.2 → ...
- Each iteration should address ALL issues from the previous review
- Stop iterating when HeavySkill says "方案审查通过"
- Typical: 2-3 iterations for complex technical docs

## Deviation Notification Template

When you find a deviation from the spec:

```
⚠️ 偏差通知

问题: [具体问题]
原因: [根本原因]
影响: [对功能的影响]
建议: [修复方案]

等待用户确认后继续。
```
