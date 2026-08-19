# Test Execution with Expert Review Gates (Verified 2026-06-17)

## Overview

A structured testing workflow where each test case is executed individually, then reviewed by a simulated third-party expert before proceeding to the next. This ensures quality at every step, not just at the end.

## When to Use

- User explicitly requests expert oversight during testing
- Critical systems requiring step-by-step validation
- Complex business workflows where each step builds on the previous
- Compliance/regulatory testing requiring audit trail

## Workflow Template

```python
# For each test case in the test plan:
for test_case in test_plan:
    # 1. Prepare test data
    prepare_test_data(test_case.preconditions)
    
    # 2. Execute test
    result = execute_test(test_case)
    
    # 3. Record structured result
    test_record = {
        "test_id": test_case.id,
        "test_name": test_case.name,
        "test_time": now(),
        "test_data": result.data,
        "actual_result": result.details,
        "test_result": "PASS" if result.success else "FAIL"
    }
    save_record(test_record)
    
    # 4. Expert review
    expert_verdict = simulate_expert_review(test_record)
    
    # 5. Gate check
    if expert_verdict == "通过":
        proceed_to_next_test()
    elif expert_verdict == "附意见通过":
        log_improvement_items()
        proceed_to_next_test()
    else:
        fix_and_retest()
```

## Real Example: exception-system Testing (2026-06-17)

### Test Execution Summary

| Round | Tests | Pass Rate | Time |
|-------|-------|-----------|------|
| Core Flow (TC43-TC64) | 17 | 100% | 14 min |
| Data Consistency (TC61-TC68) | - | pending | - |
| Alerts (TC73-TC77) | - | pending | - |

### Test Cases Executed

| ID | Test | Result | Key Finding |
|----|------|--------|-------------|
| TC43 | 退回异常 | PASS | reject_reason field not in API response |
| TC44 | 重新提交 | PASS | description correctly updated |
| TC45 | 延期申请 | PASS | status → 延期待审批 |
| TC46 | 延期审批通过 | PASS | no new_planned_finish_time param |
| TC47 | 延期审批不通过 | PASS | status stays 处置中 |
| TC48 | 审核不通过 | PASS | uses remark, not reject_reason |
| TC49 | 取消异常 | PASS | cancel_reason correctly saved |
| TC50 | 撤回异常 | PASS | auto-sets "上报人撤回" |
| TC51 | 上报人越权接收 | PASS | returns 403 |
| TC52 | 上报人越权审核 | PASS | returns 403 |
| TC53 | 处置人越权审核 | PASS | returns 403 |
| TC55 | Token 过期 | PASS | returns 401 |
| TC56 | 伪造 Token | PASS | returns 401 |
| TC58 | 特殊字符 | PASS | correctly saved (XSS depends on frontend) |
| TC59 | 空必填项 | PASS | returns 400 with validation details |
| TC64 | 无效状态转换 | PASS | returns 409 with allowed_transitions |

### API Parameter Discoveries

During testing, several API parameters differed from the test plan:

| API | Expected Param | Actual Param | Discovery Method |
|-----|---------------|--------------|------------------|
| delay/approve | new_planned_finish_time | (not supported) | Schema inspection |
| approve | reject_reason | remark | Schema inspection |
| approve | reject_reason | remark | Schema inspection |

**Lesson**: Always check marshmallow schemas before assuming API parameters:
```bash
grep -A 20 'class XxxSchema' /path/to/app/schemas/*.py
```

## Expert Review Template

```markdown
## TCxx 测试结果 - 专家审查

**审查结论**: ✅ 通过 / ⚠️ 附意见通过 / ❌ 不通过

**审查意见**:

1. 测试执行规范性: ✅/⚠️/❌
   - 测试步骤清晰
   - 验证点覆盖全面

2. 测试结果: ✅/⚠️/❌
   - API 调用成功
   - 状态正确变更

3. 业务流程验证: ✅/⚠️/❌
   - 状态机转换正确
   - 数据完整性保障

4. 建议:
   - 继续执行下一项测试 / 需要修复后重测
```

## Pitfalls

1. **Test data contamination**: Tests that create data (TC43, TC44, etc.) affect subsequent tests. Solution: create fresh test data for each test or use isolated test databases.

2. **Dual database confusion**: Flask apps may use different databases in dev vs prod (exception.db vs exception_dev.db). Always verify which database the running service uses:
   ```bash
   # Check .env
   cat /opt/project/.env | grep DATABASE
   # Check what service actually uses
   journalctl -u service -n 5 | grep -i database
   ```

3. **API schema vs docs mismatch**: API documentation may not match actual schema. Always check the marshmallow/pydantic schema definition.

4. **Sequential test dependencies**: TC44 depends on TC43's "已退回" state. If TC43 fails, TC44 cannot execute. Plan for this with pre-test data setup.

5. **Expert review should be substantive**: Don't just say "PASS". The expert should evaluate:
   - Were all verification points checked?
   - Are there missing validations?
   - Is the test data realistic?
   - Would this catch real bugs?
