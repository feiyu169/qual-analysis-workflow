# HGF Code Review Pitfalls (2026-07-10)

## Context
Full code review of HGF workflow implementation (`~/.hermes/workflow/`) against standard SE practices. Expert scored 50/100. Found 35 issues: 7 P0, 14 P1, 14 P2. 27/35 fixed, 75/75 tests passing.

## P0-Level Anti-Patterns (MUST fix)

### 1. Empty Validator Stubs
```python
# BAD: gate_manager.py _verify_criteria always returns True
def _verify_criteria(self, criteria, result=None) -> bool:
    return True  # ← entire gate mechanism is theater

# GOOD: wire to verification engine, handle by criteria type
def _verify_criteria(self, criteria, result=None) -> bool:
    if criteria.type in command_types:
        return self.verification_engine.verify(level=criteria.verification).passed
    elif criteria.type in document_types:
        return True if result is None else result.get("passed", False)
    else:
        raise ValueError(f"Unknown criteria type: {criteria.type}")
```

### 2. Variable Shadowing in Verify Loops
```python
# BAD: result parameter gets overwritten
def verify_exit_criteria(self, gate_id, result):
    for criteria in gate_config.exit_criteria:
        result = self._verify_criteria(criteria, result)  # ← shadows parameter!
        
# GOOD: use different variable name
def verify_exit_criteria(self, gate_id, result):
    for criteria in gate_config.exit_criteria:
        criteria_result = self._verify_criteria(criteria, result)
```

### 3. Double-Counting Failures
```python
# BAD: transition(FAILED) increments, then handle_failure increments again
def execute_gate(self, gate_id):
    self.state_machine.transition(gate_id, GateStatus.FAILED)  # +1
    return self.handle_failure(gate_id, e)  # +1 again!

# GOOD: handle_failure checks current state
def handle_failure(self, gate_id, error):
    current = self.state_machine.get_status(gate_id)
    if current == GateStatus.FAILED:
        # Already counted, do IN_PROGRESS→FAILED cycle for retry
        self.state_machine.transition(gate_id, GateStatus.IN_PROGRESS)
        self.state_machine.transition(gate_id, GateStatus.FAILED)
    elif current == GateStatus.IN_PROGRESS:
        self.state_machine.transition(gate_id, GateStatus.FAILED)
```

### 4. SQLite Connection Leaks
```python
# BAD: exception before close() leaks connection
conn = sqlite3.connect(path)
cursor = conn.cursor()
cursor.execute(...)  # if this throws, conn.close() never runs
conn.close()

# GOOD: context manager
with sqlite3.connect(path) as conn:
    cursor = conn.cursor()
    cursor.execute(...)
    conn.commit()
```

### 5. Relative Import Missing
```python
# BAD: ModuleNotFoundError when run as package
from gate_types import GateConfig

# GOOD: relative import
from .gate_types import GateConfig
```

## P1-Level Anti-Patterns

### 6. shell=True Command Injection
```python
# BAD
subprocess.run(command, shell=True, ...)

# GOOD
import shlex
cmd_args = shlex.split(command)
subprocess.run(cmd_args, shell=False, ...)
```

### 7. Bare except Clauses
```python
# BAD: catches KeyboardInterrupt, SystemExit
except:
    pass

# GOOD
except Exception:
    pass
```

### 8. Terminal State Bypass
```python
# BAD: reset_gate ignores VALID_TRANSITIONS
def reset_gate(self, gate_id):
    self.states[gate_id] = GateState(gate_id=gate_id, status=GateStatus.PENDING)

# GOOD: check terminal state
def reset_gate(self, gate_id, force=False):
    if self.get_status(gate_id) == GateStatus.PASSED and not force:
        raise ValueError("Cannot reset PASSED gate without force=True")
```

### 9. FORBIDDEN_VERIFICATIONS Check Logic Error
```python
# BAD: checks level ("L1") against method names ("file_exists") — never matches
if level in self.FORBIDDEN_VERIFICATIONS:
    raise ValueError(...)

# GOOD: check command content
if command:
    for forbidden in self.FORBIDDEN_VERIFICATIONS:
        if forbidden in command.lower():
            raise ValueError(...)
```

## Test Adaptation Pattern

When fixing core validation logic (making `_verify_criteria` actually validate):

1. Tests relying on "always pass" WILL break — this is expected and correct
2. Inject real VerificationEngine into test fixtures:
   ```python
   @pytest.fixture
   def gate_manager(config_path, db_path):
       gm = GateManager(config_path=config_path, db_path=db_path)
       gm.set_verification_engine(VerificationEngine())
       return gm
   ```
3. Change test criteria types from generic `"test"` to real types
4. Entry criteria (result=None) → document/flow types return True
5. Exit criteria (with result) → check `result.get("passed")`
6. For reset_gate tests: add `force=True` for PASSED state, add negative test for without force

## State Machine Design Rules

- `PASSED` = irreversible terminal (no outgoing transitions)
- `ESCALATED` = NOT terminal (can retry after human intervention)
- `FAILED` retry cycle: `FAILED → IN_PROGRESS → FAILED` (each cycle increments count)
- `handle_failure` must handle BOTH paths: from execute_gate (already FAILED) AND direct call (still IN_PROGRESS)
