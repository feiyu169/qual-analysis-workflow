# Advanced Testing Patterns (verified 2026-07-10)

## Mutation Testing with mutmut

### Critical Pitfalls

1. **tests_dir must match actual test location**
   ```toml
   # WRONG - tests are in tests/ not workflow/tests/
   tests_dir = ["workflow/tests/"]
   
   # CORRECT
   tests_dir = ["tests"]
   ```

2. **Kill rate calculation: exclude skipped**
   ```python
   # WRONG - skipped inflates denominator, deflates kill rate
   score = killed / (killed + survived + skipped)
   
   # CORRECT - only killed + survived are meaningful
   score = killed / (killed + survived)
   ```

3. **Equivalent mutant whitelist must match actual survived IDs**
   ```python
   # WRONG - assumes all whitelist entries are survived
   adjusted_survived = survived - len(whitelist)
   
   # CORRECT - parse actual survived IDs, then match
   survived_ids = parse_survived_from_mutmut_output()
   matched = sum(1 for w in whitelist if w in survived_ids)
   adjusted_survived = survived - matched
   ```

4. **CI caching must include test files and config**
   ```yaml
   # WRONG - only caches source
   key: mutmut-${{ hashFiles('workflow/*.py') }}
   
   # CORRECT - includes tests and config
   key: mutmut-${{ hashFiles('workflow/**/*.py', 'tests/**/*.py', 'pyproject.toml') }}
   ```

5. **Exclude slow tests in CI, run full weekly**
   ```yaml
   # PR: fast subset
   mutmut run --use-cache --pytest-args="-m 'not slow and not integration'"
   
   # Weekly: full run
   mutmut run  # no exclusions
   ```

### CI Gate Script Pattern

```python
# scripts/check_mutation_score.py
# Key: use Python for robust parsing, not shell grep
import subprocess, sys

def parse_mutation_results() -> dict:
    """Robust parsing with try/except"""
    try:
        result = subprocess.run(['mutmut', 'results'], 
                              capture_output=True, text=True, timeout=60)
        # Parse with regex, handle format changes
        ...
    except subprocess.TimeoutExpired:
        print("❌ mutmut results timeout")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ mutmut not installed")
        sys.exit(1)
```

---

## Property-Based Testing with Hypothesis

### Critical Pitfalls

1. **Seed fixing: `pytestmark = seed(42)` is WRONG**
   ```python
   # WRONG - pytestmark doesn't work with seed()
   pytestmark = seed(42)
   
   # CORRECT - use @settings decorator
   @settings(seed=42, max_examples=100, deadline=5000)
   class TestMyProperties:
       ...
   
   # CORRECT - CI fallback
   pytest -m property --hypothesis-seed=42
   ```

2. **Use `st.sets()` not `lists + set + assume`**
   ```python
   # WRONG - wastes generation time
   @given(st.lists(st.sampled_from(['a', 'b', 'c'])))
   def test_prop(items):
       unique = set(items)
       if len(unique) < 2:
           assume(False)
       ...
   
   # CORRECT - generates directly
   @given(st.sets(st.sampled_from(['a', 'b', 'c']), min_size=2))
   def test_prop(items):
       ...
   ```

3. **RuleBasedStateMachine for state machines**
   ```python
   # Static checks are weak - only verify config table
   def test_terminal_has_no_outgoing(self):
       assert VALID_TRANSITIONS[PASSED] == []  # Just checks a dict
   
   # Dynamic checks are strong - actually drive transitions
   class StateMachineMachine(RuleBasedStateMachine):
       @rule()
       def transition_to_passed(self):
           try:
               self.sm.transition('test', GateStatus.PASSED)
           except ValueError:
               pass
       
       @invariant()
       def terminal_has_no_outgoing(self):
           status = self.sm.get_status('test')
           if status == GateStatus.PASSED:
               assert VALID_TRANSITIONS[status] == []
   ```

4. **@pytest.mark.property must be on ALL property test classes**
   ```python
   # WRONG - only on some classes
   @pytest.mark.property
   class TestA: ...
   
   class TestB: ...  # Missing marker! CI skips this
   
   # CORRECT - on all classes
   @pytest.mark.property
   class TestA: ...
   
   @pytest.mark.property
   class TestB: ...
   ```

---

## Contract Testing

### Principle: Interface-level only, NO behavior

**Verify:**
- Return types
- Required fields
- Enum value ranges
- Exception types

**Do NOT verify:**
- Persistence behavior
- Idempotency
- Error message text (implementation detail)

### Pattern

```python
@pytest.mark.contract
class TestStateMachineContract:
    def test_transition_returns_none(self, sm):
        """Contract: transition returns None"""
        sm.add_gate('test')
        result = sm.transition('test', GateStatus.IN_PROGRESS)
        assert result is None
    
    def test_get_status_returns_enum(self, sm):
        """Contract: get_status returns GateStatus enum"""
        sm.add_gate('test')
        status = sm.get_status('test')
        assert isinstance(status, GateStatus)
    
    def test_get_status_raises_on_missing(self, sm):
        """Contract: missing gate raises ValueError"""
        with pytest.raises(ValueError):
            sm.get_status('nonexistent')
```

### Automated Coverage Measurement

```yaml
# contracts/required_interfaces.yaml
interfaces:
  - module: state_machine
    class: GateStateMachine
    methods: [add_gate, get_status, transition, reset_gate]
  - module: verification_engine
    class: VerificationEngine
    methods: [verify]
```

```python
# scripts/measure_contract_coverage.py
# Compare required interfaces against collected contract tests
required = load_required_interfaces()
tests = get_contract_tests()  # pytest -m contract --collect-only
covered = [r for r in required if any(r.split('.')[-1] in t for t in tests)]
ratio = len(covered) / len(required) * 100
```

---

## coverage.py JSON Structure

**Two formats exist** (version-dependent):

```json
// Format 1: dict of functions
{
  "files": {
    "module.py": {
      "functions": {
        "func_name": {"executed_lines": [1,2,3], "missing_lines": [4]}
      }
    }
  }
}

// Format 2: list of functions
{
  "files": {
    "module.py": {
      "functions": [
        {"name": "func_name", "executed_lines": [1,2,3]}
      ]
    }
  }
}
```

**Robust parsing:**
```python
functions_data = file_data.get('functions', {})
if isinstance(functions_data, dict):
    # Format 1
    for name, data in functions_data.items():
        if len(data.get('executed_lines', [])) > 0:
            covered.append(name)
elif isinstance(functions_data, list):
    # Format 2
    for item in functions_data:
        if len(item.get('executed_lines', [])) > 0:
            covered.append(item['name'])
```

---

## HeavySkill Review Iteration Pattern

When iterating on technical documents through HeavySkill K=8:

1. **v1**: Submit initial plan → get baseline score
2. **Fix**: Address ALL findings, not just descriptions — provide executable code
3. **v2**: Re-submit → HeavySkill checks if fixes are real or just descriptions
4. **Fix again**: HeavySkill is strict — "descriptive fixes" get caught
5. **v3+**: Continue until score stabilizes above 80

**Key lesson**: HeavySkill distinguishes between "described fix" and "implemented fix". Always provide working code, not pseudocode.

**Score progression pattern**: 78 → 70 → 68 → 73 (scores drop when fixes are found to be superficial)
