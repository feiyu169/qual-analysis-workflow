# Gate-Driven Development — Pitfalls & Corrections

## Pitfall: Scope Deflection During Review

**Symptom**: When a HeavySkill or expert review asks for more detail (e.g., "provide complete interface signatures", "define error handling protocol"), the agent responds with "this is beyond the scope of the technical document."

**User's explicit correction**: "超出技术方案文档的范围不是你应该考虑的，你审查的目的是看清楚功能能不能做到dayu-agent的功能，如果不行，那就修改，如果可以那就不改，给出你的具体信息，陷入无限循环是为什么"

**Root cause**: The agent confused "technical document scope" with "functional capability verification." The review's purpose is binary: CAN the solution achieve the reference implementation's functionality? This requires full detail, not scope debates.

**Fix**: 
1. When a review asks for more detail, extract it from the reference implementation's source code
2. If information is genuinely unknown, state what is unknown — don't refuse to look
3. Never say "beyond scope" — the user decides scope, not the agent
4. Focus on the binary question: does this work or not?

## Pitfall: Treating Review as One-Shot

**Symptom**: Running HeavySkill once, getting findings, and either:
- Moving on without fixing findings
- Asking user "should I fix these?" instead of fixing them
- Treating "原则通过" (principally approved) as "可以开始" (ready to start)

**Fix**: Each review output is a mandatory fix checklist. Fix ALL items, then re-review. This is expected to take 2-4 iterations for complex proposals.

## Pitfall: Infinite Loop in Review

**Symptom**: Review cycles that don't converge because:
- Each review generates new requirements not in the original spec
- The agent adds detail, but the review finds more gaps
- The user asks "why are we looping?"

**Root cause**: The agent is not reading the review output carefully enough. Each iteration should address ALL findings from the previous review, not just some.

**Fix**:
1. After each review, extract ALL findings into a numbered list
2. Address EVERY item in the next spec version
3. Don't add new features — only fill gaps identified by the review
4. If a finding is genuinely unclear, ask the user — don't guess and loop

## Correct Review Workflow

```
1. Write technical spec (v1)
2. Run HeavySkill review with full feature checklist
3. Review output → numbered list of findings
4. Fix ALL findings → spec v2
5. Run HeavySkill review on v2
6. If pass → proceed to implementation
7. If fail → go to step 3
8. Maximum 4 iterations before escalating to user
```

## Escalation After 4 Iterations

If after 4 iterations the review still has findings:
1. Summarize what has been fixed
2. List remaining findings
3. Ask user: "Continue fixing or start implementation?"
4. The user may decide that remaining findings are acceptable
