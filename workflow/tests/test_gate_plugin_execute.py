"""真实工具执行测试：ruff / detect-secrets / pytest 门禁的真实运行路径。

这些测试要求本机已安装 ruff、detect-secrets、pytest（见 hgf 技能环境说明），
对应 L1 门禁的"真实执行"验证（禁止文件存在即通过）。
"""

import os

from gate_plugins import DetectSecretsPlugin, PytestPlugin, RuffPlugin
from gate_types import GateConfig, GateExecutionStatus


def _config(name, tool, **kw):
    base = dict(name=name, tool=tool, command="", timeout=120)
    base.update(kw)
    return GateConfig(**base)


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_ruff_passes_clean_file(tmp_path):
    wd = str(tmp_path)
    _write(os.path.join(wd, "a.py"), "def hello():\n    return 1\n")
    plugin = RuffPlugin(_config("static_analysis", "ruff"))
    result = plugin.execute(["a.py"], wd)
    assert result.status == GateExecutionStatus.PASSED


def test_ruff_fails_on_unused_import(tmp_path):
    wd = str(tmp_path)
    _write(os.path.join(wd, "a.py"), "import os\n")
    plugin = RuffPlugin(_config("static_analysis", "ruff"))
    result = plugin.execute(["a.py"], wd)
    assert result.status == GateExecutionStatus.FAILED
    assert result.issues_count >= 1


def test_detect_secrets_passes_clean_file(tmp_path):
    wd = str(tmp_path)
    _write(os.path.join(wd, "a.py"), "API_URL = 'https://example.com'\n")
    plugin = DetectSecretsPlugin(_config("secret_scan", "detect-secrets"))
    result = plugin.execute(["a.py"], wd)
    assert result.status == GateExecutionStatus.PASSED


def test_pytest_plugin_end_to_end(tmp_path):
    wd = str(tmp_path)
    _write(os.path.join(wd, "calc.py"), ("def add(a, b):\n    return a + b\n"))
    _write(
        os.path.join(wd, "tests", "test_calc.py"),
        ("from calc import add\ndef test_add():\n    assert add(1, 2) == 3\n"),
    )
    _write(
        os.path.join(wd, "pyproject.toml"),
        ('[tool.pytest.ini_options]\npythonpath = ["."]\n'),
    )
    plugin = PytestPlugin(_config("unit_test", "pytest", coverage_min=80))
    result = plugin.execute(["calc.py"], wd)
    assert result.status == GateExecutionStatus.PASSED, result.output
    assert result.coverage == 100.0


def test_pytest_plugin_fails_on_test_failure(tmp_path):
    wd = str(tmp_path)
    _write(os.path.join(wd, "calc.py"), ("def add(a, b):\n    return a + b\n"))
    _write(
        os.path.join(wd, "tests", "test_calc.py"),
        ("def test_add():\n    assert add(1, 2) == 4\n"),
    )
    _write(
        os.path.join(wd, "pyproject.toml"),
        ('[tool.pytest.ini_options]\npythonpath = ["."]\n'),
    )
    plugin = PytestPlugin(_config("unit_test", "pytest", coverage_min=80))
    result = plugin.execute(["calc.py"], wd)
    assert result.status == GateExecutionStatus.FAILED
