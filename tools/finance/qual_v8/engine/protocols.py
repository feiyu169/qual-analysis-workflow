"""
Engine 层协议定义（参照 dayu-agent engine/protocols.py）。

定义 Runner / ToolExecutor 的最小协议，便于测试 Mock。
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMRunnerProtocol(Protocol):
    """LLM Runner 最小协议。

    qual 的 LLM 调用层必须实现此协议。
    """

    def call(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """同步调用 LLM，返回标准信封。

        Args:
            messages: 消息列表。
            model: 模型名（可选，使用默认）。
            temperature: 温度参数。
            max_tokens: 最大 token 数。

        Returns:
            成功: {"ok": True, "value": {"content": "...", "usage": {...}}}
            失败: {"ok": False, "error": "...", "message": "..."}
        """
        ...


@runtime_checkable
class ToolExecutorProtocol(Protocol):
    """工具执行器协议。

    工具注册表中的每个工具必须实现此协议。
    """

    @property
    def name(self) -> str:
        """工具名称。"""
        ...

    @property
    def description(self) -> str:
        """工具描述。"""
        ...

    @property
    def parameters(self) -> dict[str, Any] | None:
        """工具参数 schema（JSON Schema 格式）。"""
        ...

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行工具，返回标准信封。

        Args:
            arguments: 校验后的参数。

        Returns:
            成功: build_success(value)
            失败: build_error(code, message)
        """
        ...
