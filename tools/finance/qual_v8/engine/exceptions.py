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


class WritePipelineError(EngineError):
    """写入管线异常（对标 dayu write_pipeline 异常层级）。"""

    def __init__(self, phase: str, reason: str) -> None:
        self.phase = phase
        self.reason = reason
        super().__init__(f"写入管线 [{phase}] 失败: {reason}")


class RepairRollbackError(WritePipelineError):
    """ADVC 自证失败回滚异常。"""

    def __init__(self, chapter: int, reason: str) -> None:
        self.chapter = chapter
        super().__init__("repair", f"第{chapter}章自证失败回滚: {reason}")


class DataAnchorError(EngineError):
    """数据锚点异常（对标 dayu DataStoreProtocol 异常）。"""

    def __init__(self, key: str, fiscal_year: int | None, reason: str) -> None:
        self.key = key
        self.fiscal_year = fiscal_year
        fy_str = f"FY{fiscal_year}" if fiscal_year else "latest"
        super().__init__(f"数据锚点 [{key}/{fy_str}] 异常: {reason}")
