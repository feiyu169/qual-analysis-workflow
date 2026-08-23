"""
Qual v9 工具结果信封（参照 dayu-agent engine/tool_result.py）。

统一工具结果格式：装信封（build_success/build_error）、拆信封（is_tool_success/get_value）、
LLM 投影（project_for_llm）。确保 Runner/Agent/Trace 对结果的理解完全一致。

设计原则：
- 所有工具返回统一信封格式，消除自由 dict 传递
- LLM 投影零嵌套，LLM 可直接区分成功/失败/截断
"""
from __future__ import annotations

import json
from typing import Any

# ============================================================
# 装信封
# ============================================================

def build_success(
    value: Any,
    *,
    truncation: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建统一的工具成功结果信封。

    Args:
        value: 工具返回的业务数据。
        truncation: 可选截断信息。
        meta: 可选元信息。

    Returns:
        {"ok": True, "value": value, ...}
    """
    result: dict[str, Any] = {"ok": True, "value": value}
    if truncation:
        result["truncation"] = truncation
    if meta:
        result["meta"] = meta
    return result


def build_error(
    code: str,
    message: str,
    *,
    hint: str = "",
    meta: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """构建统一的工具失败结果信封。

    Args:
        code: 错误码。
        message: 人类可读错误说明。
        hint: LLM 可执行的恢复建议（可选）。
        meta: 可选元信息。
        **extra: 附加上下文。

    Returns:
        {"ok": False, "error": code, "message": message, ...}
    """
    result: dict[str, Any] = {"ok": False, "error": code, "message": message}
    if hint:
        result["hint"] = hint
    if extra:
        result.update(extra)
    if meta:
        result["meta"] = meta
    return result


# ============================================================
# 拆信封
# ============================================================

def is_tool_success(result: Any) -> bool:
    """判断工具结果是否真正成功（ok=True 且有 value）。"""
    if not isinstance(result, dict):
        return False
    return result.get("ok") is True and "value" in result


def get_error_code(result: Any) -> str | None:
    """提取错误码；成功结果返回 None。"""
    if not isinstance(result, dict) or result.get("ok") is not False:
        return None
    code = result.get("error")
    return code.strip() if isinstance(code, str) and code.strip() else None


def get_error_message(result: Any) -> str | None:
    """提取错误消息；成功结果返回 None。"""
    if not isinstance(result, dict) or result.get("ok") is not False:
        return None
    msg = result.get("message")
    return msg.strip() if isinstance(msg, str) and msg.strip() else None


def get_value(result: Any) -> Any | None:
    """提取成功结果的业务数据；失败返回 None。"""
    if not isinstance(result, dict):
        return None
    if result.get("ok") is not True or "value" not in result:
        return None
    return result.get("value")


def get_hint(result: Any) -> str | None:
    """提取恢复建议；无 hint 返回 None。"""
    if not isinstance(result, dict):
        return None
    hint = result.get("hint")
    return hint.strip() if isinstance(hint, str) and hint.strip() else None


# ============================================================
# 校验
# ============================================================

def validate_tool_result(result: Any) -> str | None:
    """校验工具结果是否符合信封格式。

    Returns:
        None 表示合法；否则返回错误说明。
    """
    if not isinstance(result, dict):
        return "tool result must be dict"
    ok = result.get("ok")
    if not isinstance(ok, bool):
        return 'tool result must contain boolean field "ok"'
    if ok:
        if "value" not in result:
            return 'successful tool result must contain field "value"'
        return None
    error = result.get("error")
    if not isinstance(error, str) or not error.strip():
        return 'failed tool result must contain non-empty string field "error"'
    message = result.get("message")
    if not isinstance(message, str) or not message.strip():
        return 'failed tool result must contain non-empty string field "message"'
    return None


# ============================================================
# LLM 投影（扁平化，零嵌套）
# ============================================================

def _make_json_safe(value: object) -> Any:
    """递归将任意值转换为 JSON-safe 结构。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (bytes, bytearray)):
        return {"content_base64": __import__("base64").b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, (tuple, list)):
        return [_make_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted([_make_json_safe(item) for item in value], key=lambda x: json.dumps(x, default=str))
    if isinstance(value, dict):
        return {str(k): _make_json_safe(v) for k, v in value.items()}
    return str(value)


def project_for_llm(
    result: dict[str, Any],
    *,
    budget: int | None = None,
) -> dict[str, Any]:
    """将内部信封投影为 LLM 最优的扁平 JSON。

    投影规则：
    1. ok=False → {"error": code, "message": msg, "hint": hint}
    2. ok=True, value is dict → {**value}
    3. ok=True, value is non-dict → {"content": value}
    4. budget 非 None → 追加 {"tool_calls_remaining": budget}
    """
    if contract_error := validate_tool_result(result):
        proj: dict[str, Any] = {"error": "invalid_result", "message": contract_error}
        if budget is not None:
            proj["tool_calls_remaining"] = budget
        return proj

    if result.get("ok") is not True:
        proj = {"error": result.get("error", "UNKNOWN")}
        if msg := result.get("message"):
            proj["message"] = msg
        if hint := result.get("hint"):
            proj["hint"] = hint
        if budget is not None:
            proj["tool_calls_remaining"] = budget
        return proj

    # 成功投影
    value = result.get("value")
    if isinstance(value, dict):
        safe = _make_json_safe(value)
        proj = safe if isinstance(safe, dict) else {"content": safe}
    else:
        proj = {"content": _make_json_safe(value)}

    if budget is not None:
        proj["tool_calls_remaining"] = budget
    return proj
