# Reasoning Model Pitfall — deepseek-v4-pro / deepseek-r1

**Date**: 2026-06-01
**Severity**: Critical (silent failure, no output)

## Problem

HeavySkill config.yaml was updated from `model: deepseek-v3` to `model: deepseek-v4-pro`. This broke all HeavySkill invocations silently.

## Technical Root Cause

DeepSeek v4-pro is a reasoning model. Its API response format differs from standard models:

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "",                          // ← EMPTY (HeavySkill reads this)
      "reasoning_content": "推理过程..."        // ← Actual output here
    }
  }],
  "usage": {
    "completion_tokens_details": {
      "reasoning_tokens": 10                   // ← All tokens are reasoning tokens
    }
  }
}
```

HeavySkill's `openai_compatible.py` line 152:
```python
content=message.get("content", "")  # Always empty for reasoning models
```

## Error Cascade

1. 6 concurrent requests sent to DeepSeek API with `max_tokens=80000`
2. v4-pro enters reasoning phase → consumes time + tokens for internal reasoning
3. Reasoning phase for 6 concurrent long-prompt requests takes 3+ minutes
4. httpx connection times out (120s default) → `httpx.TimeoutException`
5. Retry logic kicks in (4 attempts × 6 requests = 24 total requests)
6. Terminal timeout at 300s → process killed

Log output:
```
WARNING: Request error (attempt 1/4):     ← empty error string from TimeoutException
```

## Verification

Simple API test confirms both models work:
```python
# deepseek-v3: content field has output ✅
# deepseek-v4-pro: content field empty, reasoning_content has output ❌ for HeavySkill
```

6 concurrent simple requests: both models respond in <2s.
6 concurrent HeavySkill-length requests with max_tokens=80000: v3 works, v4-pro times out.

## Fix

Always use `deepseek-v3` for HeavySkill:
```yaml
# config.yaml
model: deepseek-v3
summary_model: deepseek-v3
```

Or override per invocation:
```bash
--model deepseek-v3
```

## Compatible Models

| Model | Compatible? | Notes |
|-------|------------|-------|
| deepseek-v3 | ✅ | Standard model, content field works |
| deepseek-v4-pro | ❌ | Reasoning model, uses reasoning_content |
| deepseek-reasoner | ❌ | Reasoning model, uses reasoning_content |
| deepseek-v4 | Unknown | Test before use |
