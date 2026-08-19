# API Parameter Discovery Pattern

## Problem

API returns 400 with "Unknown field" or "参数验证失败" when testing.

## Root Cause

Parameters sent don't match the Schema definition in the backend.

## Discovery Method

### Step 1: Find the Schema class
```bash
ssh server 'grep -A 20 "class XxxSchema" /path/to/schemas/*.py'
```

### Step 2: Check field definitions
```python
class AcceptExceptionSchema(Schema):
    handler_name = fields.String(required=True)  # Required!
    handler_dingtalk_id = fields.String(load_default=None)
    version = fields.Integer(load_default=None)
```

### Step 3: Use correct parameter names
```python
# ❌ Wrong: Using guessed parameter names
{"handler": "李四"}  # Schema expects "handler_name"

# ✅ Right: Using Schema-defined names
{"handler_name": "李四"}
```

## Common Mismatches Found (2026-06-17)

| API Endpoint | Expected Param | Actual Param | Notes |
|--------------|---------------|--------------|-------|
| /accept | handler | handler_name | Schema uses handler_name |
| /approve | reject_reason | remark | Schema uses remark, not reject_reason |
| /delay/approve | new_planned_finish_time | (not supported) | Schema only has approved + remark |
| /reject | reject_reason | reject_reason | This one matches |

## Lesson

ALWAYS check the Schema definition before testing. Don't assume parameter names from documentation or API descriptions.
