"""
Qual v9 公共契约层。

所有跨层传递的 frozen dataclass + Protocol 定义在此。
消除 dict[str, Any] 传递，确保类型安全。

设计参照：dayu-agent contracts/ 层（frozen dataclass + lazy import）。
"""
from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .protocols import CheckerProtocol, GateProtocol, RepairerProtocol  # noqa: F401
    from .types import (  # noqa: F401
        AuditDecision,
        ChapterSnapshot,
        ConsistencyIssue,
        DataPoint,
        GateContext,
        GateResult,
        GateState,
        GateStateTransition,
        NumericViolation,
        RepairAction,
        RepairRecord,
        ReviewIssue,
        StructuralViolation,
        WorkflowRunResult,
    )


_EXPORT_MAP: dict[str, tuple[str, str]] = {
    # types
    "GateResult": (".types", "GateResult"),
    "GateState": (".types", "GateState"),
    "GateStateTransition": (".types", "GateStateTransition"),
    "GateContext": (".types", "GateContext"),
    "WorkflowRunResult": (".types", "WorkflowRunResult"),
    "DataPoint": (".types", "DataPoint"),
    "ChapterSnapshot": (".types", "ChapterSnapshot"),
    "ConsistencyIssue": (".types", "ConsistencyIssue"),
    "NumericViolation": (".types", "NumericViolation"),
    "StructuralViolation": (".types", "StructuralViolation"),
    "ReviewIssue": (".types", "ReviewIssue"),
    "RepairAction": (".types", "RepairAction"),
    "RepairRecord": (".types", "RepairRecord"),
    "AuditDecision": (".types", "AuditDecision"),
    # protocols
    "GateProtocol": (".protocols", "GateProtocol"),
    "CheckerProtocol": (".protocols", "CheckerProtocol"),
    "RepairerProtocol": (".protocols", "RepairerProtocol"),
}


def __getattr__(name: str) -> object:
    """按需加载公共契约导出（参照 dayu-agent contracts/__init__.py）。"""
    export = _EXPORT_MAP.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_path, attr_name = export
    module = import_module(module_path, package=__name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
