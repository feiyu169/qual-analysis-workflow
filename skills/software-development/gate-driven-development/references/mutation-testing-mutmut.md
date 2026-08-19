# Mutation Testing with mutmut — Integration Guide

## mutmut 3.x Configuration

```toml
# pyproject.toml
[tool.mutmut]
source_paths = ["target_module.py"]  # NOT paths_to_mutate (deprecated in 3.x)
timeout = 30
also_copy = ["conftest.py"]  # CRITICAL: must copy to mutants/

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_target.py"]  # Limit collection
```

## Critical Pitfalls (verified 2026-07-10)

### 1. Python Version Requirement
mutmut 3.x requires Python 3.9+ (`os.waitstatus_to_exitcode`). If system Python is 3.8:
```bash
cd project && uv venv .venv --python 3.11
.venv/bin/python3.11 -m pip install mutmut pytest
```

### 2. mutants/ Directory Problem
mutmut creates `mutants/` subdirectory and runs tests from there. Without `also_copy = ["conftest.py"]`, the sys.path setup is missing and all absolute imports fail.

### 3. Relative Imports Break
mutmut breaks `from ..module import` in test files. **All test files must use absolute imports**:
```python
# BAD (breaks under mutmut)
from ..state_machine import GateStateMachine

# GOOD
from state_machine import GateStateMachine
```

### 4. Source File Imports
Source files using relative imports also break. Use try/except pattern:
```python
try:
    from .state_machine import GateStateMachine
except ImportError:
    from state_machine import GateStateMachine
```

### 5. Kill Rate Formula
```
score = killed / (killed + survived)
```
NOT `killed / (killed + survived + skipped)`. Skipped/timeout mutants don't dilute score.

### 6. Test Collection
mutmut runs pytest which collects ALL test files. Use `[tool.pytest.ini_options] python_files` to limit, or ensure ALL test files have compatible imports.

## conftest.py Template

```python
"""Root conftest.py — ensures imports work under both pytest and mutmut"""
import sys
import os

_dir = os.path.dirname(os.path.abspath(__file__))
if _dir not in sys.path:
    sys.path.insert(0, _dir)

# Handle mutants/ subdirectory
_mutants = os.path.join(_dir, "mutants")
if os.path.isdir(_mutants) and _mutants not in sys.path:
    sys.path.insert(0, _mutants)
```

## Property-Based Testing (Hypothesis)

```python
from hypothesis import given, strategies as st, settings
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant

# Fix seed for CI reproducibility
@settings(seed=42, max_examples=50, deadline=3000)
class TestProperties:
    @given(st.lists(st.sampled_from(['a', 'b', 'c'])))
    def test_invariant(self, items):
        assert len(items) >= 0

# State machine testing (dynamic driving)
class MyMachine(RuleBasedStateMachine):
    @rule()
    def some_action(self): ...
    
    @invariant()
    def property_holds(self): ...

TestMyMachine = MyMachine.TestCase
```

**Key**: `@settings(seed=42)` for reproducibility, NOT `pytestmark = seed(42)` (invalid).

## Coverage Measurement

```python
# Use functions field, not file-level summary
functions_data = file_data.get('functions', {})
for func_name, cov_data in functions_data.items():
    if isinstance(cov_data, dict):
        executed = cov_data.get('executed_lines', [])
        if len(executed) > 0:
            # Function is covered
            pass
```

## CI Integration Pattern

```yaml
# .github/workflows/mutation.yml
- name: Cache mutmut
  uses: actions/cache@v4
  with:
    path: .mutmut-cache
    key: mutmut-${{ hashFiles('**/*.py', 'pyproject.toml') }}

- name: Run mutation testing
  run: .venv/bin/python -m mutmut run

- name: Check mutation score
  run: python scripts/check_mutation_score.py  # Custom script with threshold
```
