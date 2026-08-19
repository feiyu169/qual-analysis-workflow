# Python Testing Tool Pitfalls (Verified 2026-07-10)

## Hypothesis (Property-Based Testing)

### Pitfall: `pytestmark = seed(42)` Does NOT Fix Seed

**Wrong:**
```python
from hypothesis import seed
pytestmark = seed(42)  # INVALID - does not apply to test classes
```

**Correct (Option 1 - Decorator):**
```python
from hypothesis import settings

@settings(seed=42, max_examples=100, deadline=5000)
class TestMyProperties:
    @given(st.integers())
    def test_something(self, n):
        ...
```

**Correct (Option 2 - Global Profile):**
```python
# conftest.py
from hypothesis import settings, HealthCheck
settings.register_profile("ci", seed=42, max_examples=100, deadline=5000)
settings.load_profile("ci")
```

**Correct (Option 3 - CI Command Line):**
```bash
pytest -m property --hypothesis-seed=42
```

**Key**: Use ALL THREE for maximum reliability.

### Pitfall: `RuleBasedStateMachine` Needs Explicit Marker

```python
class MyMachine(RuleBasedStateMachine):
    ...

# WRONG - missing marker, CI will skip
TestMyProperties = MyMachine.TestCase

# CORRECT - add marker
TestMyProperties = pytest.mark.property(MyMachine.TestCase)
```

### Pitfall: `lists + set + assume` Is Wasteful

```python
# WRONG - wastes generation time
@given(st.lists(st.sampled_from(['a', 'b', 'c'])))
def test_something(items):
    unique = list(set(items))
    if len(unique) < 2:
        assume(False)
    ...

# CORRECT - use st.sets directly
@given(st.sets(st.sampled_from(['a', 'b', 'c']), min_size=2, max_size=3))
def test_something(items):
    ...
```

---

## Mutmut (Mutation Testing)

### Pitfall: `tests_dir` Must Match Actual Test Location

**Wrong:**
```toml
[tool.mutmut]
tests_dir = ["workflow/tests/"]  # If tests are actually in ./tests/
```

**Correct:**
```toml
[tool.mutmut]
tests_dir = ["tests/"]  # Must match actual location
```

**Verification:** Run `mutmut run` and check if tests are found. If output shows "No tests found", path is wrong.

### Pitfall: CI Kill Rate Parsing Is Fragile

**Wrong:** Shell-based parsing depends on text format
```bash
KILLED=$(mutmut results | grep -oP 'Killed \K\d+')  # Brittle
```

**Correct:** Python script with try/except
```python
def parse_mutation_results() -> dict:
    try:
        result = subprocess.run(['mutmut', 'results'], capture_output=True, text=True, timeout=60)
        output = result.stdout + result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {'error': str(e)}
    # Parse with fallbacks
    ...
```

### Pitfall: Whitelist Deduction Must Match Actual Survived Mutants

**Wrong:** Simple count subtraction
```python
adjusted_survived = survived - len(whitelist)  # May undercount
```

**Correct:** Parse actual survived mutant IDs, then subtract matching whitelist entries
```python
survived_ids = parse_survived_ids(mutmut_output)
whitelist_ids = load_whitelist()
actual_survived = survived_ids - whitelist_ids
score = killed / (killed + len(actual_survived) + skipped) * 100
```

### Pitfall: Cache Key Must Include Test Files

**Wrong:**
```yaml
key: mutmut-${{ hashFiles('workflow/*.py') }}  # Misses test changes
```

**Correct:**
```yaml
key: mutmut-${{ hashFiles('workflow/**/*.py', 'tests/**/*.py', 'pyproject.toml') }}
```

---

## Coverage.py

### Pitfall: File-Level Coverage ≠ Method-Level Coverage

**Wrong:** Checking if file has any coverage
```python
covered = sum(1 for v in data['files'].values() if v['summary']['covered'] > 0)
# This counts FILES, not METHODS
```

**Correct:** Use `ast` to extract public methods, then match against coverage data
```python
import ast

def extract_public_methods(module_path: str) -> list:
    with open(module_path, 'r') as f:
        tree = ast.parse(f.read())
    methods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not item.name.startswith('_'):
                        methods.append(f"{node.name}.{item.name}")
    return methods
```

### Pitfall: coverage.py JSON Has Two Formats

coverage.py JSON `functions` field can be dict OR list depending on version:

```python
# Format 1 (dict): {"func_name": {"executed_lines": [...]}}
# Format 2 (list): [{"name": "func_name", "executed_lines": [...]}]

# Robust parsing:
functions_data = file_data.get('functions', {})
if isinstance(functions_data, dict):
    for name, data in functions_data.items():
        if len(data.get('executed_lines', [])) > 0:
            covered.append(name)
elif isinstance(functions_data, list):
    for item in functions_data:
        if isinstance(item, dict) and len(item.get('executed_lines', [])) > 0:
            covered.append(item.get('name', ''))
```

---

## General Pattern: "Description vs Implementation" Gap

When writing technical documents, ALWAYS provide **executable code**, not pseudocode.

**Wrong (description):**
```
固定随机种子：使用 @settings(seed=42) 装饰器
```

**Correct (executable):**
```python
@settings(seed=42, max_examples=100, deadline=5000)
class TestMyProperties:
    @given(st.integers())
    def test_something(self, n):
        assert n >= 0
```

**Rule:** Every technical claim in a document must have a corresponding code block that can be copy-pasted and run.
