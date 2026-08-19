# HGF 架构级缺陷清单（HeavySkill 审查确认）

> 发现日期：2026-07-11
> 审查方法：HeavySkill K=4 多轮审查（3 轮）
> 状态：✅ 全部修复，329/329 测试通过
> 实施：async_state_machine.py + async_gate_manager.py

---

## 第一批：架构级缺陷（HeavySkill v1 审查）

### A1: 非命令类条件未调用验证引擎（质量门禁虚化）

**位置**：`_verify_criteria` 方法

**问题**：
- `command_types` 调用 `verification_engine.verify()` ✅
- `document_types`、`deploy_types`、`review_types` 只检查 `result` 字典 ❌
- 配置中明确指定的 `verification: L1` 被完全忽略

**影响**：16 个 Gate 中，12 个 Gate 的出口条件未调用验证引擎。

**修复**：统一验证逻辑，所有类型都优先调用验证引擎（仅出口条件）。

### A2: 超时重试无上限（无限循环风险）

**位置**：超时处理逻辑

**问题**：超时后转移到 TIMEOUT 并允许重新执行，但不计入 `failure_count`，反复超时将无限重试。

**修复**：添加 `timeout_count` 字段，超过 `max_retries` 后升级。

### A3: 并发锁范围不完整（竞争条件风险）

**位置**：`execute_gate` 和 `check_timeout`

**问题**：
- `execute_gate` 使用 `asyncio.Lock` ✅
- `check_timeout` 和 `reset_gate` 无锁 ❌

**修复**：统一使用细粒度锁（Gate 级别）。

---

## 第二批：异步架构缺陷（HeavySkill v2-v3 审查）

### A4: 异步事件循环阻塞（致命）

**问题**：`threading.Lock` + 同步 `sqlite3` 阻塞 asyncio 事件循环。

**修复**：改用 `aiosqlite` + `asyncio.Lock`。

### A5: 超时重试与锁冲突（致命）

**问题**：超时后原协程仍持有 `asyncio.Lock`，新重试无法获取锁。

**修复**：使用 `asyncio.wait_for` + `task.cancel()` 实现超时取消。

### A6: SQLite 并发安全

**问题**：未启用 WAL 模式，并发读写可能触发 `database is locked`。

**修复**：
```python
await cursor.execute("PRAGMA journal_mode=WAL")
await cursor.execute("PRAGMA busy_timeout=5000")
```

### A7: 全局锁串行化所有 Gate

**问题**：单一 `asyncio.Lock` 导致所有 Gate 完全串行执行。

**修复**：改为 Gate 级别细粒度锁，允许无依赖 Gate 并行执行。

### A8: 数据库 Schema 不一致

**问题**：`CREATE TABLE` 语句缺少 `timeout_count` 列，但 `_save_state` 引用该列。

**修复**：添加自动迁移逻辑。

### A9: `_load_states` 解包遗漏字段

**问题**：查询返回 9 个字段，解包只用 8 个变量，导致 `ValueError`。

### A10: `_load_states` 构造遗漏参数

**问题**：解包正确但构造 `GateState` 时遗漏 `timeout_count` 参数。

### A11: `handle_failure` 和 `escalate_to_owner` 应为私有方法

**问题**：公开方法可被外部调用，绕过锁保护。

**修复**：改为 `_handle_failure` 和 `_escalate_to_owner`。

### A12: 事务原子性不足

**问题**：`add_gate` 和 `reset_gate` 采用"先内存、后持久化"模式。

**修复**：统一为"先写数据库，成功后再更新内存"。

### A13: 超时监控无容错

**问题**：后台 `_monitor` 循环中若抛出未捕获异常，整个监控任务崩溃。

**修复**：添加 `try/except` 和 `CancelledError` 处理。
