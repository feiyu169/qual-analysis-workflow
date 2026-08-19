# Testing Quality Methodology

## Overview

Systematic approach to improving test effectiveness through mutation testing, property-based testing, and contract testing.

## Mutation Testing (mutmut)

### Configuration
```toml
[tool.mutmut]
paths_to_mutate = ["src/module.py"]
tests_dir = ["tests"]
timeout = 300
```

### Kill Rate Calculation
```python
# CORRECT: denominator = killed + survived (exclude skipped/timeout)
score = (killed * 100) // (killed + survived)

# WRONG: denominator includes skipped
score = (killed * 100) // (killed + survived + skipped)  # DO NOT USE
```

### White-list Integration
```python
# CORRECT: Parse actual survived mutants and match
survived_ids = parse_survived_mutants(mutmut_output)
matched = sum(1 for w in whitelist if w in survived_ids)
adjusted_survived = max(0, survived - matched)

# WRONG: Simple subtraction
adjusted_survived = survived - len(whitelist)  # DO NOT USE
```

### CI Parsing
```python
# CORRECT: Python script with try/except
def parse_mutation_results():
    try:
        result = subprocess.run(['mutmut', 'results'], ...)
        # Use regex to extract numbers
        killed = int(re.search(r'Killed\s+(\d+)', output).group(1))
    except Exception as e:
        print(f"Parse error: {e}")
        sys.exit(1)

# WRONG: Shell grep (fragile)
# killed=$(echo "$RESULT" | grep -oP 'Killed \K\d+')  # DO NOT USE
```

### Cache Key
```yaml
key: mutmut-${{ hashFiles('src/**/*.py', 'tests/**/*.py', 'pyproject.toml') }}
```

## Property-Based Testing (hypothesis)

### Seed Fixing
```python
# CORRECT: Use @settings decorator
@settings(seed=42, max_examples=100, deadline=5000)
class TestProperties:
    @given(st.integers())
    def test_something(self, n):
        ...

# WRONG: pytestmark = seed(42)  # Invalid syntax
```

### CI Configuration
```bash
# Command-line fallback
pytest -m property --hypothesis-seed=42
```

### Marker Requirement
All property test classes MUST have `@pytest.mark.property`:
```python
@pytest.mark.property
@settings(seed=42)
class TestProperties:
    ...

# RuleBasedStateMachine.TestCase does NOT inherit markers
@pytest.mark.property
class TestStateMachineProperties(GateStateMachineMachine.TestCase):
    pass
```

### Coverage Measurement
```python
# CORRECT: Use functions field from coverage.py JSON
functions_data = file_data.get('functions', {})
for method_name in methods:
    for cov_func, cov_data in functions_data.items():
        if cov_func == method_name or cov_func.endswith(f".{method_name}"):
            if isinstance(cov_data, dict):
                executed = cov_data.get('executed_lines', [])
                if len(executed) > 0:
                    covered_methods.append(method_name)

# WRONG: File-level coverage
if file_data.get('summary', {}).get('covered', 0) > 0:
    covered_methods.extend(methods)  # DO NOT USE
```

## Contract Testing

### Design Principles
1. **Only verify interface-level constraints**: return types, required fields, enum values
2. **Do NOT verify behavior**: persistence, idempotency belong in integration tests
3. **Avoid checking error message text**: only check error type

### Required Interfaces List
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

### Coverage Measurement
```python
# scripts/measure_contract_coverage.py
def main():
    with open('contracts/required_interfaces.yaml') as f:
        data = yaml.safe_load(f)
    
    required = []
    for item in data['interfaces']:
        for method in item['methods']:
            required.append(f"{item['module']}.{item['class']}.{method}")
    
    result = subprocess.run(['pytest', '-m', 'contract', '--collect-only', '-q'], ...)
    tests = [l.strip() for l in result.stdout.split('\n') if '::' in l]
    
    covered = [r for r in required if any(r.split('.')[-1] in t for t in tests)]
    ratio = (len(covered) * 100) // len(required) if required else 0
```

## HeavySkill Review Patterns

When using HeavySkill K=8 for technical document review:

1. **Implementation details matter**: Reviewers check actual code, not descriptions
2. **Iterative fixes**: Each round may reveal new issues in "fixed" code
3. **Score trajectory**: v1(78) → v2(70) → v3(68) → v4(35) → v5(73) → v6(75) is normal
4. **Convergence**: After 3-4 rounds, score stabilizes when all critical issues are fixed

### Common Reviewer Findings
- Invalid syntax (e.g., `pytestmark = seed(42)`)
- Data structure mismatch (coverage.py JSON format varies by version)
- Parsing fragility (string split vs regex)
- Missing markers/decorators
- Logic errors in calculations (denominator, matching)
