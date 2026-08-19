# Qual v8.4 非侵入式整合模式 (Verified 2026-08-08)

## 核心教训

**用户纠正**："与现有的workflow集成？是说现在的qual和workflow不是同一个事情吗"

**关键规则**：新组件必须作为现有workflow的内部依赖，不能创建独立系统。

---

## 整合架构

```
workflow.py (唯一的qual流程入口)
    │
    ├── Step 1-7 (原有逻辑不变)
    │
    └── qual_v8/ (内部依赖，不独立运行)
        ├── workflow_context.py  ← 非侵入式挂载
        ├── mode_manager.py      ← 渐进式激活
        ├── step_gate_mapping.py ← Step/Gate映射
        ├── core/                ← 核心组件
        │   ├── state_machine.py
        │   ├── audit_logger.py
        │   ├── circuit_breaker.py
        │   ├── error_classifier.py
        │   └── supervisor.py
        ├── gates/               ← Gate实现
        ├── monitoring/          ← 监控告警
        └── security/            ← 安全合规
```

---

## 三阶段整合路径

### Phase 1: 非侵入式挂载

在workflow.py中注入WorkflowContext，默认shadow模式（只记录不阻断）：

```python
# workflow.py 开始处
try:
    from .qual_v8.workflow_context import get_workflow_context, QualConfig
    qual_config = QualConfig(mode="shadow")
    qual_ctx = get_workflow_context(qual_config)
    qual_ctx.initialize(str(uuid.uuid4()))
except Exception as e:
    qual_ctx = None
    logger.warning(f"[Qual] WorkflowContext初始化失败（非阻断）: {e}")

# workflow.py 结束处
if qual_ctx:
    qual_ctx.finalize()
    qual_summary = qual_ctx.get_state_summary()
```

### Phase 2: 功能对标

Step/Gate映射表：

| workflow.py Step | qual_v8 Gate |
|------------------|-------------|
| Step 1.5: 自动获取财报 | Gate 0 |
| Step 1: 类型推断 | Gate 1 |
| Step 2: 数据收集 | Gate 2 |
| Step 3: 逐章写作 | Gate 3 |
| Step 4: 审计修复 | Gate 4 |
| Step 4.5: 质量增强 | Gate 5 |
| Step 5: 综合结论 | Gate 6 |
| Step 6/7: 记忆/问题转化 | Gate 7 |

### Phase 3: 渐进式激活

通过环境变量控制模式：

```bash
QUAL_MODE=shadow   # 仅记录，不阻断
QUAL_MODE=soft     # 告警，不阻断
QUAL_MODE=enforce  # 阻断
```

---

## WorkflowContext钩子模式

```python
class WorkflowContext:
    def on_step_start(self, step_name, step_num=None):
        """Step开始时的钩子（非侵入式）"""
        if self._audit_logger:
            self._audit_logger.log(self.run_id, step_num, f"step_started:{step_name}", {})
        if self._state_machine and step_num is not None:
            self._state_machine.transition_gate(step_num, GateState.RUNNING)

    def on_step_end(self, step_name, step_num=None, passed=True, details=None):
        """Step结束时的钩子（非侵入式）"""
        if self._audit_logger:
            self._audit_logger.log(self.run_id, step_num, f"step_completed:{step_name}", {})
        if self._state_machine and step_num is not None:
            new_state = GateState.PASSED if passed else GateState.FAILED
            self._state_machine.transition_gate(step_num, new_state)
        # 第三方监督（仅记录，不阻断）
        if self._supervisor and step_num is not None:
            compliance_result = self._supervisor.check_gate(step_num, execution_log)
            if not compliance_result.passed:
                logger.warning(f"[Qual] Step {step_name} 合规性检查未通过")
```

---

## Pitfall: 创建平行系统

- **症状**: 新增的组件独立于现有workflow运行，有自己的入口和配置
- **根因**: 未理解"整合"的含义，把新组件当作独立系统设计
- **规则**: 
  - 新组件必须是现有workflow的内部依赖
  - 删除所有独立入口（CLI、__main__、API路由）
  - 所有调用统一指向workflow.py的入口函数
  - 目录可下沉为 `workflow/_qual_v8/`

---

## HeavySkill审查结论（K=8, 2026-08-08）

> 该整合方案总体正确可行，但必须采用"渐进式增强、非侵入式挂载"的方式实施，否则会破坏现有功能。

**核心原则**：原有步骤的业务逻辑完全不动，新组件仅作为观察、记录、可选的检查层附属运行，且默认行为与原流程等价。

**审查维度**：
1. 整合方案是否正确？ ✅ 正确
2. 是否会破坏现有功能？ ⚠️ 存在破坏可能，但可完全避免
3. 如何确保qual流程唯一？ 物理唯一+调用唯一+代码约束
4. 如何确保所有实现的功能不变？ 功能映射矩阵+等价性验证+回归测试
