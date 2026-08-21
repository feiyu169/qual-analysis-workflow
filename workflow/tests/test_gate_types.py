"""门禁类型单元测试（GateConfig 新字段、报告 exit_code / to_json）"""

from gate_types import (
    GateConfig,
    GateExecutionReport,
    GateExecutionStatus,
)


def test_gate_config_new_fields():
    config = GateConfig(
        name="x",
        tool="ruff",
        command="ruff {files}",
        incremental_coverage_min=80.0,
        verification="L1",
        probes=[{"name": "p"}],
    )
    d = config.to_dict()
    assert d["incremental_coverage_min"] == 80.0
    assert d["verification"] == "L1"
    assert d["probes"] == [{"name": "p"}]


def test_report_exit_code_zero_when_success():
    report = GateExecutionReport(
        level="L1",
        total_gates=1,
        passed=1,
        failed=0,
        skipped=0,
        must_pass_failed=[],
        results=[],
        duration=1.0,
    )
    assert report.success is True
    assert report.exit_code == 0


def test_report_exit_code_one_when_failure():
    report = GateExecutionReport(
        level="L1",
        total_gates=1,
        passed=0,
        failed=1,
        skipped=0,
        must_pass_failed=["unit_test"],
        results=[],
        duration=1.0,
    )
    assert report.exit_code == 1
    d = report.to_dict()
    assert d["exit_code"] == 1
    assert '"success": false' in report.to_json()
    assert '"exit_code": 1' in report.to_json()


def test_gate_result_status_helpers():
    from gate_types import GateLevel, GateResult

    passed = GateResult(
        name="a",
        tool="ruff",
        status=GateExecutionStatus.PASSED,
        exit_code=0,
        issues_count=0,
        level=GateLevel.MUST_PASS,
    )
    assert passed.passed is True
    assert passed.failed is False


def test_format_report_renders_success():
    from gate_types import GateLevel, GateResult

    result = GateResult(
        name="static_analysis",
        tool="ruff",
        status=GateExecutionStatus.PASSED,
        exit_code=0,
        issues_count=0,
        message="静态分析通过",
        level=GateLevel.MUST_PASS,
    )
    report = GateExecutionReport(
        level="L1",
        total_gates=1,
        passed=1,
        failed=0,
        skipped=0,
        must_pass_failed=[],
        results=[result],
        duration=1.5,
    )
    text = report.format_report()
    assert "质量门禁执行报告" in text
    assert "所有 MUST_PASS 门禁通过" in text
    assert "static_analysis" in text


def test_format_report_renders_failure():
    from gate_types import GateLevel, GateResult

    result = GateResult(
        name="unit_test",
        tool="pytest",
        status=GateExecutionStatus.FAILED,
        exit_code=1,
        issues_count=0,
        message="测试失败",
        level=GateLevel.MUST_PASS,
    )
    report = GateExecutionReport(
        level="L1",
        total_gates=1,
        passed=0,
        failed=1,
        skipped=0,
        must_pass_failed=["unit_test"],
        results=[result],
        duration=1.5,
    )
    text = report.format_report()
    assert "MUST_PASS 门禁失败" in text
    assert "unit_test" in text


def test_tool_health_in_report():
    """V3.2.5 环境维度：SKIPPED/ERROR 门禁进入 tool_health，且报告有该段"""
    from gate_types import GateLevel, GateResult

    skipped = GateResult(
        name="security_scan",
        tool="semgrep",
        status=GateExecutionStatus.SKIPPED,
        exit_code=0,
        issues_count=0,
        message="工具不可用: semgrep",
        level=GateLevel.SHOULD_PASS,
    )
    report = GateExecutionReport(
        level="L1",
        total_gates=2,
        passed=1,
        failed=0,
        skipped=1,
        must_pass_failed=[],
        results=[skipped],
        duration=1.0,
        tool_health=[
            {
                "gate": "security_scan",
                "tool": "semgrep",
                "status": "skipped",
                "message": "工具不可用: semgrep",
            }
        ],
    )
    d = report.to_dict()
    assert d["tool_health"][0]["gate"] == "security_scan"
    assert "工具健康度" in report.format_report()
