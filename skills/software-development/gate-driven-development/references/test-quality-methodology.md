# Test Quality Improvement Methodology (Verified 2026-07-10)

## Root Cause: Why Tests Don't Catch Bugs

Analysis of 210 tests that all passed but missed 47 bugs found by expert review:

| Root Cause | % of Missed Bugs | Example |
|------------|------------------|---------|
| Tests only verify happy path | 35% | `assert result` instead of `assert result == expected` |
| Assertions too weak | 25% | Average 1.8 assertions/test (should be 3+) |
| No side-effect verification | 20% | Don't check DB, logs, state changes |
| No integration tests | 15% | Module interaction bugs invisible |
| Simple test data only | 5% | Don't trigger edge cases |

## Three-Layer Test Quality Framework

### Layer 1: Assertion Quality (Immediate)
- Every test must verify 2+ independent dimensions:
  - Dimension 1: Return value / state correctness
  - Dimension 2: Side effects / boundary conditions
- Use `AssertMixin` base class for consistent assertions
- Target: 3+ assertions per test

### Layer 2: Test Coverage (1-2 weeks)
- **Boundary tests**: Empty, None, invalid, corrupted data
- **Side-effect tests**: DB persistence, logging, state changes
- **Integration tests**: Cross-module interaction
- **Concurrent tests**: Thread safety with `threading.Barrier`

### Layer 3: Test Effectiveness (2-4 weeks)
- **Mutation testing** (mutmut): Kill rate ≥80%
- **Property-based testing** (hypothesis): Auto-generate 100+ inputs
- **Contract testing**: Interface-level assertions

## Test File Organization

```
tests/
├── conftest.py          # Global fixtures (db_path, sm, gate_manager)
├── base.py              # AssertMixin base class
├── factories.py         # Test data factory
├── test_boundary.py     # Boundary conditions
├── test_side_effects.py # DB/logging/state verification
├── test_integration.py  # Cross-module tests
├── test_concurrent.py   # Thread safety
├── test_contracts.py    # Interface contracts
├── test_properties.py   # Property-based tests
└── test_*.py            # Module-specific tests
```

## Pytest Configuration (2026 Best Practice)

```toml
[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
addopts = ["-ra", "--strict-markers", "--tb=short", "-q"]
markers = [
    "integration: 集成测试",
    "contract: 接口契约测试",
    "property: 属性测试",
    "slow: 慢速测试",
]
```

## Contract Testing Principles

**DO verify:**
- Return types
- Required fields
- Enum value ranges
- Exception types

**DON'T verify:**
- Persistence behavior
- Idempotency
- Error message text
- Implementation details

## Property Testing Scenarios

| Module | Property | Strategy |
|--------|----------|----------|
| State machine | Terminal has no outgoing | RuleBasedStateMachine |
| Risk assessor | Score never negative | st.lists(st.sampled_from(...)) |
| Task classifier | Level always valid | st.integers for file/line counts |
| Serialization | Roundtrip consistency | st.text for IDs |
