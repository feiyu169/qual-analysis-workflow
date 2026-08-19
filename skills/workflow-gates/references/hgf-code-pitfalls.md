# HGF 代码审查坑点（2026-07-11 实战）

## 1. 准出条件验证绕过（P0）

**问题**：`_verify_criteria` 对 `document_types`、`deploy_types` 入口条件直接返回 True，不检查前驱 Gate 状态。

**根因**：设计意图是"前驱 Gate 已通过则视为产出物已就绪"，但实现时未检查前驱状态。

**修复**：
```python
if result is None:
    # 入口条件：检查前驱 Gate 状态
    predecessor = self._get_predecessor_gate(gate_id, criteria.type)
    if predecessor:
        status = await self.state_machine.get_status(predecessor)
        return status == GateStatus.PASSED
    return False  # 无映射时默认不通过
```

## 2. Gate 间无依赖关系（P0）

**问题**：`GateConfig` 无 `depends_on` 字段，`execute_gate` 未检查前置 Gate。

**修复**：
```python
@dataclass
class GateConfig:
    depends_on: List[str] = None  # 新增

async def execute_gate(self, gate_id: str, ...):
    for dep in gate_config.depends_on or []:
        dep_status = await self.state_machine.get_status(dep)
        if dep_status != GateStatus.PASSED:
            raise GateEntryError(f"前置 Gate {dep} 未完成")
```

## 3. 失败处理重复计数（P0）

**问题**：`execute_gate` 转移 FAILED 后，`handle_failure` 又做一次 `FAILED → IN_PROGRESS → FAILED`。

**修复**：`handle_failure` 不再重复转移，只检查重试次数。

## 4. 超时 Off-by-one（P1）

**问题**：`_handle_timeout` 在转移 TIMEOUT **之前**检查 `timeout_count >= max_retries`，导致实际允许次数比配置多 1。

**修复**：先转移 TIMEOUT（计数+1），再检查是否超过限制。

## 5. 非法状态转移 TIMEOUT → FAILED（P0）

**问题**：`_escalate_to_owner` 尝试 `TIMEOUT → FAILED`，但 `VALID_TRANSITIONS` 不允许。

**修复**：`TIMEOUT → ESCALATED` 直接升级。

## 6. 时区混淆（P1）

**问题**：`datetime.now(timezone.utc)`（aware）与 `datetime.fromisoformat(...)`（naive）相减抛 TypeError。

**修复**：
```python
entry_time = datetime.fromisoformat(state.entry_time)
if entry_time.tzinfo is None:
    entry_time = entry_time.replace(tzinfo=timezone.utc)
```

## 7. 数据库迁移缺失（P1）

**问题**：旧数据库无 `timeout_count` 列，`_load_states` 解包失败。

**修复**：
```python
await cursor.execute("PRAGMA table_info(gate_states)")
columns = [row[1] async for row in cursor]
if 'timeout_count' not in columns:
    await cursor.execute('ALTER TABLE gate_states ADD COLUMN timeout_count INTEGER DEFAULT 0')
```

## 8. 状态机暴露（P2）

**问题**：`state_machine` 是公开属性，可直接操作绕过所有检查。

**建议**：改为私有属性 `_state_machine`，通过方法访问。

## 9. `_verify_criteria` 硬编码（P2）

**问题**：类型分类硬编码在代码中，可维护性差。

**建议**：改为配置驱动或注册机制。

## 10. TOCTOU 竞争（P2）

**问题**：依赖检查在 gate-lock 外部，依赖 Gate 可能在检查通过后被重置。

**缓解**：PASSED 是终态不可变，实际风险低。
