# Test-to-Fix Pipeline with Expert Review

## Overview

A complete workflow for fixing issues found during functional testing, with expert review gates at each stage. Demonstrated in the exception-system project (2026-06-17).

## Pipeline Stages

```
Functional Testing (per-test expert review)
    ↓
Issue Aggregation & Prioritization
    ↓
HeavySkill Review of Technical Fix Plan (6 trajectories)
    ↓
Plan Revision Based on Review Findings
    ↓
HGF-Gated Implementation (per-phase expert review)
    ↓
Regression Testing
```

## Stage 1: Functional Testing with Per-Test Expert Review

### Pattern

For each test case:
1. Execute the test (API call, UI interaction, etc.)
2. Record actual results
3. Submit to expert review (simulated or delegate_task)
4. Expert must approve before proceeding to next test
5. Document both test result AND expert verdict

### Implementation

```python
# Per-test expert review template
def review_test(test_record):
    """Submit test result to expert for review"""
    
    review = f"""
    Test: {test_record['test_id']} - {test_record['test_name']}
    Priority: {test_record['priority']}
    Result: {test_record['test_result']}
    
    Actual Results:
    {json.dumps(test_record['actual_result'], indent=2)}
    
    Expert Review Points:
    1. Test execution quality
    2. Result validation completeness
    3. Issues found (if any)
    4. Recommendation: PASS / PASS_WITH_WARNING / FAIL
    """
    
    return review
```

### Expert Review Template

```
Expert Review: {test_id}

审查结论: ✅ 通过 / ⚠️ 通过（有改进建议）/ ❌ 不通过

审查意见:
1. 测试执行规范性: ✅/⚠️/❌
2. 测试结果: ✅/⚠️/❌
3. 发现的问题: [list]
4. 建议: [list]

审查结论: [总结]
```

### Test Result Categories

| Category | Meaning | Action |
|----------|---------|--------|
| PASS | All verifications passed | Continue to next test |
| PASS_WITH_WARNING | Core function works, but issue found | Document issue, continue |
| FAIL | Core function broken | Stop, fix immediately |
| ERROR | Test execution failed | Debug test, retry |

## Stage 2: Issue Aggregation

After all tests complete, aggregate findings:

```markdown
## Issues Found

| Priority | Issue | Test Cases | Impact |
|----------|-------|------------|--------|
| 🔴 P0 | Feature X missing | TC73-77 | High |
| 🟡 P1 | API Y missing | TC78 | Medium |
| 🟡 P1 | Security Z weak | TC81 | Medium |
```

## Stage 3: HeavySkill Review of Technical Fix Plan

**Key learning**: Before implementing fixes, submit the technical plan to HeavySkill for multi-trajectory review. This catches design errors BEFORE implementation.

### Pattern

1. Write technical fix plan to file
2. Run HeavySkill with 6 trajectories
3. Process review findings
4. Revise plan based on findings
5. Only then start implementation

### Command

```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "请审查这个技术方案，从完整性、可行性、优先级合理性、工作量估算、实施风险、改进建议 6 个维度进行深度审查" \
  --include-file /tmp/tech-plan.md \
  --reason_k 6 --summary_k 3 --language cn \
  --output /tmp/heavyskill-review-result.json \
  --quiet
```

### What HeavySkill Catches (from this session)

| Finding | Impact |
|---------|--------|
| "审核结果通知遗漏" | P0 feature incomplete |
| "XSS存储转义方案错误" | Would corrupt data |
| "APScheduler多实例重复" | Would cause notification storm |
| "防重复提交设计空洞" | Would not actually prevent duplicates |
| "操作日志安全风险" | Would leak sensitive info |
| "工作量估算偏乐观" | 6 days → 11.5 days |

## Stage 4: HGF-Gated Implementation

Implement fixes following HGF gates, with expert review between phases.

### Phase Structure

```
Stage 1: Critical fixes (P0)
  Gate 1.1: [component] → verify → expert review
  Gate 1.2: [component] → verify → expert review

Stage 2: Feature completion (P1)
  Gate 2.1: [component] → verify → expert review
  Gate 2.2: [component] → verify → expert review

Stage 3: Security hardening (P1)
  Gate 3.1: [component] → verify → expert review
  Gate 3.2: [component] → verify → expert review
```

### Gate Definition Template

```
Gate N.M: [Component Name]
准入条件: Previous gate passed
准出条件:
  1. [Specific measurable condition]
  2. [Specific measurable condition]
  3. [Specific measurable condition]
验证方法: [How to verify - must be REAL execution, not file checks]
```

## Pitfalls

### P1: Skipping expert review between tests

When running many tests (30+), there's temptation to skip expert review for "simple" tests. Each test review catches issues that compound:
- TC43 review caught that `reject_reason` field name was wrong
- TC46 review caught that `new_planned_finish_time` parameter wasn't supported
- These would have cascaded to later tests

### P2: Implementing before HeavySkill review

The original technical plan had 5 critical issues that HeavySkill caught:
- Would have corrupted data (XSS storage)
- Would have caused notification storms (APScheduler)
- Would have missed features (审核结果通知)

**Rule**: Always HeavySkill review the fix plan before implementation.

### P3: Not revising plan after HeavySkill review

HeavySkill review found the original 6-day estimate was too optimistic (actual: 11.5 days). Implementing without revision would have caused schedule overrun.

### P4: Treating PASS_WITH_WARNING as PASS

Tests that pass with warnings (e.g., "防重复提交未实现") indicate real issues that need tracking. Don't lose them in the success metrics.

## Metrics from This Session

| Metric | Value |
|--------|-------|
| Total tests | 33 |
| Test rounds | 5 |
| Per-test expert reviews | 33 |
| HeavySkill reviews | 2 (plan + supplement plan) |
| Issues found | 7 |
| HeavySkill findings | 6 critical |
| Original estimate | 6 days |
| Revised estimate | 11.5 days |

## When to Use This Pipeline

- Functional testing of a complete system (10+ test cases)
- Post-deployment verification
- Security audit with fix implementation
- Any testing where issues require code changes
- When user requests "第三方专家审查" for each test
