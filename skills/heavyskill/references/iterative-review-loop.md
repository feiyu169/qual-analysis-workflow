# Iterative HeavySkill Review Loop Pattern

## Pattern Description

When using HeavySkill for technical proposal review, the workflow is iterative:
1. **Propose** → write technical spec
2. **Review** → run HeavySkill with domain-specific checklist
3. **Analyze gaps** → compare review findings against requirements
4. **Fix** → update spec to address all findings
5. **Re-review** → run HeavySkill again on updated spec
6. **Repeat** until review passes cleanly

## Key Lesson: Review Findings Must Drive Iteration

**Anti-pattern**: Treating review as a one-shot gate. Running HeavySkill once and moving on regardless of findings.

**Correct pattern**: Each HeavySkill review output is a checklist of required fixes. The next spec version MUST address every finding before re-submitting for review.

## Anti-pattern: Scope Deflection

**NEVER tell the user "this is beyond the scope of the technical document" when a review asks for more detail.**

The user explicitly stated: "超出技术方案文档的范围不是你应该考虑的" (scope boundaries are NOT your concern).

When a review asks for more information, the correct response is:
- If the information CAN be determined from source code → extract and add it
- If the information CANNOT be determined → state honestly what is unknown
- NEVER refuse to add information because "it's beyond scope"

The review's purpose is to verify **functional capability** — can the proposed solution achieve what the reference implementation achieves? This is a binary question, not a scope debate.

## Checklist Injection for Technical Reviews

When running HeavySkill for technical review, inject the full reference implementation's feature list as a checklist. This improves discovery rate from 71% to 86%.

Example query structure:
```
审查原则：对照[reference]的功能，一一核对，以满足功能实现为前提，全面审慎，不得隐瞒欺骗。

[reference]功能清单：
1. function_a() -> ReturnType
2. function_b(param) -> ReturnType
...

审查点：
1. 是否实现function_a？
2. 是否实现function_b？
...
```

## Convergence Criteria

A review passes when ALL of the following are true:
- Every function in the reference has a corresponding implementation
- Interface signatures are compatible (exact match or documented simplification)
- Error handling follows the same patterns
- No "undetermined" or "待澄清" items remain in the review output

## Typical Iteration Count

Based on session history:
- Simple proposals: 1-2 iterations
- Complex proposals (multi-module): 3-4 iterations
- The user expects and accepts multiple iterations — this is normal, not failure
