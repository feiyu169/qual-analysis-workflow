"""
Qual v9 Engine 层入口。

提供工具基础设施 + Gate 执行引擎 + 影子运行框架。
参照 dayu-agent engine/ 层，精简为 qual 需要的核心组件。
"""
from .argument_validator import ArgumentValidator
from .events import (
    EventCollector,
    QualEvent,
    QualEventType,
    checker_warning,
    done_event,
    error_event,
    gate_complete,
    gate_degraded,
    gate_failed,
    gate_start,
    repair_applied,
)
from .exceptions import (
    BudgetExceededError,
    ConfigError,
    EngineError,
    ToolArgumentError,
    ToolError,
    ToolExecutionError,
    ToolNotFoundError,
)
from .gate_dag import GateDAG
from .protocols import LLMRunnerProtocol, ToolExecutorProtocol
from .run_lifecycle import RunLifecycle
from .tool_registry import ToolRegistry
from .tool_result import (
    build_error,
    build_success,
    get_error_code,
    get_error_message,
    get_hint,
    get_value,
    is_tool_success,
    project_for_llm,
    validate_tool_result,
)

__all__ = [  # noqa: RUF022 — grouped by module for readability
    # tool_result
    "build_success",
    "build_error",
    "is_tool_success",
    "get_error_code",
    "get_error_message",
    "get_value",
    "get_hint",
    "validate_tool_result",
    "project_for_llm",
    # argument_validator
    "ArgumentValidator",
    # events
    "QualEventType",
    "QualEvent",
    "EventCollector",
    "gate_start",
    "gate_complete",
    "gate_failed",
    "gate_degraded",
    "checker_warning",
    "repair_applied",
    "error_event",
    "done_event",
    # protocols
    "LLMRunnerProtocol",
    "ToolExecutorProtocol",
    # exceptions
    "EngineError",
    "ConfigError",
    "ToolError",
    "ToolNotFoundError",
    "ToolExecutionError",
    "ToolArgumentError",
    "BudgetExceededError",
    # tool_registry
    "ToolRegistry",
    # gate_dag + run_lifecycle
    "GateDAG",
    "RunLifecycle",
]
