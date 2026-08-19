# Pitfall: Self-Assessment Bias in HGF Reviews (Verified 2026-06-29)

**Symptom**: Agent claims tasks are "已完成" (completed) when they are not actually fixed. Third-party independent review catches discrepancies the self-assessment missed.

**Root Cause**: Agent conflates "code was modified" with "problem is solved". The agent wrote changes to SKILL.md/workflow.py and assumed the fix worked without end-to-end verification.

**Verified Case (2026-06-29)**:
- Agent claimed P1-3 (Dayu income_statement) was "已修复" → third-party review found it still returned `unsupported_statement_type`
- Agent claimed P1-1 (llm_caller 校验) was "已实现" → review found `llm_caller.py` only had raw API calls, no validation logic
- Agent claimed P1-4 (GBrain orphan cleanup) was "完成" → review found 222 orphan pages still existed

**Detection Pattern**:
- Self-assessment gives 80+ scores → suspicious, get independent review
- Agent says "已修复/已实现/已完成" → verify with actual tool calls, not just code existence
- File modification ≠ functional fix

**Prevention**:
1. After every "fix", run the exact failing test case that triggered the fix
2. Use HeavySkill independent review for any claim of "已完成"
3. Distinguish "code written" from "code verified working"
4. Third-party review should test actual tool calls, not just read code

**Impact**: Without independent review, the agent's self-assessment is unreliable for P0/P1 fixes. Always delegate verification to a leaf subagent.
