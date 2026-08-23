"""
工具注册表（参照 dayu-agent engine/tool_registry.py）。

管理工具注册、schema 查询、参数校验、执行分发。
所有工具通过注册表接入，Gate 内部不直接调用工具函数。
"""
from __future__ import annotations

import logging
from typing import Any

from .argument_validator import ArgumentValidator
from .protocols import ToolExecutorProtocol
from .tool_result import build_error

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表。

    用法：
        registry = ToolRegistry()
        registry.register(my_tool)
        result = registry.execute("my_tool", {"arg": "value"})
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolExecutorProtocol] = {}
        self._validator = ArgumentValidator()

    def register(self, tool: ToolExecutorProtocol) -> None:
        """注册工具。"""
        self._tools[tool.name] = tool
        logger.info(f"工具注册: {tool.name}")

    def unregister(self, name: str) -> None:
        """注销工具。"""
        self._tools.pop(name, None)

    def has(self, name: str) -> bool:
        """检查工具是否已注册。"""
        return name in self._tools

    def list_tools(self) -> list[str]:
        """列出所有已注册工具名。"""
        return list(self._tools.keys())

    def get_schema(self, name: str) -> dict[str, Any] | None:
        """获取工具参数 schema。"""
        tool = self._tools.get(name)
        if tool is None:
            return None
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }

    def get_all_schemas(self) -> list[dict[str, Any]]:
        """获取所有工具的 schema 列表（用于 LLM prompt 注入）。"""
        return [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in self._tools.values()
        ]

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行工具（含参数校验）。

        Args:
            name: 工具名。
            arguments: 工具参数。

        Returns:
            标准信封格式结果。
        """
        tool = self._tools.get(name)
        if tool is None:
            return build_error(
                "tool_not_found",
                f"工具未注册: {name}",
                hint=f"可用工具: {', '.join(self._tools.keys())}",
            )

        # 参数校验
        validation = self._validator.validate_and_coerce(arguments, tool.parameters)
        if validation.get("ok") is not True:
            return validation

        coerced_args = validation.get("arguments", arguments)

        # 执行
        try:
            result = tool.execute(coerced_args)
            # 校验返回格式
            from .tool_result import validate_tool_result
            if err := validate_tool_result(result):
                logger.warning(f"工具 {name} 返回非法格式: {err}")
                return build_error("invalid_result", f"工具返回非法格式: {err}")
            return result
        except Exception as e:
            logger.error(f"工具 {name} 执行异常: {e}")
            return build_error(
                "tool_execution_error",
                f"工具执行异常: {e}",
                hint="请检查工具参数和依赖",
            )
