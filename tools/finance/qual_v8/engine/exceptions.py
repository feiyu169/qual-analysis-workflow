"""
Engine 异常层级（参照 dayu-agent engine/exceptions.py）。

分层异常便于精确捕获：
- EngineError: 基类
  - ConfigError: 配置错误（必须中断）
  - ToolError: 工具错误
    - ToolNotFoundError: 工具未注册
    - ToolExecutionError: 工具执行失败
    - ToolArgumentError: 参数校验失败
  - BudgetExceededError: 预算超限
  - TimeoutError: 超时
"""
from __future__ import annotations


class EngineError(Exception):
    """Engine 基类异常。"""


class ConfigError(EngineError):
    """配置错误（必须中断，不可重试）。"""


class ToolError(EngineError):
    """工具相关错误基类。"""


class ToolNotFoundError(ToolError):
    """工具未注册。"""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"工具未注册: {tool_name}")


class ToolExecutionError(ToolError):
    """工具执行失败。"""

    def __init__(self, tool_name: str, error_code: str, message: str) -> None:
        self.tool_name = tool_name
        self.error_code = error_code
        self.message = message
        super().__init__(f"工具 {tool_name} 执行失败 [{error_code}]: {message}")


class ToolArgumentError(ToolError):
    """参数校验失败。"""

    def __init__(self, tool_name: str, issues: list[dict]) -> None:
        self.tool_name = tool_name
        self.issues = issues
        super().__init__(f"工具 {tool_name} 参数校验失败: {issues}")


class BudgetExceededError(EngineError):
    """预算超限（LLM 调用次数/token 用尽）。"""

    def __init__(self, resource: str, limit: int, actual: int) -> None:
        self.resource = resource
        self.limit = limit
        self.actual = actual
        super().__init__(f"{resource} 预算超限: {actual} > {limit}")


class TimeoutError(EngineError):
    """执行超时。"""

    def __init__(self, operation: str, timeout_seconds: float) -> None:
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        super().__init__(f"{operation} 超时 ({timeout_seconds}s)")
