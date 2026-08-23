"""
参数校验器（参照 dayu-agent engine/argument_validator.py）。

基于 JSON Schema 对工具参数做校验与强制转换：
- 深度限制检查
- 字符串长度 / 数组大小限制
- 按 schema 类型做强制类型转换
- 必填字段与默认值填充
"""
from __future__ import annotations

from typing import Any

from .tool_result import build_error


class ArgumentValidator:
    """工具参数校验与强制转换器。

    Attributes:
        MAX_STRING_LENGTH: 单个字符串参数最大长度。
        MAX_ARRAY_ITEMS: 单个数组参数最大元素数。
        MAX_DEPTH: 参数嵌套最大深度。
    """

    MAX_STRING_LENGTH: int = 4096
    MAX_ARRAY_ITEMS: int = 1000
    MAX_DEPTH: int = 8

    def validate_and_coerce(
        self,
        arguments: Any,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """基于 schema 对 arguments 做校验/规整/默认值填充。

        Args:
            arguments: LLM 传入的参数（应为 dict）。
            parameters: 工具 schema 中 function.parameters 部分。None 时仅做通用限制。

        Returns:
            校验成功: {"ok": True, "arguments": coerced_dict}
            校验失败: {"ok": False, "error": ..., "message": ..., "hint": ...}
        """
        if not isinstance(arguments, dict):
            return build_error(
                "invalid_argument",
                "arguments 必须是对象",
                hint="请传入 JSON 对象格式的参数",
            )

        depth = self._calculate_depth(arguments)
        if depth > self.MAX_DEPTH:
            return build_error(
                "invalid_argument",
                f"arguments 结构过深（{depth} > {self.MAX_DEPTH}）",
                hint="请减少参数嵌套层级",
            )

        if not isinstance(parameters, dict):
            issues = self._check_generic_limits(arguments)
            if issues:
                return build_error("invalid_argument", "arguments 超出限制", hint=str(issues))
            return {"ok": True, "arguments": arguments}

        ok, coerced, issues = self._coerce_value(arguments, parameters, path="$")
        if not ok:
            return build_error("invalid_argument", "arguments 校验失败", hint=str(issues))
        return {"ok": True, "arguments": coerced}

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _calculate_depth(self, value: Any, current: int = 0) -> int:
        """计算嵌套深度。"""
        if isinstance(value, dict):
            if not value:
                return current
            return max(self._calculate_depth(v, current + 1) for v in value.values())
        if isinstance(value, list):
            if not value:
                return current
            return max(self._calculate_depth(v, current + 1) for v in value)
        return current

    def _check_generic_limits(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        """无 schema 时的通用限制检查。"""
        issues = []
        for key, value in self._flatten_values(arguments):
            if isinstance(value, str) and len(value) > self.MAX_STRING_LENGTH:
                issues.append({"path": key, "reason": "string_too_long", "max": self.MAX_STRING_LENGTH})
            if isinstance(value, list) and len(value) > self.MAX_ARRAY_ITEMS:
                issues.append({"path": key, "reason": "array_too_long", "max": self.MAX_ARRAY_ITEMS})
        return issues

    def _flatten_values(self, obj: Any, prefix: str = "$") -> list[tuple[str, Any]]:
        """递归展平 dict 为 (path, value) 列表。"""
        result = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                path = f"{prefix}.{k}"
                result.append((path, v))
                result.extend(self._flatten_values(v, path))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                path = f"{prefix}[{i}]"
                result.append((path, v))
                result.extend(self._flatten_values(v, path))
        return result

    def _coerce_value(
        self,
        value: Any,
        schema: dict[str, Any],
        path: str,
    ) -> tuple[bool, Any, list[dict[str, Any]]]:
        """递归校验+强制转换。返回 (ok, coerced_value, issues)。"""
        issues: list[dict[str, Any]] = []
        schema_type = schema.get("type")

        if schema_type == "object":
            if not isinstance(value, dict):
                issues.append({"path": path, "reason": "type_mismatch", "expected": "object"})
                return False, value, issues
            properties = schema.get("properties", {})
            required = set(schema.get("required", []))
            coerced = {}
            for key, prop_schema in properties.items():
                if key in value:
                    ok, coerced_val, sub_issues = self._coerce_value(
                        value[key], prop_schema, f"{path}.{key}"
                    )
                    issues.extend(sub_issues)
                    if ok:
                        coerced[key] = coerced_val
                elif key in required:
                    if "default" in prop_schema:
                        coerced[key] = prop_schema["default"]
                    else:
                        issues.append({"path": f"{path}.{key}", "reason": "missing_required"})
            # 保留 schema 未定义的额外字段
            for key in value:
                if key not in properties:
                    coerced[key] = value[key]
            return len(issues) == 0, coerced, issues

        elif schema_type == "array":
            if not isinstance(value, list):
                issues.append({"path": path, "reason": "type_mismatch", "expected": "array"})
                return False, value, issues
            if len(value) > self.MAX_ARRAY_ITEMS:
                issues.append({"path": path, "reason": "array_too_long", "max": self.MAX_ARRAY_ITEMS})
                return False, value, issues
            items_schema = schema.get("items")
            if items_schema:
                coerced = []
                for i, item in enumerate(value):
                    ok, coerced_item, sub_issues = self._coerce_value(
                        item, items_schema, f"{path}[{i}]"
                    )
                    issues.extend(sub_issues)
                    coerced.append(coerced_item if ok else item)
                return len(issues) == 0, coerced, issues
            return True, value, issues

        elif schema_type == "string":
            if isinstance(value, str):
                if len(value) > self.MAX_STRING_LENGTH:
                    issues.append({"path": path, "reason": "string_too_long", "max": self.MAX_STRING_LENGTH})
                    return False, value, issues
                return True, value, issues
            # 强制转换
            return True, str(value), issues

        elif schema_type in ("number", "integer"):
            if isinstance(value, (int, float)):
                if schema_type == "integer" and not isinstance(value, int):
                    return True, int(value), issues
                return True, value, issues
            try:
                coerced = int(value) if schema_type == "integer" else float(value)
                return True, coerced, issues
            except (ValueError, TypeError):
                issues.append({"path": path, "reason": "type_mismatch", "expected": schema_type})
                return False, value, issues

        elif schema_type == "boolean":
            if isinstance(value, bool):
                return True, value, issues
            return True, bool(value), issues

        # 未知类型，原样返回
        return True, value, issues
