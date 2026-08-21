"""tool_runner 共享工具执行测试（V3.3-R2，架构评审修复 D/E）。

验证：
- split_command 正确拆分命令字符串（引号保留、Windows 路径兼容）；
- safe_run 用 argv 数组 + shell=False（无 shell 解释）；
- lifecycle 检查器（_check_static/_check_tool_scan）经 tool_runner 执行。
"""

import tool_runner


def test_split_command_basic():
    assert tool_runner.split_command("ruff check a.py") == [
        "ruff",
        "check",
        "a.py",
    ]


def test_split_command_keeps_quotes():
    argv = tool_runner.split_command('semgrep --config="p/r2c-ci" --json .')
    assert "--config=p/r2c-ci" in argv  # 引号被去除，argv 语义正确
    assert "." in argv


def test_split_command_empty():
    assert tool_runner.split_command("") == []
    assert tool_runner.split_command("   ") == []


def test_safe_run_uses_shell_false(tmp_path, monkeypatch):
    """safe_run 必须 shell=False + argv 数组（消除 shell 解释）"""
    captured = {}

    def fake_run(argv, **kw):
        captured["argv"] = argv
        captured["shell"] = kw.get("shell", None)

        class R:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return R()

    monkeypatch.setattr(tool_runner.subprocess, "run", fake_run)
    tool_runner.safe_run(["ruff", "check", "."], str(tmp_path), timeout=10)
    assert captured["argv"] == ["ruff", "check", "."]
    assert captured["shell"] is False


def test_safe_run_utf8_encoding(tmp_path, monkeypatch):
    captured = {}

    def fake_run(argv, **kw):
        captured.update(kw)

        class R:
            returncode = 0
            stdout = "中文输出"
            stderr = ""

        return R()

    monkeypatch.setattr(tool_runner.subprocess, "run", fake_run)
    tool_runner.safe_run(["echo", "hi"], str(tmp_path))
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"


def test_check_tool_available():
    assert tool_runner.check_tool_available("python") is True
    assert tool_runner.check_tool_available("definitely-no-such-tool-xyz") is False


def test_lifecycle_static_uses_tool_runner(tmp_path, monkeypatch):
    """_check_static 经 tool_runner（argv 数组）执行"""
    import lifecycle

    captured = {}

    def fake_safe_run(argv, cwd, timeout=120):
        captured["argv"] = argv
        captured["shell_invoked"] = False

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(tool_runner, "safe_run", fake_safe_run)
    ok, issues = lifecycle._check_static({}, str(tmp_path), None)
    assert ok is True
    assert captured["argv"] == ["ruff", "check", "."]


def test_lifecycle_tool_scan_uses_tool_runner(tmp_path, monkeypatch):
    """_check_tool_scan 经 tool_runner 拆分命令 + 安全执行"""
    import lifecycle

    monkeypatch.setattr(tool_runner, "check_tool_available", lambda tool: True)
    captured = {}

    def fake_safe_run(argv, cwd, timeout=120):
        captured["argv"] = argv

        class R:
            returncode = 0
            stdout = "{}"
            stderr = ""

        return R()

    monkeypatch.setattr(tool_runner, "safe_run", fake_safe_run)
    ok, issues = lifecycle._check_tool_scan(
        {"id": "gate_2_1"},
        str(tmp_path),
        None,
        tool="semgrep",
        command="semgrep --config=p/r2c-ci --json .",
        label="SAST",
    )
    assert ok is True, issues
    assert captured["argv"] == ["semgrep", "--config=p/r2c-ci", "--json", "."]
