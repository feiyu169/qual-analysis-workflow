# Module Identity Bug & Import Compatibility (verified 2026-07-10)

## Problem: Module Identity Conflict

**Symptom**: `Invalid transition: pending -> in_progress` despite VALID_TRANSITIONS showing it's legal.

**Root cause**: pytest loads modules as `workflow.state_machine` (package import via __init__.py), but test files import `state_machine` (direct import via sys.path). These are TWO DIFFERENT MODULE INSTANCES with DIFFERENT GateStatus enum instances. Comparing `GateStatus.PENDING` from one with `GateStatus.IN_PROGRESS` from the other always fails.

**Reproduction**:
```python
# This FAILS:
from workflow.state_machine import GateStatus as A
from state_machine import GateStatus as B
assert A.PENDING is B.PENDING  # False!
```

## Fix: Consistent Import Style

ALL files (conftest.py, test files, source files) must use the SAME import style.

**Recommended approach**: Direct imports + root conftest.py with sys.path:

```python
# Root conftest.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# All test files
from state_machine import GateStateMachine, GateStatus  # ✅
# NOT: from ..state_machine import ...  # ❌

# Source files (with fallback for mutmut)
try:
    from .state_machine import GateStateMachine
except ImportError:
    from state_machine import GateStateMachine
```

## mutmut Compatibility

mutmut runs tests from `mutants/` subdirectory, breaking relative imports.

**Solution**:
1. Root conftest.py with sys.path.insert
2. Direct imports in all test files
3. try/except imports in source files
4. pyproject.toml: `also_copy = ["conftest.py"]`

## Verification

```bash
# Verify module identity
.venv/bin/python3.11 -c "
from state_machine import GateStatus
sm = GateStateMachine()
sm.add_gate('test')
print(sm.can_transition('test', GateStatus.IN_PROGRESS))  # Must be True
"
```
