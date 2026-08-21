"""运行历史模块单元测试（追加/读取/摘要）"""

import run_history


def test_append_and_history(tmp_path):
    wd = str(tmp_path)
    run_history.append_run(
        wd,
        {
            "level": "L1",
            "total_gates": 3,
            "passed": 3,
            "failed": 0,
            "skipped": 0,
            "must_pass_failed": [],
            "success": True,
            "exit_code": 0,
            "duration": 1.0,
        },
    )
    run_history.append_run(
        wd,
        {
            "level": "L1",
            "total_gates": 3,
            "passed": 2,
            "failed": 1,
            "skipped": 0,
            "must_pass_failed": ["unit_test"],
            "success": False,
            "exit_code": 1,
            "duration": 1.0,
        },
    )
    entries = run_history.history(wd)
    assert len(entries) == 2
    assert entries[0]["success"] is True
    assert entries[1]["must_pass_failed"] == ["unit_test"]


def test_history_limit(tmp_path):
    wd = str(tmp_path)
    for i in range(5):
        run_history.append_run(
            wd,
            {
                "level": "L1",
                "total_gates": 1,
                "passed": 1,
                "failed": 0,
                "skipped": 0,
                "must_pass_failed": [],
                "success": True,
                "exit_code": 0,
                "duration": 1.0,
            },
        )
    assert len(run_history.history(wd, n=3)) == 3


def test_summarize_repeated_failures(tmp_path):
    wd = str(tmp_path)
    for i in range(3):
        run_history.append_run(
            wd,
            {
                "level": "L1",
                "total_gates": 3,
                "passed": 2,
                "failed": 1,
                "skipped": 0,
                "must_pass_failed": ["unit_test"],
                "success": False,
                "exit_code": 1,
                "duration": 1.0,
            },
        )
    summary = run_history.summarize(run_history.history(wd))
    assert summary["runs"] == 3
    assert summary["success_rate"] == 0.0
    assert summary["repeated_failures"] == {"unit_test": 3}


def test_summarize_empty():
    assert run_history.summarize([]) == {}


# ── V3.2.11 Phase 4：门禁健康报告 ────────────────────────────────────────


def _run_entry(results, success=True):
    return {
        "level": "L1",
        "total_gates": len(results),
        "passed": sum(1 for r in results if r["status"] == "passed"),
        "failed": sum(1 for r in results if r["status"] in ("failed", "error")),
        "skipped": 0,
        "must_pass_failed": [],
        "success": success,
        "exit_code": 0 if success else 1,
        "duration": 1.0,
        "results": results,
    }


def test_gate_health_flags_always_failed(tmp_path):
    """从未通过过的门禁被标记 always_failed（逃逸舱口识别）"""
    wd = str(tmp_path)
    run_history.append_run(
        wd,
        _run_entry(
            [
                {"name": "dependency_scan", "status": "error"},
                {"name": "static_analysis", "status": "passed"},
            ],
            success=False,
        ),
    )
    run_history.append_run(
        wd,
        _run_entry(
            [
                {"name": "dependency_scan", "status": "error"},
                {"name": "static_analysis", "status": "passed"},
            ],
            success=False,
        ),
    )
    health = run_history.gate_health(run_history.history(wd))
    assert health["dependency_scan"]["always_failed"] is True
    assert health["dependency_scan"]["fail_rate"] == 1.0
    assert health["static_analysis"]["always_failed"] is False
    assert health["static_analysis"]["fail_rate"] == 0.0


def test_gate_health_recovers_after_pass(tmp_path):
    """门禁曾失败但后来通过 → 不是 always_failed"""
    wd = str(tmp_path)
    run_history.append_run(
        wd,
        _run_entry(
            [
                {"name": "unit_test", "status": "failed"},
            ],
            success=False,
        ),
    )
    run_history.append_run(
        wd,
        _run_entry(
            [
                {"name": "unit_test", "status": "passed"},
            ],
            success=True,
        ),
    )
    health = run_history.gate_health(run_history.history(wd))
    assert health["unit_test"]["always_failed"] is False
    assert health["unit_test"]["fail_rate"] == 0.5
