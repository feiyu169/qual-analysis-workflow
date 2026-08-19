# Technical Document → HGF Phase Mapping

Verified pattern from P1 fix plan execution (2026-06-29).

## Mapping Rule

When executing a technical document through HGF, map document sections to phases:

| Document Section | HGF Phase | Content |
|------------------|-----------|---------|
| 前置依赖清单 | Phase 0 | Validate all dependencies before any modification |
| 整改方案1 (最高优先级) | Phase 1 | Core functionality fix |
| 整改方案2 | Phase 2 | Infrastructure improvement |
| 整改方案3 | Phase 3 | Validation/compatibility |
| 整改方案4 (最低优先级) | Phase 4 | Cleanup |
| 验收检查清单 | Gate E2E | End-to-end verification |

## Phase Structure

Each phase must have:
1. **Entry criteria**: What must be verified before starting
2. **Exit criteria**: What proves completion
3. **Rollback steps**: How to undo if something breaks
4. **Checkpoint summary**: `[CHECKPOINT] Phase X-Y completed / Phase Z-W pending / Gate E2E pending`

## Pitfalls

- **Phase 4 cleanup may find target already deleted**: Mark as "completed, no action needed" rather than blocking
- **Soft delete before physical delete**: Always backup + tag first, observe for 7 days
- **Config switches for rollback**: Add configuration options that allow instant rollback without code changes

## Example: P1 Fix Plan (2026-06-29)

```
Phase 0: 前置验证 — Wind MCP可用性、income支持、llm_caller调用点
Phase 1: P1-3 Dayu降级策略 — 配置开关+数据标准化+异常保护
Phase 2: P1-4 GBrain清理 — 清单确认+备份+软删除+建索引
Phase 3: P1-1 llm_caller校验 — 渐进式警告+降级
Phase 4: P1-2 备份目录清理 — 目录已不存在，无需执行
Gate E2E: 端到端测试 — 全部功能验证
```

## Todo Integration

```python
todo(todos=[
    {"content": "Phase 0: 前置验证", "id": "phase0", "status": "in_progress"},
    {"content": "Phase 1: 核心修复", "id": "phase1", "status": "pending"},
    {"content": "Phase 2: 基础设施", "id": "phase2", "status": "pending"},
    {"content": "Phase 3: 验证/兼容", "id": "phase3", "status": "pending"},
    {"content": "Phase 4: 清理", "id": "phase4", "status": "pending"},
    {"content": "Gate E2E: 端到端测试", "id": "gate-e2e", "status": "pending"},
])

# Update after each phase
todo(merge=True, todos=[
    {"id": "phase0", "status": "completed"},
    {"id": "phase1", "status": "in_progress"},
])
```
