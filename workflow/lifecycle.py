"""HGF 生命周期管理器（V3.2.0 / V3.3-R3）。

V3.3-R3（架构专家评审修复 B）：原 970 行"上帝模块"拆分为三模块——
- lifecycle_dag.py：DAG 状态机（准入/准出/推进/reopen，~180 行）
- lifecycle_checkers.py：26 种准出检查器 + 注册表（~630 行）
- lifecycle_metrics.py：流程度量 + DAG 接电（~190 行）

本文件为 re-export 壳：**外部 API 完全不变**（workflow_cli / hgf_bridge /
mcp_server / 测试均 `import lifecycle` 后调用同名函数）。

分层（与工具矩阵层 mcp-gates.yaml 的职责划分）：
- 生命周期层管"现在该干什么"：gate 的准入（依赖完成）→ 执行准出检查器 → done；
- 工具矩阵层管"当前步骤怎么验"：GateExecutor 按等级跑工具门禁。

状态持久化在 `<working_dir>/.hgf/lifecycle.json`。
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ── 拆分模块（V3.3-R3）────────────────────────────────────────────────────
try:
    from . import lifecycle_checkers as _checkers
    from . import lifecycle_dag as _dag
    from . import lifecycle_metrics as _metrics
except ImportError:
    import lifecycle_checkers as _checkers
    import lifecycle_dag as _dag
    import lifecycle_metrics as _metrics

# ── 异常（保持兼容）───────────────────────────────────────────────────────
LifecycleError = _dag.LifecycleError

# ── DAG 状态机（re-export）───────────────────────────────────────────────
load_gates = _dag.load_gates
build_dag = _dag.build_dag
state_path = _dag.state_path
save_state = _dag.save_state
load_state = _dag.load_state
status = _dag.status
advance = _dag.advance
reopen = _dag.reopen

# ── 准出检查器（re-export）───────────────────────────────────────────────
# V3.3.1（复审共识 A：收敛内部暴露）：不再 re-export 内部注册表/常量
# （_CHECKERS / _DOC_SEMANTIC_REQUIREMENTS / _read_text——这些是 checkers
#  的实现细节，调用方应直连 lifecycle_checkers）；_check_* 函数是准出
# 检查器的稳定入口，保留 re-export 供测试/外部调用。
check_exit_criteria = _checkers.check_exit_criteria
_check_document = _checkers._check_document
_check_document_semantic = _checkers._check_document_semantic
_check_review = _checkers._check_review
_check_unit_tests = _checkers._check_unit_tests
_check_integration_tests = _checkers._check_integration_tests
_check_static = _checkers._check_static
_check_health = _checkers._check_health
_check_tool_scan = _checkers._check_tool_scan
_check_semgrep = _checkers._check_semgrep
_check_dependency = _checkers._check_dependency
_check_checkov = _checkers._check_checkov
_check_dast = _checkers._check_dast
_check_tdd_evidence = _checkers._check_tdd_evidence

# ── 度量 + DAG 接电（re-export）───────────────────────────────────────────
MATRIX_TO_EXIT = _metrics.MATRIX_TO_EXIT
record_matrix_evidence = _metrics.record_matrix_evidence
auto_advance = _metrics.auto_advance
metrics = _metrics.metrics

# V3.3.1（复审共识 A）：__all__ 声明稳定公开 API——`from lifecycle import *`
# 只导入此列表；内部 _check_* 仍可通过 lifecycle._check_* 显式访问（测试用），
# 但注册表/常量/工具函数不再暴露。
__all__ = [
    "LifecycleError",
    "load_gates",
    "build_dag",
    "state_path",
    "save_state",
    "load_state",
    "status",
    "advance",
    "reopen",
    "check_exit_criteria",
    "record_matrix_evidence",
    "auto_advance",
    "metrics",
    "MATRIX_TO_EXIT",
]
