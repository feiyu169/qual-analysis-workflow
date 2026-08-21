"""门禁插件单元测试（纪律门禁抓违规、命令模板、增量覆盖率解析）"""

import os

import pytest

# 注意：TestQualityPlugin 类名以 Test 开头，直接导入进测试模块会被 pytest
# 当作测试类尝试收集（触发 PytestCollectionWarning），故使用不带 Test 前缀的别名。
from gate_plugins import (
    FailureLogPlugin as FailureLogGate,
)
from gate_plugins import (
    IntegrationProbePlugin as IntegrationProbeGate,
)
from gate_plugins import (
    PytestPlugin as PytestGate,
)
from gate_plugins import (
    TestQualityPlugin as QualityGate,
)
from gate_types import GateConfig, GateExecutionStatus


def _config(**kw):
    base = dict(name="x", tool="t", command="")
    base.update(kw)
    return GateConfig(**base)


def test_test_quality_catches_stub_test(tmp_path):
    wd = str(tmp_path)
    os.makedirs(os.path.join(wd, "tests"))
    with open(os.path.join(wd, "tests", "test_x.py"), "w", encoding="utf-8") as f:
        f.write("def test_stub():\n    pass\n")
    plugin = QualityGate(_config(name="test_quality", tool="test-quality"))
    result = plugin.execute([], wd)
    assert result.status == GateExecutionStatus.FAILED
    assert result.issues_count == 1
    assert "空桩" in result.message


def test_test_quality_passes_real_assertions(tmp_path):
    wd = str(tmp_path)
    os.makedirs(os.path.join(wd, "tests"))
    with open(os.path.join(wd, "tests", "test_y.py"), "w", encoding="utf-8") as f:
        f.write("def test_real():\n    assert 1 + 1 == 2\n")
    plugin = QualityGate(_config(name="test_quality", tool="test-quality"))
    result = plugin.execute([], wd)
    assert result.status == GateExecutionStatus.PASSED


def test_test_quality_passes_unittest_style(tmp_path):
    """V3.3.2（B1 触达）：unittest.TestCase 的 self.assertXxx 应计为断言，非空桩"""
    wd = str(tmp_path)
    os.makedirs(os.path.join(wd, "tests"))
    with open(os.path.join(wd, "tests", "test_u.py"), "w", encoding="utf-8") as f:
        f.write(
            "import unittest\n"
            "class TestU(unittest.TestCase):\n"
            "    def test_x(self):\n"
            "        self.assertTrue(True)\n"
            "        self.assertEqual(1, 1)\n"
        )
    plugin = QualityGate(_config(name="test_quality", tool="test-quality"))
    result = plugin.execute([], wd)
    assert result.status == GateExecutionStatus.PASSED, f"unittest 断言应被识别: {result.message}"


def test_test_quality_handles_multiline_strings(tmp_path):
    """回归：函数体内含列 0 的多行字符串时，不得误判为空桩"""
    wd = str(tmp_path)
    os.makedirs(os.path.join(wd, "tests"))
    with open(os.path.join(wd, "tests", "test_x.py"), "w", encoding="utf-8") as f:
        f.write(
            "def test_parse():\n"
            '    data = """<root>\n'
            "<item>1</item>\n"
            '</root>"""\n'
            '    assert "<item>" in data\n'
        )
    plugin = QualityGate(_config(name="test_quality", tool="test-quality"))
    result = plugin.execute([], wd)
    assert result.status == GateExecutionStatus.PASSED


def test_integration_probe_catches_missing_caller(tmp_path):
    wd = str(tmp_path)
    with open(os.path.join(wd, "calc.py"), "w", encoding="utf-8") as f:
        f.write("def apply_discount(p, d):\n    return p\n")
    plugin = IntegrationProbeGate(
        _config(
            name="integration_probe",
            tool="integration-probe",
            probes=[
                {
                    "name": "discount 已接入",
                    "module": "calc",
                    "symbol": "apply_discount",
                    "usage_pattern": "apply_discount",
                }
            ],
        )
    )
    result = plugin.execute(["calc.py"], wd)
    assert result.status == GateExecutionStatus.FAILED
    assert "无任何调用点" in result.output


def test_integration_probe_passes_with_caller(tmp_path):
    wd = str(tmp_path)
    with open(os.path.join(wd, "calc.py"), "w", encoding="utf-8") as f:
        f.write("def apply_discount(p, d):\n    return p\n")
    with open(os.path.join(wd, "main.py"), "w", encoding="utf-8") as f:
        f.write("from calc import apply_discount\nx = apply_discount(1, 2)\n")
    plugin = IntegrationProbeGate(
        _config(
            name="integration_probe",
            tool="integration-probe",
            probes=[
                {
                    "name": "discount 已接入",
                    "module": "calc",
                    "symbol": "apply_discount",
                    "usage_pattern": "apply_discount",
                }
            ],
        )
    )
    result = plugin.execute(["calc.py"], wd)
    assert result.status == GateExecutionStatus.PASSED


def test_failure_log_plugin_flags_incomplete(tmp_path):
    from failure_log import record_failure

    wd = str(tmp_path)
    record_failure(wd, "unit_test", "MUST_PASS", "测试失败")
    plugin = FailureLogGate(_config(name="failure_log", tool="failure-log"))
    result = plugin.execute([], wd)
    assert result.status == GateExecutionStatus.FAILED


def test_build_command_substitutes_files():
    from gate_plugin import GatePlugin

    class P(GatePlugin):
        verification_levels = {"L1"}

        def execute(self, files, working_dir):
            return None

        def is_available(self):
            return True

    with_template = P(_config(name="x", tool="ruff", command="ruff check {files}"))
    assert (
        with_template._build_command(["a.py", "b.py"], "fallback")
        == "ruff check a.py b.py"
    )

    fallback = P(_config(name="x", tool="ruff", command=""))
    assert fallback._build_command(["a.py"], "ruff check {files}") == "ruff check a.py"


def test_build_argv_expands_files_individually():
    """V3.2.9 修复 F：{files} 展开为独立 argv（路径含空格安全，不经过 shell）"""
    from gate_plugin import GatePlugin

    class P(GatePlugin):
        verification_levels = {"L1"}

        def execute(self, files, working_dir):
            return None

        def is_available(self):
            return True

    with_template = P(_config(name="x", tool="ruff", command="ruff check {files}"))
    assert with_template._build_argv(["a.py", "b.py"], "fallback") == [
        "ruff", "check", "a.py", "b.py",
    ]

    # 路径含空格：作为独立元素保留，不被拆开
    spacey = P(_config(name="x", tool="ruff", command="ruff check {files}"))
    assert spacey._build_argv(["my dir/a.py", "b.py"], "fallback") == [
        "ruff", "check", "my dir/a.py", "b.py",
    ]

    fallback = P(_config(name="x", tool="ruff", command=""))
    assert fallback._build_argv(["a.py"], "ruff check {files}") == [
        "ruff", "check", "a.py",
    ]


def test_run_command_accepts_argv_and_str(tmp_path, monkeypatch):
    """V3.2.9 修复 F：_run_command 兼容 argv 数组与字符串，且 shell=False"""
    from gate_plugin import GatePlugin

    captured = {}

    class P(GatePlugin):
        verification_levels = {"L1"}

        def execute(self, files, working_dir):
            return None

        def is_available(self):
            return True

    plugin = P(_config(name="x", tool="fake", command=""))

    import gate_plugin as _gp

    subprocess_kwargs = {}

    def fake_run(argv, **kw):
        subprocess_kwargs.update(kw)
        captured["argv"] = argv
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(_gp.subprocess, "run", fake_run)
    plugin._run_command(["ruff", "check", "a.py"], str(tmp_path))
    assert captured["argv"] == ["ruff", "check", "a.py"]
    assert subprocess_kwargs.get("shell") is False

    plugin._run_command("ruff check a.py", str(tmp_path))
    assert captured["argv"] == ["ruff", "check", "a.py"]


def test_pytest_changed_coverage_parser(tmp_path):
    wd = str(tmp_path)
    with open(os.path.join(wd, "coverage.xml"), "w", encoding="utf-8") as f:
        f.write("""<?xml version="1.0"?>
<coverage><packages><package><classes>
  <class filename="demo_hgf/calc.py"><lines>
    <line number="1" hits="1"/><line number="2" hits="1"/><line number="3" hits="0"/>
  </lines></class>
  <class filename="other.py"><lines><line number="1" hits="1"/></lines></class>
</classes></package></packages></coverage>""")
    plugin = PytestGate(_config(name="unit_test", tool="pytest"))
    cov = plugin._changed_coverage(wd, ["demo_hgf/calc.py"])
    assert cov == pytest.approx(66.67, abs=0.1)
    assert plugin._changed_coverage(wd, ["missing.py"]) is None


# ── 工具输出解析函数（合成数据锁定解析行为）───────────────────────────────


def test_detect_secrets_parse():
    from gate_plugins import DetectSecretsPlugin

    plugin = DetectSecretsPlugin(_config(name="secret_scan", tool="detect-secrets"))
    out = '{"results": {"a.py": [{"type": "Secret Keyword", "line_number": 3}]}}'
    issues = plugin._parse_secrets_output(out)
    assert len(issues) == 1
    assert issues[0].file == "a.py"
    # fail-loud：畸形 JSON 抛异常（由 _safe_parse 转 ERROR），绝不静默 PASS
    with pytest.raises(Exception):
        plugin._parse_secrets_output("not json")


def test_semgrep_parse():
    from gate_plugins import SemgrepPlugin

    plugin = SemgrepPlugin(_config(name="security_scan", tool="semgrep"))
    out = (
        '{"results": [{"check_id": "python.lang.security", "path": "a.py", '
        '"start": {"line": 5}, "extra": {"severity": "ERROR", "message": "注入"}}]}'
    )
    issues = plugin._parse_semgrep_output(out)
    assert len(issues) == 1
    assert issues[0].rule == "python.lang.security"
    with pytest.raises(Exception):
        plugin._parse_semgrep_output("bad")


def test_safety_parse():
    from gate_plugins import SafetyPlugin

    plugin = SafetyPlugin(_config(name="dependency_scan", tool="safety"))
    out = '[{"package_name": "requests", "vulnerability_id": "V-1", "advisory": "x"}]'
    issues = plugin._parse_safety_output(out)
    assert len(issues) == 1
    assert issues[0].rule == "V-1"
    with pytest.raises(Exception):
        plugin._parse_safety_output("bad")


def test_safety_parse_dict_format():
    """回归（V3.2）：safety 3.x 顶层为字典 {"vulnerabilities": [...]}"""
    from gate_plugins import SafetyPlugin

    plugin = SafetyPlugin(_config(name="dependency_scan", tool="safety"))
    out = ('{"vulnerabilities": [{"package_name": "flask", '
           '"vulnerability_id": "86909", "advisory": "x"}], "remediations": {}}')
    issues = plugin._parse_safety_output(out)
    assert len(issues) == 1
    assert issues[0].rule == "86909"
    assert plugin._parse_safety_output('{"vulnerabilities": []}') == []


def test_checkov_parse():
    from gate_plugins import CheckovPlugin

    plugin = CheckovPlugin(_config(name="iac_scan", tool="checkov"))
    out = (
        '{"results": {"terraform": {"failed_checks": [{"check_id": "CKV_AWS_1", '
        '"file_path": "main.tf", "file_line_range": [10], '
        '"check": {"name": "S3 公网访问"}}]}}}'
    )
    issues = plugin._parse_checkov_output(out)
    assert len(issues) == 1
    assert issues[0].rule == "CKV_AWS_1"
    with pytest.raises(Exception):
        plugin._parse_checkov_output("bad")


def test_checkov_parse_new_list_format():
    """回归（V3.1）：checkov 3.x 顶层为数组，必须解析出 failed_checks"""
    from gate_plugins import CheckovPlugin

    plugin = CheckovPlugin(_config(name="iac_scan", tool="checkov"))
    out = (
        '[{"check_type": "terraform", "summary": {}, "url": "", "results": {'
        '"passed_checks": [], '
        '"failed_checks": [{"check_id": "CKV_AWS_19", "check_name": "加密", '
        '"file_path": "main.tf", "file_line_range": [1, 3]}], '
        '"skipped_checks": []}}]'
    )
    issues = plugin._parse_checkov_output(out)
    assert len(issues) == 1
    assert issues[0].rule == "CKV_AWS_19"
    assert issues[0].line == 1


def test_get_version():
    from gate_plugins import RuffPlugin

    plugin = RuffPlugin(_config(name="static_analysis", tool="ruff"))
    assert plugin.get_version() is not None


# ── fail-loud 假通过防线（V3.2）：工具输出畸形 → ERROR，绝不静默 PASS ───────


class _FakeResult:
    def __init__(self, stdout, returncode=0):
        self.stdout = stdout
        self.returncode = returncode


@pytest.mark.parametrize(
    "plugin_factory, tool",
    [
        ("detect-secrets", "secret_scan"),
        ("semgrep", "security_scan"),
        ("safety", "dependency_scan"),
        ("checkov", "iac_scan"),
    ],
)
def test_fail_loud_on_malformed_output(tmp_path, monkeypatch, plugin_factory, tool):
    from importlib import import_module

    plugin_cls = getattr(
        import_module("gate_plugins"),
        {
            "detect-secrets": "DetectSecretsPlugin",
            "semgrep": "SemgrepPlugin",
            "safety": "SafetyPlugin",
            "checkov": "CheckovPlugin",
        }[plugin_factory],
    )
    plugin = plugin_cls(_config(name=tool, tool=plugin_factory, command=""))
    monkeypatch.setattr(
        plugin, "_run_command", lambda cmd, wd: _FakeResult("this is not json {")
    )
    result = plugin.execute(["a.py"], str(tmp_path))
    assert result.status == GateExecutionStatus.ERROR
    assert "解析失败" in result.message


def test_fail_loud_empty_output(tmp_path, monkeypatch):
    """工具无输出（崩溃/被杀）也必须 ERROR，不得当成'0 问题通过'"""
    from gate_plugins import DetectSecretsPlugin

    plugin = DetectSecretsPlugin(_config(name="secret_scan", tool="detect-secrets"))
    monkeypatch.setattr(
        plugin, "_run_command", lambda cmd, wd: _FakeResult("", returncode=1)
    )
    result = plugin.execute(["a.py"], str(tmp_path))
    assert result.status == GateExecutionStatus.ERROR


def test_safe_parse_helper():
    from gate_plugins import DetectSecretsPlugin

    plugin = DetectSecretsPlugin(_config(name="secret_scan", tool="detect-secrets"))
    issues, error = plugin._safe_parse(plugin._parse_secrets_output, '{"results": {}}')
    assert error is None
    assert issues == []
    issues2, error2 = plugin._safe_parse(plugin._parse_secrets_output, "{bad")
    assert issues2 == []
    assert error2 is not None
    assert "解析" in error2


# ── V3.2 生态门禁：格式 / 依赖固定 / 文档结构 ───────────────────────────────


def test_format_check_fails_on_unformatted(tmp_path):
    from gate_plugins import FormatCheckPlugin

    wd = str(tmp_path)
    with open(os.path.join(wd, "a.py"), "w", encoding="utf-8") as f:
        f.write("def f(  x):\n    return x\n")
    plugin = FormatCheckPlugin(_config(name="format_check", tool="format-check"))
    result = plugin.execute(["a.py"], wd)
    assert result.status == GateExecutionStatus.FAILED
    assert "格式" in result.message


def test_format_check_passes_on_formatted(tmp_path):
    from gate_plugins import FormatCheckPlugin

    wd = str(tmp_path)
    with open(os.path.join(wd, "a.py"), "w", encoding="utf-8") as f:
        f.write("def hello():\n    return 1\n")
    plugin = FormatCheckPlugin(_config(name="format_check", tool="format-check"))
    result = plugin.execute(["a.py"], wd)
    assert result.status == GateExecutionStatus.PASSED


def test_pin_check_flags_unpinned(tmp_path):
    from gate_plugins import PinCheckPlugin

    wd = str(tmp_path)
    with open(os.path.join(wd, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write("requests>=2.0\nnumpy==1.26.0\n")
    plugin = PinCheckPlugin(_config(name="pin_check", tool="pin-check"))
    result = plugin.execute([], wd)
    assert result.status == GateExecutionStatus.FAILED
    assert result.issues_count == 1
    assert "requests" in result.issues[0].message


def test_pin_check_passes_when_all_pinned(tmp_path):
    from gate_plugins import PinCheckPlugin

    wd = str(tmp_path)
    with open(os.path.join(wd, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write("numpy==1.26.0\n# comment line\n")
    plugin = PinCheckPlugin(_config(name="pin_check", tool="pin-check"))
    result = plugin.execute([], wd)
    assert result.status == GateExecutionStatus.PASSED


def test_docs_check_requires_readme(tmp_path):
    from gate_plugins import DocsCheckPlugin

    plugin = DocsCheckPlugin(_config(name="docs_check", tool="docs-check"))
    result = plugin.execute([], str(tmp_path))
    assert result.status == GateExecutionStatus.FAILED
    assert "README.md 不存在" in result.output


def test_docs_check_required_sections(tmp_path):
    from gate_plugins import DocsCheckPlugin

    wd = str(tmp_path)
    with open(os.path.join(wd, "README.md"), "w", encoding="utf-8") as f:
        f.write("# Demo\n\n## 安装\npip install demo\n\n" + "内容" * 100 + "\n")
    plugin = DocsCheckPlugin(
        _config(
            name="docs_check",
            tool="docs-check",
            probes=[{"name": "安装"}, {"name": "使用"}],
        )
    )
    result = plugin.execute([], wd)
    assert result.status == GateExecutionStatus.FAILED
    assert "使用" in result.output
    with open(os.path.join(wd, "README.md"), "a", encoding="utf-8") as f:
        f.write("\n## 使用\ndemo run\n")
    result2 = plugin.execute([], wd)
    assert result2.status == GateExecutionStatus.PASSED
