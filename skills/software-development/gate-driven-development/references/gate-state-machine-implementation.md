# Gate-Driven State Machine Implementation Pattern

## Overview

Concrete Python implementation of the Gate-Driven abstract concepts: state machine with SQLite persistence, verification engine, and failure handling.

## File Structure

```
~/.hermes/workflow/
├── __init__.py
├── state_machine.py          # Core state machine with SQLite persistence
├── gate_manager.py           # Gate execution engine
├── verification_engine.py    # L1-L5 verification
├── config/
│   └── gates.yaml            # Gate definitions (YAML config)
├── tests/
│   ├── test_gate_manager.py
│   └── test_verification_engine.py
└── db/
    └── gate_state.db         # SQLite persistence
```

## State Machine Design (state_machine.py)

```python
class GateStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ESCALATED = "escalated"

# Valid state transitions - IMMUTABLE
VALID_TRANSITIONS = {
    GateStatus.PENDING: [GateStatus.IN_PROGRESS],
    GateStatus.IN_PROGRESS: [GateStatus.PASSED, GateStatus.FAILED, GateStatus.TIMEOUT],
    GateStatus.FAILED: [GateStatus.IN_PROGRESS, GateStatus.ESCALATED],
    GateStatus.TIMEOUT: [GateStatus.IN_PROGRESS, GateStatus.ESCALATED],
    GateStatus.PASSED: [],  # Terminal state
    GateStatus.ESCALATED: [GateStatus.IN_PROGRESS],  # Can retry after escalation
}
```

### Key Design Decisions

1. **SQLite persistence**: State survives process restarts
2. **Immutable transitions**: VALID_TRANSITIONS is a class-level dict, not instance-level
3. **Terminal states**: PASSED and ESCALATED are terminal (no further transitions)
4. **Failure counting**: Each FAILED transition increments failure_count
5. **Error recording**: Last error is stored in state for debugging

## Gate Manager Design (gate_manager.py)

```python
class GateManager:
    def __init__(self, config_path=None, db_path=None):
        self.gates = {}
        self.handlers = {}
        self.state_machine = GateStateMachine(db_path)
        
    async def execute_gate(self, gate_id, task_func=None):
        # 1. Check entry criteria
        self.check_entry_criteria(gate_id)
        
        # 2. Transition to IN_PROGRESS
        self.state_machine.transition(gate_id, GateStatus.IN_PROGRESS)
        
        try:
            # 3. Execute task
            result = await task_func() if task_func else None
            
            # 4. Verify exit criteria
            self.verify_exit_criteria(gate_id, result)
            
            # 5. Transition to PASSED
            self.state_machine.transition(gate_id, GateStatus.PASSED)
            return result
            
        except Exception as e:
            # 6. Handle failure
            self.state_machine.transition(gate_id, GateStatus.FAILED, error=str(e))
            return self.handle_failure(gate_id, e)
```

### Critical: escalate_to_owner must go through FAILED first

```python
# ❌ WRONG - can't go PENDING -> ESCALATED
def escalate_to_owner(self, gate_id):
    self.state_machine.transition(gate_id, GateStatus.ESCALATED)

# ✅ CORRECT - must go through FAILED first
def escalate_to_owner(self, gate_id):
    current = self.state_machine.get_status(gate_id)
    if current != GateStatus.FAILED:
        self.state_machine.transition(gate_id, GateStatus.FAILED)
    self.state_machine.transition(gate_id, GateStatus.ESCALATED)
```

## Verification Engine Design (verification_engine.py)

```python
class VerificationEngine:
    FORBIDDEN_VERIFICATIONS = [
        "file_exists",           # File existing ≠ working
        "status_code_200",       # 200 ≠ correct data
        "output_not_empty"       # Non-empty ≠ correct
    ]
    
    def verify(self, level, command=None, expected=None):
        if level in self.FORBIDDEN_VERIFICATIONS:
            raise ValueError(f"Forbidden verification: {level}")
        return self.verifiers[level](command, expected)
```

### L1 Verification (Unit Tests)

```python
def verify_unit_test(self, command=None):
    result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=300)
    
    # Check pass/fail
    if result.returncode != 0:
        return VerificationResult(passed=False, level="L1", message="Tests failed")
    
    # Check coverage (must extract from output)
    coverage = self._extract_coverage(result.stdout)
    if coverage < 80:
        return VerificationResult(passed=False, level="L1", message=f"Coverage {coverage}% < 80%")
    
    return VerificationResult(passed=True, level="L1", message=f"Passed, coverage {coverage}%")
```

## Gate YAML Config Format

```yaml
gates:
  gate_0_1:
    name: "Grill Session"
    phase: 0
    entry_criteria:
      - type: "user_request"
        description: "User提出需求"
    exit_criteria:
      - type: "document_generated"
        description: "需求文档生成"
        verification: "L1"
    timeout: 3600  # seconds
    max_retries: 3
```

## Pitfalls

### P1: State transition validation must be in transition(), not in caller
The state machine's `transition()` method must validate the transition is legal. Callers should NOT pre-check and then call — this creates a TOCTOU race.

### P2: SQLite datetime is always offset-naive
Use `datetime.now()` not `datetime.now(timezone.utc)` with SQLite. See gate-driven-development pitfall P17.

### P3: handle_failure must check failure_count BEFORE incrementing
The failure_count check in handle_failure happens on the state AFTER the FAILED transition incremented it. So `state.failure_count >= max_retries` fires at exactly the right count.

### P4: Test coverage extraction is fragile
Pytest output format varies. Use `pytest-cov` with `--cov-report=json` for reliable extraction:
```bash
pytest tests/ -v --cov=workflow --cov-report=json
```
Then parse `coverage.json` instead of regex on stdout.
