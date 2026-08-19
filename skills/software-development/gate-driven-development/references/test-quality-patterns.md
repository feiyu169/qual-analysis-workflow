# Multi-Round Code Review Pattern (verified 2026-07-10)

## Review Cycle

When conducting code review with iterative fixes:

**Round 1**: Expert delegate review → fix all P0/P1 issues
**Round 2**: Re-review to verify fixes and catch regressions
**Round 3**: HeavySkill K=8 for deep multi-trajectory analysis
**Round 4**: Final verification with expert sign-off

Each round should:
1. Dispatch expert review (delegate_task)
2. Extract findings and respond to each
3. Fix issues and run tests
4. Update score tracking

**Score progression pattern**: 50 → 72 → 88 → 90 (4 rounds typical)

---

# Test Quality Improvement Pattern (verified 2026-07-10)

## Root Causes of Test Blindness

When tests pass (100%) but expert review finds bugs (100% miss rate):

| Root Cause | Signal | Fix |
|------------|--------|-----|
| Tests only verify happy path | No `raises`/`None`/`empty` tests | Add boundary tests |
| Assertions too loose | `assert result` not `assert result == expected` | Use AssertMixin |
| No side effect verification | Only check return values | Add DB/log assertions |
| No integration tests | Unit passes but modules disagree | Cross-module tests |
| No concurrent tests | Single-thread only | threading.Barrier sync |

## Test Infrastructure Files

```
tests/
├── conftest.py          # Shared fixtures (temp DB, config)
├── base.py              # AssertMixin
├── factories.py         # TestDataFactory
├── test_boundary.py     # Edge cases
├── test_side_effects.py # DB persistence, logging, roundtrip
├── test_integration.py  # Cross-module, mapping chains
├── test_concurrent.py   # Thread-safe tests
└── test_*.py            # Unit tests per module
```

## AssertMixin Pattern

```python
class AssertMixin:
    def assert_return_value(self, actual, expected, msg=""):
        """Dimension 1: Verify return value"""
        assert actual == expected, f"Return mismatch: {actual!r} != {expected!r}. {msg}"
    
    def assert_state_change(self, obj, attr, expected, msg=""):
        """Dimension 1: Verify state change"""
        actual = getattr(obj, attr)
        assert actual == expected, f"State mismatch: {attr}={actual!r} != {expected!r}. {msg}"
    
    def assert_side_effect(self, db_path, query, expected, msg=""):
        """Dimension 2: Verify database side effect"""
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            actual = cursor.fetchone()[0]
            assert actual == expected, f"DB mismatch: {actual!r} != {expected!r}. {msg}"
    
    def assert_time_field(self, time_str, msg=""):
        """Dimension 2: Verify ISO 8601 + UTC timezone"""
        assert time_str is not None, f"Time field is None. {msg}"
        assert 'T' in time_str, f"Not ISO format: {time_str}. {msg}"
        has_tz = ('+' in time_str or 'Z' in time_str or time_str.endswith('+00:00'))
        assert has_tz, f"No timezone: {time_str}. {msg}"
```

## TestDataFactory Pattern

```python
class TestDataFactory:
    @staticmethod
    def create_standard_config() -> Dict: ...
    
    @staticmethod
    def create_edge_case_configs() -> Dict[str, Dict]:
        """Returns: empty, invalid_type, missing_fields, unicode, zero_timeout, zero_retries"""
    
    @staticmethod
    def create_corrupted_config_path() -> str:
        """Returns path to invalid YAML file"""
```

## Concurrent Test Pattern

```python
def test_concurrent_transition_only_one_succeeds(self, sm):
    """Use threading.Barrier for deterministic synchronization"""
    sm.add_gate('test')
    success_count = [0]
    error_count = [0]
    barrier = threading.Barrier(10)  # Sync start point
    
    def worker():
        barrier.wait()  # Ensure simultaneous start
        try:
            sm.transition('test', GateStatus.IN_PROGRESS)
            success_count[0] += 1
        except ValueError:
            error_count[0] += 1
    
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=5)
    
    # Strict assertions
    assert success_count[0] == 1
    assert error_count[0] == 9
```

## Logging Verification Pattern

```python
from structlog.testing import capture_logs

def test_transition_logging(self, sm):
    """Non-invasive log verification"""
    with capture_logs() as cap_logs:
        sm.transition('test', GateStatus.IN_PROGRESS)
    
    logs = [e for e in cap_logs if e.get('event') == 'state_transition']
    assert len(logs) == 1
    assert logs[0]['gate_id'] == 'test'
```

## Acceptance Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Validation dimensions/test | 2.0+ | Manual review |
| Boundary equivalence classes/method | 2+ | Manual review |
| Integration test ratio | 20%+ | `pytest -m integration --collect-only` |
| Mutation test kill rate | 80%+ | `mutmut run --paths-to-mutate=module/` |

---

## Advanced Patterns

For mutation testing (mutmut), property-based testing (Hypothesis), and contract testing patterns, see:
→ `references/mutation-property-contract-testing.md`
