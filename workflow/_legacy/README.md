# _legacy —— 已归档模块（V3.2.0）

这些模块在 hermes 原环境中曾参与 HGF 设计，但移植到 DSH 后**从未被任何活代码
引用**（只互相引用，或只被文档提及）。按"一次只让一条管线可执行"原则归档于此，
不参与导入、测试与覆盖率统计。**复活条件**写在每个条目里。

| 模块 | 行数 | 当初设计用途 | 为何归档 | 复活条件 |
|------|------|--------------|----------|----------|
| `state_machine.py` | 142 | 门禁生命周期状态机（GateStatus/GateState） | 无活引用；主流程是线性执行 | 阶段 2：生命周期 DAG 接线时复活为 LifecycleManager 基础 |
| `gate_manager.py` | 230 | 基于 gates.yaml 的门禁编排（含 DB 持久化） | 只被 state_machine 引用，二者互锁成孤岛 | 阶段 2：作为 LifecycleManager 的编排实现 |
| `async_state_machine.py` | 149 | 异步版状态机 | 无活引用 | 需要并发门禁时 |
| `async_gate_manager.py` | 303 | 异步版编排 | 无活引用 | 需要并发门禁时 |
| `tdd_verifier.py` | 91 | TDD 证据核验（git 历史测试先于实现） | 无活引用 | 阶段 2.3：复活为准出条件检查器 `tdd_evidence` |
| `verification_engine.py` | 107 | 验证引擎（覆盖率 JSON 提取等） | 无活引用 | 阶段 2.3：检查器复用其 _extract_coverage_json |
| `change_manager.py` | 81 | 变更评估（ChangeRequest/Evaluation） | 无活引用 | 需要变更单跟踪时 |
| `pre_commit_tools.py` | 109 | 提交前检查工具 | 无活引用 | CI/钩子落地时（阶段 3.1） |
| `post_deploy_tools.py` | 121 | 部署后检查工具 | 无活引用 | CI/钩子落地时（阶段 3.1） |

注：`failure_handler.py`（重试/升级）**未归档**——V3.2 阶段 1.2 将把它接线进
GateExecutor。
