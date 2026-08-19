# HGF Workflow Defect Patterns (2026-07-11)

## Three Critical Deficiencies Identified

### Deficiency 1: Non-Command Conditions Bypass Verification Engine

**Problem**: `_verify_criteria` only calls `verification_engine.verify()` for `command_types`. All other types (`document_types`, `deploy_types`, `review_types`) only check `result["completed"]` or `result["passed"]`.

**Impact**: 80%+ of quality gates are not independently verified.

**Fix Pattern**:
```python
# Entry condition (result is None): Check predecessor gate status
if result is None:
    predecessor = self._get_predecessor_gate(gate_id, criteria.type)
    if predecessor:
        status = self.state_machine.get_status(predecessor)
        return status == GateStatus.PASSED

# Exit condition (result is not None): Call verification engine
if criteria.verification:
    if not self.verification_engine:
        raise ValueError("Verification engine not set")
    return self.verification_engine.verify(level=criteria.verification, ...)
```

**Key Rule**: Entry conditions check predecessor; exit conditions call engine.

---

### Deficiency 2: Timeout Retry Has No Limit

**Problem**: When a gate times out, it transitions to `TIMEOUT` status and allows retry, but `failure_count` is not incremented and there's no `timeout_count`.

**Fix Pattern**:
1. Add `timeout_count` field to `GateState` dataclass
2. Add `timeout_count` column to database schema
3. Increment `timeout_count` in `_handle_timeout` method
4. Check `timeout_count >= max_retries` before allowing retry

**Database Migration**:
```python
# In _init_db, after CREATE TABLE:
cursor.execute("PRAGMA table_info(gate_states)")
columns = [row[1] for row in cursor.fetchall()]
if 'timeout_count' not in columns:
    cursor.execute('ALTER TABLE gate_states ADD COLUMN timeout_count INTEGER DEFAULT 0')
```

---

### Deficiency 3: Incomplete Concurrency Lock Scope

**Problem**: `execute_gate` uses `asyncio.Lock` but `check_timeout` and `reset_gate` don't use any lock, causing race conditions.

**Fix Pattern**:
```python
class GateManager:
    def __init__(self):
        self._lock = asyncio.Lock()  # Single unified lock
    
    async def execute_gate(self, gate_id, task_func=None):
        async with self._lock:
            return await self._execute_gate_impl(gate_id, task_func)
    
    async def check_timeout(self, gate_id):
        async with self._lock:
            # timeout check logic
    
    async def reset_gate(self, gate_id, force=False):
        async with self._lock:
            self.state_machine.reset_gate(gate_id, force=force)
```

**Key Rule**: All state-modifying methods must use the same lock.

---

## HeavySkill Review Iteration Pattern

**Process**: Document → HeavySkill K=8 Review → Fix → Re-review

**Rounds Observed**: 4-8 rounds typical for complex fixes

**Common Review Findings**:
1. Schema/implementation mismatch
2. Missing error handling paths
3. Concurrency safety issues
4. Database migration gaps

**Anti-pattern**: Submitting code that doesn't match the document. HeavySkill will catch this immediately.

---

## Database Schema Migration Pattern

**Problem**: Adding new columns to existing SQLite tables.

**Solution**:
```python
# Check if column exists
cursor.execute("PRAGMA table_info(table_name)")
columns = [row[1] for row in cursor.fetchall()]
if 'new_column' not in columns:
    cursor.execute('ALTER TABLE table_name ADD COLUMN new_column TYPE DEFAULT value')
```

**Key Rule**: Always check before altering. SQLite doesn't support `IF NOT EXISTS` for ALTER TABLE.

---

## Test Pattern for HGF Fixes

```python
class TestHgfFix:
    def test_fix_works(self):
        """Test the fix works correctly"""
        gm = GateManager(config_path="config/gates.yaml")
        # Setup
        gm.state_machine.add_gate("test")
        gm.state_machine.transition("test", GateStatus.IN_PROGRESS)
        # Execute
        gm._handle_timeout("test")
        # Verify
        state = gm.state_machine.get_state("test")
        assert state.timeout_count == 1
    
    def test_fix_persists(self):
        """Test the fix persists to database"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            gm = GateManager(config_path="config/gates.yaml", db_path=db_path)
            # Execute
            gm._handle_timeout("test")
            # Verify persistence
            gm2 = GateManager(config_path="config/gates.yaml", db_path=db_path)
            state = gm2.state_machine.get_state("test")
            assert state.timeout_count == 1
```
