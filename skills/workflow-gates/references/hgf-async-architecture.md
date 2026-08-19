# HGF 异步架构改造模式

> 日期：2026-07-11
> 状态：✅ 已实施，329/329 测试通过
> 文件：async_state_machine.py、async_gate_manager.py

---

## 架构问题（HeavySkill 识别）

| # | 问题 | 说明 |
|---|------|------|
| 1 | 异步事件循环阻塞 | `threading.Lock` + 同步 `sqlite3` 阻塞 asyncio |
| 2 | 超时重试与锁冲突 | 超时后原协程仍持有锁，新重试无法获取 |
| 3 | SQLite 并发安全 | 未启用 WAL 模式 |
| 4 | 全局锁串行化 | 所有 Gate 完全串行执行 |

---

## 解决方案

### 1. 异步状态机（aiosqlite）

```python
import aiosqlite

class AsyncGateStateMachine:
    def __init__(self, db_path):
        self._lock = asyncio.Lock()
        self._db: Optional[aiosqlite.Connection] = None
    
    async def initialize(self):
        if self.db_path:
            self._db = await aiosqlite.connect(self.db_path)
            await self._init_db()
            await self._load_states()
    
    async def _init_db(self):
        async with self._db.cursor() as cursor:
            await cursor.execute("PRAGMA journal_mode=WAL")
            await cursor.execute("PRAGMA busy_timeout=5000")
            # ... 创建表 + 迁移
            await self._db.commit()
```

### 2. 细粒度锁（Gate 级别）

```python
class AsyncGateManager:
    def __init__(self):
        self._gate_locks: Dict[str, asyncio.Lock] = {}
    
    def _get_gate_lock(self, gate_id: str) -> asyncio.Lock:
        if gate_id not in self._gate_locks:
            self._gate_locks[gate_id] = asyncio.Lock()
        return self._gate_locks[gate_id]
    
    async def execute_gate(self, gate_id, task_func=None):
        # 依赖检查（无锁）
        for dep in gate_config.depends_on:
            dep_status = await self.state_machine.get_status(dep)
            if dep_status != GateStatus.PASSED:
                raise GateEntryError(...)
        
        # Gate 级别锁
        gate_lock = self._get_gate_lock(gate_id)
        async with gate_lock:
            return await self._execute_gate_impl(gate_id, task_func)
```

### 3. 超时任务取消

```python
async def execute_gate(self, gate_id, task_func=None):
    async with gate_lock:
        task = asyncio.create_task(_execute())
        self._running_tasks[gate_id] = task
        
        try:
            result = await asyncio.wait_for(task, timeout=gate_config.timeout)
            return result
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await self._handle_timeout(gate_id)
            raise GateTimeoutError(...)
        finally:
            self._running_tasks.pop(gate_id, None)
```

### 4. 原子写入（先数据库后内存）

```python
async def transition(self, gate_id, target_status, error=None):
    async with self._lock:
        # 计算新值
        ...
        
        # 先写数据库
        if self._db:
            try:
                async with self._db.cursor() as cursor:
                    await cursor.execute(...)
                    await self._db.commit()
            except Exception as e:
                logger.error("transition_db_error", ...)
                raise  # 不更新内存
        
        # 再更新内存
        state.status = target_status
        ...
```

### 5. 超时监控

```python
class AsyncGateManager:
    async def start_timeout_monitor(self, interval=60):
        async def _monitor():
            while True:
                try:
                    await asyncio.sleep(interval)
                    await self._check_all_timeouts()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("timeout_monitor_error", error=str(e))
        
        self._timeout_task = asyncio.create_task(_monitor())
    
    async def stop_timeout_monitor(self):
        if self._timeout_task:
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass
```

### 6. 状态恢复（重启后）

```python
async def initialize(self):
    await self.state_machine.initialize()
    await self._recover_timeout_gates()

async def _recover_timeout_gates(self):
    all_states = await self.state_machine.get_all_states()
    for gate_id, state in all_states.items():
        if state.status == GateStatus.IN_PROGRESS:
            gate_config = self.gates.get(gate_id)
            if gate_config and state.entry_time:
                entry_time = datetime.fromisoformat(state.entry_time)
                if entry_time.tzinfo is None:
                    entry_time = entry_time.replace(tzinfo=timezone.utc)
                timeout = timedelta(seconds=gate_config.timeout)
                if datetime.now(timezone.utc) - entry_time > timeout:
                    await self.state_machine.transition(gate_id, GateStatus.TIMEOUT)
```

---

## 锁顺序（防死锁）

```
gate_lock (Gate 级别)
    └── state_machine._lock (状态机全局锁)
```

**规则**：必须先获取 `gate_lock`，再获取 `state_machine._lock`。所有路径必须遵循同一顺序。

---

## 私有方法约束

`_handle_failure` 和 `_escalate_to_owner` 必须为私有方法，仅在持有 Gate 锁时调用。防止外部绕过锁保护。

---

## 数据库迁移

```python
async def _init_db(self):
    async with self._db.cursor() as cursor:
        await cursor.execute("PRAGMA table_info(gate_states)")
        columns = [row[1] async for row in cursor]
        if 'timeout_count' not in columns:
            await cursor.execute('ALTER TABLE gate_states ADD COLUMN timeout_count INTEGER DEFAULT 0')
```

---

## 测试模式

```python
@pytest_asyncio.fixture
async def gm(config_path, db_path):
    gm = AsyncGateManager(config_path=config_path, db_path=db_path)
    await gm.initialize()
    yield gm
    await gm.close()  # 必须关闭避免 event loop 警告
```

---

## 依赖

```bash
pip install aiosqlite
```
