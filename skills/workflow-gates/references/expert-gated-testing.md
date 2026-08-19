# Expert-Gated Test Execution Workflow (Verified 2026-06-17)

## Pattern
Execute tests sequentially, with each test reviewed by an expert (human or AI) before proceeding to the next. This ensures quality and catches issues early.

## Workflow

```
For each test in test_plan:
    1. Prepare test data (create prerequisites)
    2. Execute test steps
    3. Record results (test_record JSON)
    4. Submit to expert for review
    5. If expert approves → proceed to next test
    6. If expert rejects → fix issue and re-test
    7. Log all results for final report
```

## Implementation

### Test Record Format
```python
test_record = {
    "test_id": "TC01",
    "test_name": "描述",
    "priority": "P0",
    "test_time": "2026-06-17 01:00:00",
    "test_data": { ... },
    "test_steps": ["步骤1", "步骤2"],
    "expected_result": "...",
    "actual_result": { ... },
    "test_result": "PASS" | "FAIL" | "PASS_WITH_WARNING" | "ERROR"
}
```

### Expert Review Prompt
```
请审查此测试结果：
- 测试编号: TCXX
- 测试项: XXX
- 测试结果: PASS/FAIL
- 验证点: ✅/❌ 列表
- 发现的问题: ...

审查结论：通过/不通过/有条件通过
```

### Result Statuses
- `PASS` — all verifications passed
- `PASS_WITH_WARNING` — functional but has improvement suggestions
- `FAIL` — verification failed
- `ERROR` — execution error

## Benefits
- Catches issues immediately (not at the end)
- Each test builds on verified previous state
- Expert knowledge applied incrementally
- Clear audit trail for each test

## Pitfalls

### P0: Test data dependencies between tests (Verified 2026-06-17)

**Symptom**: Test N fails because test N-1 changed the state of shared test data.

**Fix**: 
- Create fresh test data for each test when possible
- Or use a test data factory that resets state
- Document which tests depend on which

### P0: API parameter names differ from documentation (Verified 2026-06-17)

**Symptom**: API returns `400 参数验证失败` with `{"field": ["Unknown field."]}`

**Fix**: Always check the marshmallow/wtforms schema before calling APIs. See `flask-nginx-deploy` skill for detailed pattern.

### P1: Expert review adds latency (Verified 2026-06-17)

**Observation**: Each test + review cycle takes 1-2 minutes. For 20+ tests, total time is 30-60 minutes.

**Mitigation**: 
- Batch related tests (e.g., all permission tests) for single review
- Only gate critical tests (P0) with expert review
- P1/P2 tests can be batch-reviewed at the end
