"""Qual v9 Engine 层单元测试。

覆盖：tool_result（装信封/拆信封/LLM 投影）、argument_validator、events、tool_registry。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pytest

from finance.qual_v8.engine import (
    ArgumentValidator,
    EventCollector,
    QualEventType,
    ToolRegistry,
    build_error,
    build_success,
    checker_warning,
    gate_complete,
    gate_start,
    get_hint,
    get_value,
    is_tool_success,
    project_for_llm,
    validate_tool_result,
)

# ============================================================
# tool_result 测试
# ============================================================

class TestToolResult:
    def test_build_success_basic(self):
        result = build_success({"revenue": 767.20})
        assert result["ok"] is True
        assert result["value"] == {"revenue": 767.20}

    def test_build_error_basic(self):
        result = build_error("not_found", "工具不存在", hint="检查工具名")
        assert result["ok"] is False
        assert result["error"] == "not_found"
        assert result["hint"] == "检查工具名"

    def test_is_tool_success_true(self):
        assert is_tool_success(build_success("data"))

    def test_is_tool_success_false(self):
        assert not is_tool_success(build_error("e", "msg"))
        assert not is_tool_success("not a dict")
        assert not is_tool_success({"ok": True})  # missing value

    def test_get_value(self):
        assert get_value(build_success(42)) == 42
        assert get_value(build_error("e", "msg")) is None

    def test_get_hint(self):
        assert get_hint(build_error("e", "msg", hint="do this")) == "do this"
        assert get_hint(build_success("v")) is None

    def test_validate_tool_result_success(self):
        assert validate_tool_result(build_success("v")) is None

    def test_validate_tool_result_error(self):
        assert validate_tool_result({"ok": False, "error": "", "message": "m"}) is not None
        assert validate_tool_result({"ok": False, "error": "e", "message": ""}) is not None

    def test_project_for_llm_success_dict(self):
        result = build_success({"a": 1, "b": 2})
        proj = project_for_llm(result)
        assert proj["a"] == 1
        assert proj["b"] == 2

    def test_project_for_llm_success_string(self):
        result = build_success("hello")
        proj = project_for_llm(result)
        assert proj["content"] == "hello"

    def test_project_for_llm_error(self):
        result = build_error("E", "msg", hint="try this")
        proj = project_for_llm(result)
        assert proj["error"] == "E"
        assert proj["hint"] == "try this"

    def test_project_for_llm_with_budget(self):
        proj = project_for_llm(build_success("v"), budget=5)
        assert proj["tool_calls_remaining"] == 5


# ============================================================
# argument_validator 测试
# ============================================================

class TestArgumentValidator:
    def setup_method(self):
        self.v = ArgumentValidator()

    def test_not_dict_rejected(self):
        result = self.v.validate_and_coerce("not a dict", {})
        assert result["ok"] is False

    def test_depth_exceeded(self):
        deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": {"j": "x"}}}}}}}}}}
        result = self.v.validate_and_coerce(deep)
        assert result["ok"] is False

    def test_no_schema_generic_limits(self):
        result = self.v.validate_and_coerce({"key": "value"})
        assert result["ok"] is True

    def test_schema_string_coercion(self):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
        result = self.v.validate_and_coerce({"name": "test"}, schema)
        assert result["ok"] is True
        assert result["arguments"]["name"] == "test"

    def test_schema_missing_required(self):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
        result = self.v.validate_and_coerce({}, schema)
        assert result["ok"] is False

    def test_schema_default_value(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string", "default": "anon"}},
            "required": ["name"],
        }
        result = self.v.validate_and_coerce({}, schema)
        assert result["ok"] is True
        assert result["arguments"]["name"] == "anon"

    def test_schema_number_coercion(self):
        schema = {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]}
        result = self.v.validate_and_coerce({"count": "42"}, schema)
        assert result["ok"] is True
        assert result["arguments"]["count"] == 42


# ============================================================
# events 测试
# ============================================================

class TestEvents:
    def test_gate_start(self):
        e = gate_start(3, "章节写作")
        assert e.type == QualEventType.GATE_START
        assert e.gate_num == 3

    def test_gate_complete(self):
        e = gate_complete(3, 85.0, 12.5)
        assert e.data["score"] == 85.0

    def test_checker_warning(self):
        e = checker_warning(4, 5, "裸数字幻觉")
        assert e.chapter_num == 5

    def test_event_collector(self):
        c = EventCollector()
        c.emit(gate_start(0, "验证"))
        c.emit(gate_complete(0, 100, 1.0))
        assert len(c.events) == 2
        assert len(c.get_events_for_gate(0)) == 2
        assert len(c.get_events_by_type(QualEventType.GATE_START)) == 1

    def test_event_to_dict(self):
        e = gate_start(1, "test")
        d = e.to_dict()
        assert d["type"] == "gate_start"
        assert d["gate_num"] == 1


# ============================================================
# tool_registry 测试
# ============================================================

class MockTool:
    """Mock 工具实现 ToolExecutorProtocol。"""
    def __init__(self, name: str, desc: str = "test tool"):
        self._name = name
        self._desc = desc

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._desc

    @property
    def parameters(self) -> dict | None:
        return {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

    def execute(self, arguments: dict) -> dict:
        return build_success({"result": f"processed {arguments.get('query', '')}"})


class TestToolRegistry:
    def setup_method(self):
        self.registry = ToolRegistry()

    def test_register_and_list(self):
        self.registry.register(MockTool("search"))
        assert self.registry.has("search")
        assert "search" in self.registry.list_tools()

    def test_execute_success(self):
        self.registry.register(MockTool("search"))
        result = self.registry.execute("search", {"query": "小鹏"})
        assert result["ok"] is True
        assert "小鹏" in result["value"]["result"]

    def test_execute_not_found(self):
        result = self.registry.execute("unknown", {})
        assert result["ok"] is False
        assert result["error"] == "tool_not_found"

    def test_execute_bad_args(self):
        self.registry.register(MockTool("search"))
        result = self.registry.execute("search", {"wrong_field": "x"})
        assert result["ok"] is False

    def test_get_schema(self):
        self.registry.register(MockTool("search"))
        schema = self.registry.get_schema("search")
        assert schema["name"] == "search"
        assert schema["parameters"]["type"] == "object"

    def test_unregister(self):
        self.registry.register(MockTool("search"))
        self.registry.unregister("search")
        assert not self.registry.has("search")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
