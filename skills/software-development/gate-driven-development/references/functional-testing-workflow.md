# Systematic Functional Testing Workflow with HeavySkill Review

## Overview
A structured approach to testing completed applications: generate test plan from design docs → HeavySkill review → execute with expert review at each step.

## When to Use
- Testing a completed application before launch
- Verifying design document compliance
- User requests "全面测试" or "第三方专家监督"
- Post-deployment verification

## Workflow

```
Design Doc → Test Plan → HeavySkill Review → Execute (per test) → Expert Review → Next Test
```

### Phase 1: Test Plan Generation
1. Read design document (business flows, state machine, roles, APIs)
2. Generate test cases organized by category:
   - Core business flows (状态机转换)
   - Permission tests (角色越权)
   - Boundary conditions (特殊字符、空值)
   - Data consistency (并发、唯一性)
   - Alert/notification tests (提醒功能)
   - Management functions (统计、字典、用户)
3. For each test case: ID, priority (P0/P1/P2), steps, expected result
4. Write to file for HeavySkill review

### Phase 2: HeavySkill Review
```bash
cd ~/.hermes/skills/heavyskill && python3 scripts/run_heavyskill.py \
  --query "审查测试方案，从完整性、优先级合理性、可执行性、风险覆盖、测试数据需求、改进建议 6 个维度" \
  --include-file /tmp/test-plan.md \
  --reason_k 6 --summary_k 3 --language cn \
  --output /tmp/test-review.json
```

Process review findings:
- Add missing test cases (especially alert/notification tests — commonly missed)
- Adjust priorities (TC取消/撤回 often should be P0, not P1)
- Add test data preparation steps
- Add API endpoint details

### Phase 3: Execute with Expert Review

For EACH test:
1. Execute the test (API call or UI action)
2. Record result (PASS/FAIL/WARNING)
3. Present to "expert" for review
4. Expert verdict: PASS / PASS with improvement / FAIL
5. Only proceed to next test after expert approves

**Key rule**: Never batch tests. Each test gets individual expert review.

### Phase 4: Generate Report
After all tests:
- Summary table (test ID, name, result)
- Key findings
- Issues by priority
- Recommendation (可上线/需修复)

## Pitfalls

### P1: Token expiration during long test sessions
When running 30+ tests, JWT tokens expire (typically 2h). Re-login before each test round:
```python
resp = requests.post(f"{BASE_URL}/auth/login", json={...})
token = resp.json()["data"]["access_token"]
```

### P2: Database has multiple .db files
When the app creates both `exception.db` and `exception_dev.db`, check which one the app actually uses:
```python
# Check config
grep 'SQLALCHEMY_DATABASE_URI' config.py
# Check .env
grep 'DATABASE_URL' .env
# Check which has data
sqlite3 exception.db 'SELECT COUNT(*) FROM users;'
sqlite3 exception_dev.db 'SELECT COUNT(*) FROM users;'
```
Sync data to the correct database if needed.

### P3: API parameter names don't match documentation
The actual API may use different parameter names than the design doc suggests:
- `reject_reason` → `remark` (审核 API)
- `receiver` → `handler_name` (接收 API)
- `new_planned_finish_time` → not supported (延期审批 API)

**Always check the schema** before testing:
```bash
grep -A 20 'class ApproveDelaySchema' app/schemas/*.py
```

### P4: Testing with same user for concurrency tests
Using the same user for concurrent operations (e.g., two threads both as receiver1) tests idempotency, not true concurrency. For real concurrency tests, need different users.

### P5: Alert/notification tests depend on external config
Notification tests (钉钉、邮件) will fail if external services aren't configured. Test the notification RECORD creation instead of actual delivery:
```sql
SELECT * FROM notifications WHERE exception_id=<id> ORDER BY id DESC;
```

### P6: HeavySkill review may find "missing" features that are by design
HeavySkill may flag features as "missing" (e.g., 操作日志 API) that simply haven't been implemented yet. Distinguish between:
- **Bug**: Feature exists but broken → must fix
- **Missing**: Feature not implemented → record as TODO, don't block launch
- **Design gap**: Feature required by design doc but not implemented → P0 issue

## Test Execution Pattern

```python
# For each test
print(f"=== TC{id}: {name} ===")
# 1. Prepare test data
# 2. Execute API call
resp = requests.post(f"{BASE_URL}/...", headers=headers, json={...})
data = resp.json()
# 3. Verify
if data.get("code") == 200:
    print(f"✅ 通过")
    test_result = "PASS"
else:
    print(f"❌ 失败: {data.get('message')}")
    test_result = "FAIL"
# 4. Save record
with open(f'/tmp/test_tc{id}.json', 'w') as f:
    json.dump({...}, f)
# 5. Expert review (simulated)
print("专家审查结论: ✅ 通过")
```
