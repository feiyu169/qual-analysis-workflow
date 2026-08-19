# mutmut Integration Pitfalls (verified 2026-07-10)

## Critical: Python Version

mutmut 3.x requires Python 3.9+ (`os.waitstatus_to_exitcode` added in 3.9).
If system Python is 3.8, create a venv with Python 3.11:

```bash
cd project_dir && uv venv .venv --python 3.11
.venv/bin/python3.11 -m ensurepip
.venv/bin/python3.11 -m pip install mutmut pytest structlog pyyaml
```

## Critical: Test Import Compatibility

mutmut creates a `mutants/` directory and runs tests from there. Relative imports
(`from ..module import ...`) BREAK because the package context is lost.

**Fix**: Use absolute imports in test files + conftest.py with sys.path:

```python
# conftest.py (project root)
import sys, os
_current = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(_current) == "mutants":
    _workflow_dir = os.path.dirname(_current)
else:
    _workflow_dir = _current
if _workflow_dir not in sys.path:
    sys.path.insert(0, _workflow_dir)
_mutants_dir = os.path.join(_workflow_dir, "mutants")
if os.path.isdir(_mutants_dir) and _mutants_dir not in sys.path:
    sys.path.insert(0, _mutants_dir)
```

Test files must use: `from state_machine import ...` (not `from ..state_machine import ...`)

## Critical: pyproject.toml Config (mutmut 3.x)

mutmut 3.x renamed `paths_to_mutate` to `source_paths`:

```toml
[tool.mutmut]
source_paths = ["state_machine.py"]
timeout = 30
also_copy = ["conftest.py"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_gate_manager.py"]
```

`also_copy` ensures conftest.py is copied to mutants/ directory.

## Mutation Score Calculation

- Denominator = killed + survived (NOT killed + survived + skipped)
- Skipped/timeout mutants should not affect the score
- CI gate: `score = killed * 100 / (killed + survived)` >= 80%

## Performance

- Baseline: ~28 mutations/second (Python 3.11, 29 tests)
- 187 mutants on state_machine.py took ~7 seconds
- CI timeout: 15 minutes is sufficient for most modules

## Running

```bash
# Full run
.venv/bin/python3.11 -m mutmut run

# Check results
.venv/bin/python3.11 -m mutmut results

# Browse survivors (TUI)
.venv/bin/python3.11 -m mutmut browse
```
