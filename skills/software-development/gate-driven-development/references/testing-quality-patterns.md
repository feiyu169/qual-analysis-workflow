# Testing Quality Patterns (verified 2026-07-10)

## Why Tests Miss Bugs

Root cause analysis of 48 bugs found by expert review but missed by 210 tests:

| Root Cause | Description | Fix |
|-----------|-------------|-----|
| Happy-path only | Tests check "runs without error" not "behavior correct" | Boundary tests + property tests |
| Weak assertions | avg 1.8 assertions/test (industry: 3-5) | AssertMixin dual-dimension |
| No side-effect verification | Only check return values | DB/log/state verification |
| No integration tests | Module interactions untested | Contract tests |
| Simple test data | Clean data doesn't trigger edge cases | TestDataFactory |

## AssertMixin Pattern

```python
class AssertMixin:
    def assert_return_value(self, actual, expected, msg=""):
        """Dimension 1: verify return value"""
        assert actual == expected, f"Return mismatch: {actual!r} != {expected!r}. {msg}"
    
    def assert_state_change(self, obj, attr, expected, msg=""):
        """Dimension 1: verify state change"""
        actual = getattr(obj, attr)
        assert actual == expected, f"State mismatch: {attr}={actual!r} != {expected!r}. {msg}"
    
    def assert_side_effect(self, db_path, query, expected, msg=""):
        """Dimension 2: verify database side effect"""
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            row = cursor.fetchone()
            assert row is not None, f"No result: {query}. {msg}"
            assert row[0] == expected, f"DB mismatch: {row[0]!r} != {expected!r}. {msg}"
    
    def assert_time_field(self, time_str, msg=""):
        """Dimension 2: verify ISO 8601 + UTC"""
        assert time_str is not None, f"Time is None. {msg}"
        assert 'T' in time_str, f"Not ISO format: {time_str}. {msg}"
        has_tz = ('+' in time_str or 'Z' in time_str or time_str.endswith('+00:00'))
        assert has_tz, f"No timezone: {time_str}. {msg}"
```

## structlog Testing (non-invasive)

```python
from structlog.testing import capture_logs

def test_transition_logs_event(self, sm):
    with capture_logs() as cap_logs:
        sm.add_gate('test')
        sm.transition('test', GateStatus.IN_PROGRESS)
    
    logs = [e for e in cap_logs if e.get('event') == 'state_transition']
    assert len(logs) == 1
    assert logs[0]['gate_id'] == 'test'
```

## Concurrent Testing with Barrier

```python
import threading

def test_concurrent_transition(self, sm):
    sm.add_gate('test')
    success_count = [0]
    error_count = [0]
    barrier = threading.Barrier(10)
    
    def worker():
        barrier.wait()  # Synchronize start
        try:
            sm.transition('test', GateStatus.IN_PROGRESS)
            success_count[0] += 1
        except ValueError:
            error_count[0] += 1
    
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=5)
    
    assert success_count[0] == 1  # Exactly one succeeds
    assert error_count[0] == 9
```

## Property-Based Testing (Hypothesis)

```python
from hypothesis import given, strategies as st, settings

@settings(seed=42, max_examples=50, deadline=3000)  # Fixed seed for CI reproducibility
class TestRiskAssessorProperties:
    @given(st.lists(st.sampled_from(['security', 'auth', 'payment'])))
    def test_score_never_negative(self, areas):
        assessor = RiskAssessor()
        result = assessor.assess_risk(areas, '')
        assert result.score >= 0
```

**Key**: Always use `@settings(seed=42)` for CI reproducibility.
Use `st.sets()` instead of `st.lists() + set() + assume()` for efficiency.

## Coverage Measurement

coverage.py JSON format for functions:
```json
{"files": {"path.py": {"functions": {"ClassName.method": {"executed_lines": [1,2,3]}}}}}
```

Match by fully qualified name: `cov_func == method_name or cov_func.endswith(f".{func_name}")`
