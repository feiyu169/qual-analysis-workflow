# State Machine Implementation for Gate Manager

## Core State Machine

```python
import sqlite3
import json
from datetime import datetime
from enum import Enum
from typing import Dict, Optional
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()

class GateStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ESCALATED = "escalated"

@dataclass
class GateState:
    gate_id: str
    status: GateStatus
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None
    failure_count: int = 0
    last_error: Optional[str] = None
    metadata: Optional[Dict] = None

class GateStateMachine:
    VALID_TRANSITIONS = {
        GateStatus.PENDING: [GateStatus.IN_PROGRESS],
        GateStatus.IN_PROGRESS: [GateStatus.PASSED, GateStatus.FAILED, GateStatus.TIMEOUT],
        GateStatus.FAILED: [GateStatus.IN_PROGRESS, GateStatus.ESCALATED],
        GateStatus.TIMEOUT: [GateStatus.IN_PROGRESS, GateStatus.ESCALATED],
        GateStatus.PASSED: [],  # Terminal state
        GateStatus.ESCALATED: [GateStatus.IN_PROGRESS],
    }
    
    def __init__(self, db_path: str = None):
        self.states: Dict[str, GateState] = {}
        self.db_path = db_path
        if db_path:
            self._init_db()
            self._load_states()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gate_states (
                gate_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                entry_time TEXT,
                exit_time TEXT,
                failure_count INTEGER DEFAULT 0,
                last_error TEXT,
                metadata TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    
    def transition(self, gate_id: str, target_status: GateStatus, error: str = None):
        current_status = self.get_status(gate_id)
        if not self.can_transition(gate_id, target_status):
            raise ValueError(
                f"Invalid transition: {current_status.value} -> {target_status.value} "
                f"for gate {gate_id}"
            )
        
        state = self.states[gate_id]
        state.status = target_status
        
        now = datetime.now().isoformat()
        if target_status == GateStatus.IN_PROGRESS:
            state.entry_time = now
        elif target_status in [GateStatus.PASSED, GateStatus.FAILED, GateStatus.TIMEOUT]:
            state.exit_time = now
        
        if error:
            state.last_error = error
        
        if target_status == GateStatus.FAILED:
            state.failure_count += 1
        
        self._save_state(gate_id)
```

## Failure Handling Pattern

```python
def handle_failure(self, gate_id: str, error: Exception) -> Dict:
    state = self.state_machine.get_state(gate_id)
    gate_config = self.gates.get(gate_id)
    
    logger.warning("gate_failed", gate_id=gate_id, error=str(error), failure_count=state.failure_count)
    
    # Check current status
    current_status = self.state_machine.get_status(gate_id)
    
    # If not FAILED, transition to FAILED (increments failure_count)
    if current_status != GateStatus.FAILED:
        self.state_machine.transition(gate_id, GateStatus.FAILED, error=str(error))
    else:
        # Already FAILED, manually increment failure_count
        state.failure_count += 1
        state.last_error = str(error)
        self.state_machine._save_state(gate_id)
    
    # Re-fetch state
    state = self.state_machine.get_state(gate_id)
    
    # Check retry limit
    if state.failure_count >= gate_config.max_retries:
        self.escalate_to_owner(gate_id)
        raise GateMaxRetriesError(f"Gate {gate_id} failed {state.failure_count} times")
    
    return {"retry": True, "failure_count": state.failure_count, "error": str(error)}

def escalate_to_owner(self, gate_id: str):
    # Ensure state is FAILED first
    current_status = self.state_machine.get_status(gate_id)
    if current_status != GateStatus.FAILED:
        self.state_machine.transition(gate_id, GateStatus.FAILED)
    
    # Then escalate
    self.state_machine.transition(gate_id, GateStatus.ESCALATED)
    logger.error("gate_escalated", gate_id=gate_id)
```

## Key Pitfalls

1. **PENDING -> ESCALATED is invalid**: Must go through FAILED first
2. **FAILED -> FAILED is invalid**: Check current status before transitioning
3. **PASSED is terminal**: No further transitions allowed
4. **failure_count only increments on FAILED transition**: If already FAILED, manually increment

## Testing Pattern

```python
def test_handle_failure(gate_manager):
    # Must be in IN_PROGRESS state first
    gate_manager.state_machine.transition('test_gate', GateStatus.IN_PROGRESS)
    
    error = Exception("Test error")
    result = gate_manager.handle_failure('test_gate', error)
    
    assert result['failure_count'] == 1

def test_handle_failure_max_retries(gate_manager):
    gate_manager.state_machine.transition('test_gate', GateStatus.IN_PROGRESS)
    
    # Fail up to max_retries-1 times
    for i in range(2):
        gate_manager.handle_failure('test_gate', Exception(f"Error {i}"))
    
    # Next failure should escalate
    with pytest.raises(GateMaxRetriesError):
        gate_manager.handle_failure('test_gate', Exception("Final error"))
```
