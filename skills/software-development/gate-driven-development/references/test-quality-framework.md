# Test Quality Framework

## Why Tests Miss Bugs — 5 Root Causes

1. **Tests only verify happy path**: Check "function runs" not "function behaves correctly"
2. **Assertions too loose**: `assert result` instead of `assert result == expected_value` (avg 1.8 assertions/test vs industry standard 3-5)
3. **Test data too simple**: Fixtures with clean data don't trigger edge cases
4. **No integration tests**: Unit tests pass but module interactions fail (e.g., naming conflicts)
5. **Tests don't verify side effects**: Only check return values, not state changes, logs, database

## AssertMixin Pattern (Two-Dimension Verification)

Each test must cover at least 2 independent verification dimensions:

```python
class AssertMixin:
    def assert_return_value(self, actual, expected, msg=""):
        """Dimension 1: Return value"""
        assert actual == expected, f"Return mismatch: {actual!r} != {expected!r}. {msg}"
    
    def assert_state_change(self, obj, attr, expected, msg=""):
        """Dimension 1: State change"""
        actual = getattr(obj, attr)
        assert actual == expected, f"State mismatch: {attr}={actual!r} != {expected!r}. {msg}"
    
    def assert_side_effect(self, db_path, query, expected, msg=""):
        """Dimension 2: Database side effect"""
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            row = cursor.fetchone()
            assert row is not None, f"No result: {query}. {msg}"
            assert row[0] == expected, f"DB mismatch: {row[0]!r} != {expected!r}. {msg}"
    
    def assert_time_field(self, time_str, msg=""):
        """Dimension 2: Time field format (ISO 8601 + UTC)"""
        assert time_str is not None, f"Time is None. {msg}"
        assert 'T' in time_str, f"Not ISO format: {time_str}. {msg}"
        has_tz = ('+' in time_str or 'Z' in time_str or time_str.endswith('+00:00'))
        assert has_tz, f"No timezone: {time_str}. {msg}"
```

## Test Categories

### Boundary Tests (test_boundary.py)
- Empty/None inputs
- Invalid state transitions
- Terminal state irreversibility
- Corrupted data (malformed JSON, missing fields)
- Database operation failures

### Side Effect Tests (test_side_effects.py)
- Database persistence verification (direct sqlite3 queries)
- Log output verification (structlog.testing.capture_logs)
- Load-save roundtrip consistency
- Field format verification (timestamps, enums)

### Integration Tests (test_integration.py)
- Cross-module state consistency
- Naming conflict detection (e.g., GateStatus vs GateExecutionStatus)
- Mapping chain integrity (verify all targets exist)
- Golden tests (verify specific values, not just "non-zero")
- Configuration loading edge cases

### Concurrent Tests (test_concurrent.py)
- Use threading.Barrier for synchronized start
- Shared counters for success/failure tracking
- Strict assertions (exact counts, not ranges)
- Test idempotency under concurrency

## TestDataFactory Pattern

```python
class TestDataFactory:
    @staticmethod
    def create_standard_config() -> Dict: ...
    
    @staticmethod
    def create_edge_case_configs() -> Dict[str, Dict]:
        """Returns: empty, invalid_type, missing_fields, unicode, zero_timeout, zero_retries"""
    
    @staticmethod
    def create_corrupted_config_path() -> str: ...
```

## Multi-Round Review Pattern

1. **Round 1**: Expert review → Score 50/100 → Fix 27 issues → Score 72
2. **Round 2**: Re-review → Fix 4 new issues → Score 80
3. **Round 3**: HeavySkill K=8 → Fix 15 issues → Score 88
4. **Round 4**: Final review → Fix 2 issues → Score 90

Key: Each round discovers issues invisible to previous rounds. Budget 3-4 rounds.

## Acceptance Criteria

| Metric | Before | Target | Measurement |
|--------|--------|--------|-------------|
| Assertions/test | 1.8 | 2.0+ | Manual review |
| Boundary coverage | 0% | 30%+ | `pytest -k boundary --collect-only` |
| Integration ratio | 0% | 20%+ | `pytest -m integration --collect-only` |
| Mutation kill rate | N/A | 80%+ | `mutmut run --paths-to-mutate=...` |
