"""门禁执行器单元测试（启动校验、验证契约、失败自动记录、V3.2 重试/升级）"""

import os

import pytest
import yaml

from failure_handler import FailureHandler
from gate_executor import GateExecutor, GateExecutorError
from gate_plugin import GatePlugin
from gate_types import GateExecutionStatus, GateResult


class _FakePlugin(GatePlugin):
    """测试用假插件：按预设结果序列执行"""

    verification_levels = frozenset({"L1"})
    _results: list = []
    calls = 0

    def execute(self, files, working_dir):
        type(self).calls += 1
        return type(self)._results.pop(0)

    def is_available(self):
        return True


def _fake_error_result(message):
    return GateResult(
        name="fake_gate",
        tool="fake",
        status=GateExecutionStatus.ERROR,
        exit_code=-1,
        issues_count=0,
        message=message,
    )


def _fake_passed_result():
    return GateResult(
        name="fake_gate",
        tool="fake",
        status=GateExecutionStatus.PASSED,
        exit_code=0,
        issues_count=0,
        message="ok",
    )


def _fake_failed_result():
    return GateResult(
        name="fake_gate",
        tool="fake",
        status=GateExecutionStatus.FAILED,
        exit_code=1,
        issues_count=1,
        message="测试失败",
    )


def _executor_with_fake(tmp_path):
    # 先注册假插件（GateExecutor 构造时做启动校验，工具必须在构造前可解析）
    import gate_plugins

    gate_plugins.GATE_PLUGINS["fake"] = _FakePlugin

    path = os.path.join(str(tmp_path), "gates.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {
                "gates": {
                    "must_pass": [
                        {
                            "name": "fake_gate",
                            "tool": "fake",
                            "verification": "L1",
                            "timeout": 10,
                        }
                    ]
                },
                "level_gates": {
                    "L1": {
                        "must_pass": ["fake_gate"],
                        "should_pass": [],
                        "optional": [],
                    }
                },
            },
            f,
            allow_unicode=True,
        )
    executor = GateExecutor(path)
    # 测试用零延迟快速重试
    executor.failure_handler = FailureHandler(
        {
            "gate_retry_delay": 0,
            "gate_max_retries": 3,
        }
    )
    return executor


def _write_config(tmp_path, gates, level_gates):
    path = os.path.join(str(tmp_path), "gates.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {"gates": gates, "level_gates": level_gates}, f, allow_unicode=True
        )
    return path


def test_missing_config_raises():
    with pytest.raises(GateExecutorError):
        GateExecutor("C:/definitely/not/exists/gates.yaml")


def test_unknown_gate_name_rejected(tmp_path):
    path = _write_config(
        tmp_path,
        {"must_pass": [{"name": "static_analysis", "tool": "ruff"}]},
        {"L1": {"must_pass": ["ghost_gate"], "should_pass": [], "optional": []}},
    )
    with pytest.raises(GateExecutorError, match="ghost_gate"):
        GateExecutor(path)


def test_unknown_tool_rejected(tmp_path):
    path = _write_config(
        tmp_path,
        {"must_pass": [{"name": "mystery", "tool": "no-such-tool"}]},
        {"L1": {"must_pass": ["mystery"], "should_pass": [], "optional": []}},
    )
    with pytest.raises(GateExecutorError, match="no-such-tool"):
        GateExecutor(path)


def test_verification_contract_rejects_undeclared_level(tmp_path):
    wd = str(tmp_path)
    with open(os.path.join(wd, "a.py"), "w", encoding="utf-8") as f:
        f.write("def hello():\n    return 1\n")
    # ruff 插件仅支持 L1，声明 L3 → 执行结果为 ERROR（验证级别不匹配）
    path = _write_config(
        tmp_path,
        {
            "must_pass": [
                {
                    "name": "static_analysis",
                    "tool": "ruff",
                    "command": "ruff check {files}",
                    "verification": "L3",
                    "timeout": 30,
                }
            ]
        },
        {"L1": {"must_pass": ["static_analysis"], "should_pass": [], "optional": []}},
    )
    executor = GateExecutor(path)
    # 验证契约失败是 ERROR（被 classify 为可重试），测试用零延迟单次执行提速
    executor.failure_handler = FailureHandler(
        {
            "gate_retry_delay": 0,
            "gate_max_retries": 1,
        }
    )
    report = executor.execute_gates("L1", files=["a.py"], working_dir=wd)
    result = report.results[0]
    assert result.status == GateExecutionStatus.ERROR
    assert "验证级别不匹配" in result.message


def test_failure_auto_recorded(tmp_path):
    wd = str(tmp_path)
    # 含 F401（未使用 import）→ ruff 失败 → 自动写入失败记录
    with open(os.path.join(wd, "a.py"), "w", encoding="utf-8") as f:
        f.write("import os\n")
    path = _write_config(
        tmp_path,
        {
            "must_pass": [
                {
                    "name": "static_analysis",
                    "tool": "ruff",
                    "command": "ruff check {files}",
                    "verification": "L1",
                    "timeout": 30,
                }
            ]
        },
        {"L1": {"must_pass": ["static_analysis"], "should_pass": [], "optional": []}},
    )
    executor = GateExecutor(path)
    report = executor.execute_gates("L1", files=["a.py"], working_dir=wd)
    assert report.failed == 1
    log = os.path.join(wd, ".hgf", "failures.jsonl")
    assert os.path.exists(log)
    from failure_log import load_failures

    entries = load_failures(wd)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["gate"] == "static_analysis"
    assert entry["root_cause"] is None


def test_failure_log_self_failure_not_recorded(tmp_path):
    """V3.3.2 S1：failure_log 门禁自身的失败不得写入 failures.jsonl（防自锁雪崩）。

    历史 bug：failure_log 因"记录不完整"FAIL 时，其自身失败也被 record_failure
    追加（且必然缺 root_cause/fix）→ 下次检查更多不完整 → 指数爆炸（232 条/196
    未解决）。修复后 failure_log 自身失败只出现在 runs.jsonl 历史与报告里。
    """
    import gate_plugins
    from gate_types import Issue

    class _FakeFailureLogPlugin(GatePlugin):
        verification_levels = frozenset({"L1"})

        def execute(self, files, working_dir):
            return GateResult(
                name="failure_log",
                tool="failure-log",
                status=GateExecutionStatus.FAILED,
                exit_code=1,
                issues_count=2,
                message="2 条失败记录不完整",
                issues=[
                    Issue(
                        severity="error", message="缺 root_cause", rule="failure-log"
                    ),
                    Issue(severity="error", message="缺 fix", rule="failure-log"),
                ],
            )

        def is_available(self):
            return True

    gate_plugins.GATE_PLUGINS["failure-log"] = _FakeFailureLogPlugin
    path = _write_config(
        tmp_path,
        {
            "must_pass": [
                {
                    "name": "failure_log",
                    "tool": "failure-log",
                    "verification": "L1",
                    "timeout": 10,
                }
            ]
        },
        {"L1": {"must_pass": ["failure_log"], "should_pass": [], "optional": []}},
    )
    executor = GateExecutor(path)
    report = executor.execute_gates("L1", files=["a.py"], working_dir=str(tmp_path))
    assert report.failed == 1
    assert report.must_pass_failed == ["failure_log"]
    # 关键断言：failure_log 自身失败不产生新失败记录
    from failure_log import load_failures

    assert load_failures(str(tmp_path)) == []


# ── V3.2 重试/升级接线 ─────────────────────────────────────────────────────


def test_retryable_error_is_retried_then_passes(tmp_path):
    _FakePlugin._results = [
        _fake_error_result("执行错误: Command timed out"),
        _fake_passed_result(),
    ]
    _FakePlugin.calls = 0
    executor = _executor_with_fake(tmp_path)
    report = executor.execute_gates("L1", files=["a.py"], working_dir=str(tmp_path))
    assert _FakePlugin.calls == 2
    assert report.results[0].status == GateExecutionStatus.PASSED
    assert report.success


def test_non_retryable_failure_not_retried(tmp_path):
    _FakePlugin._results = [_fake_failed_result()]
    _FakePlugin.calls = 0
    executor = _executor_with_fake(tmp_path)
    report = executor.execute_gates("L1", files=["a.py"], working_dir=str(tmp_path))
    assert _FakePlugin.calls == 1
    assert report.results[0].status == GateExecutionStatus.FAILED


def test_escalation_after_repeated_failures(tmp_path):
    _FakePlugin._results = [_fake_error_result("执行错误: timed out")] * 5
    _FakePlugin.calls = 0
    executor = _executor_with_fake(tmp_path)
    report = executor.execute_gates("L1", files=["a.py"], working_dir=str(tmp_path))
    # 最多重试 3 次（attempt 1-3），不再重试后保持 ERROR
    assert _FakePlugin.calls == 3
    result = report.results[0]
    assert result.status == GateExecutionStatus.ERROR
    assert any("冻结流程" in s for s in result.suggestions)


def test_must_pass_error_blocks_pipeline(tmp_path):
    """V3.2 修复回归：MUST_PASS 门禁 ERROR（如解析失败）必须阻断流水线，
    不得假绿灯（此前只统计 FAILED 状态）"""
    _FakePlugin._results = [_fake_error_result("工具输出解析失败，拒绝判定: bad json")]
    _FakePlugin.calls = 0
    executor = _executor_with_fake(tmp_path)
    report = executor.execute_gates("L1", files=["a.py"], working_dir=str(tmp_path))
    assert report.results[0].status == GateExecutionStatus.ERROR
    assert "fake_gate" in report.must_pass_failed
    assert report.success is False
    assert report.exit_code == 1


# ── V3.2.5 工具版本契约 ─────────────────────────────────────────────────────


class _VersionedFake(_FakePlugin):
    """带版本契约的假插件"""

    min_version = "2.0.0"
    max_version = "4.0.0"
    version = "3.0.0"

    def get_version(self):
        return self.version


def _versioned_executor(tmp_path):
    import gate_plugins

    gate_plugins.GATE_PLUGINS["fake"] = _VersionedFake
    path = os.path.join(str(tmp_path), "gates.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {
                "gates": {
                    "must_pass": [
                        {
                            "name": "fake_gate",
                            "tool": "fake",
                            "verification": "L1",
                            "timeout": 10,
                        }
                    ]
                },
                "level_gates": {
                    "L1": {
                        "must_pass": ["fake_gate"],
                        "should_pass": [],
                        "optional": [],
                    }
                },
            },
            f,
            allow_unicode=True,
        )
    executor = GateExecutor(path)
    executor.failure_handler = FailureHandler(
        {"gate_retry_delay": 0, "gate_max_retries": 1}
    )
    return executor


def test_version_contract_ok_in_range(tmp_path):
    _VersionedFake._results = [_fake_passed_result()]
    _VersionedFake.version = "3.5.0"
    executor = _versioned_executor(tmp_path)
    report = executor.execute_gates("L1", files=["a.py"], working_dir=str(tmp_path))
    assert report.results[0].status == GateExecutionStatus.PASSED


def test_version_contract_blocks_above_max(tmp_path):
    _VersionedFake._results = [_fake_passed_result()]
    _VersionedFake.version = "5.0.0"  # ≥ max_version 4.0.0
    executor = _versioned_executor(tmp_path)
    report = executor.execute_gates("L1", files=["a.py"], working_dir=str(tmp_path))
    result = report.results[0]
    assert result.status == GateExecutionStatus.ERROR
    assert "超出支持范围" in result.message
    assert "fake_gate" in report.must_pass_failed


def test_version_contract_blocks_below_min(tmp_path):
    _VersionedFake._results = [_fake_passed_result()]
    _VersionedFake.version = "1.0.0"  # < min_version 2.0.0
    executor = _versioned_executor(tmp_path)
    report = executor.execute_gates("L1", files=["a.py"], working_dir=str(tmp_path))
    result = report.results[0]
    assert result.status == GateExecutionStatus.ERROR
    assert "版本过低" in result.message


def test_parse_version_helper():
    from gate_plugin import GatePlugin

    assert GatePlugin._parse_version("safety, version 3.8.1") == (3, 8, 1)
    assert GatePlugin._parse_version("ruff 0.16.3") == (0, 16, 3)


# ── V3.2.9 误报过滤接线（修复 C：此前定义了单例但主流程从未调用）───────────


def _fp_executor(tmp_path, exceptions_yaml):
    """构造带自定义 exceptions.yaml 的执行器"""
    import gate_plugins

    gate_plugins.GATE_PLUGINS["fake"] = _FakePlugin
    exc_path = os.path.join(str(tmp_path), "exceptions.yaml")
    with open(exc_path, "w", encoding="utf-8") as f:
        f.write(exceptions_yaml)
    path = _write_config(
        tmp_path,
        {
            "must_pass": [
                {
                    "name": "fake_gate",
                    "tool": "fake",
                    "verification": "L1",
                    "timeout": 10,
                }
            ]
        },
        {"L1": {"must_pass": ["fake_gate"], "should_pass": [], "optional": []}},
    )
    executor = GateExecutor(path)
    executor.failure_handler = FailureHandler(
        {"gate_retry_delay": 0, "gate_max_retries": 1}
    )
    # 注入自定义误报配置
    import false_positive_checker as fpc

    executor.false_positive_checker = fpc.FalsePositiveChecker(exc_path)
    return executor


def _failed_with_issues(issues):
    return GateResult(
        name="fake_gate",
        tool="fake",
        status=GateExecutionStatus.FAILED,
        exit_code=1,
        issues_count=len(issues),
        issues=issues,
        message="发现 1 个问题",
    )


def test_false_positive_all_issues_waived_passes(tmp_path):
    """全部 issues 命中已知误报 → 门禁 PASSED 并注明豁免"""
    exc = (
        "known_false_positives:\n"
        "  - id: fp-1\n"
        "    rule: fake-rule-1\n"
        "    file: a.py\n"
        "    reason: test\n"
        "    approved_by: tech_lead\n"
        "    permanent: true\n"
    )
    from gate_types import Issue

    _FakePlugin._results = [
        _failed_with_issues(
            [Issue(severity="error", message="x", file="a.py", rule="fake-rule-1")]
        )
    ]
    executor = _fp_executor(tmp_path, exc)
    report = executor.execute_gates("L1", files=["a.py"], working_dir=str(tmp_path))
    result = report.results[0]
    assert result.status == GateExecutionStatus.PASSED
    assert "误报豁免" in result.message
    assert report.success


def test_false_positive_partial_waive_keeps_failed(tmp_path):
    """部分 issues 命中误报 → 保留 FAILED，并给出豁免提示"""
    exc = (
        "known_false_positives:\n"
        "  - id: fp-1\n"
        "    rule: fake-rule-1\n"
        "    file: a.py\n"
        "    reason: test\n"
        "    approved_by: tech_lead\n"
        "    permanent: true\n"
    )
    from gate_types import Issue

    _FakePlugin._results = [
        _failed_with_issues(
            [
                Issue(severity="error", message="x", file="a.py", rule="fake-rule-1"),
                Issue(severity="error", message="y", file="a.py", rule="real-rule-9"),
            ]
        )
    ]
    executor = _fp_executor(tmp_path, exc)
    report = executor.execute_gates("L1", files=["a.py"], working_dir=str(tmp_path))
    result = report.results[0]
    assert result.status == GateExecutionStatus.FAILED
    assert any("命中已知误报" in s for s in result.suggestions)
    assert report.success is False


def test_false_positive_no_match_unchanged(tmp_path):
    """无匹配误报 → 行为不变（FAILED）"""
    exc = "known_false_positives: []\n"
    from gate_types import Issue

    _FakePlugin._results = [
        _failed_with_issues(
            [Issue(severity="error", message="x", file="a.py", rule="r1")]
        )
    ]
    executor = _fp_executor(tmp_path, exc)
    report = executor.execute_gates("L1", files=["a.py"], working_dir=str(tmp_path))
    assert report.results[0].status == GateExecutionStatus.FAILED
    assert report.success is False
    assert GatePlugin._parse_version("") is None


# ── V3.3-R4：矩阵-生命周期解耦（注入回调）────────────────────────────────


def test_matrix_callback_invoked_when_set(tmp_path):
    """注入回调 → execute_gates 后调用（DAG 接电经回调而非直接 import）"""
    _FakePlugin._results = [_fake_passed_result()]
    _FakePlugin.calls = 0
    executor = _executor_with_fake(tmp_path)
    calls = []

    def cb(wd, report_dict):
        calls.append((wd, report_dict.get("success")))

    executor.matrix_evidence_callback = cb
    executor.execute_gates("L1", files=["a.py"], working_dir=str(tmp_path))
    assert len(calls) == 1
    assert calls[0][1] is True


def test_matrix_callback_default_off(tmp_path):
    """默认无回调 → 不调用（执行层不依赖生命周期，消除双向耦合）"""
    _FakePlugin._results = [_fake_passed_result()]
    _FakePlugin.calls = 0
    executor = _executor_with_fake(tmp_path)
    executor.execute_gates("L1", files=["a.py"], working_dir=str(tmp_path))
    assert executor.matrix_evidence_callback is None


def test_matrix_callback_exception_swallowed(tmp_path):
    """回调抛异常 → 不阻断门禁报告（try/except 保护）"""
    _FakePlugin._results = [_fake_passed_result()]
    _FakePlugin.calls = 0
    executor = _executor_with_fake(tmp_path)

    def cb(wd, report_dict):
        raise RuntimeError("cb boom")

    executor.matrix_evidence_callback = cb
    report = executor.execute_gates("L1", files=["a.py"], working_dir=str(tmp_path))
    assert report.success is True
