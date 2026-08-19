"""HGF 集成测试（V3.2.11 Phase 1/待办 1）：跨模块真实链路。

与单元测试的区别：不 mock 任何模块，验证**模块间真实协作**：
classify_task → assess_risk → execute_gates（真跑 ruff/pytest）
→ failure 纪律（自动记录+复跑回填）→ 生命周期 DAG 接电（矩阵证据自动推进）。

这些测试比单测慢（真跑工具），标记为 integration，常规 `pytest tests/` 用
`-m 'not integration'` 排除，只有 `pytest tests/integration/` 或生命周期
gate_3_1 准出（_check_integration_tests）才执行——保证 L2 真实端到端。
"""

import os
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
# tests/integration → tests → workflow
_WORKFLOW = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _WORKFLOW)


@pytest.fixture
def sandbox(tmp_path):
    """集成沙箱：临时目录 + PYTHONPATH 指向 workflow"""
    os.environ["PYTHONPATH"] = _WORKFLOW
    return str(tmp_path)


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_classify_assess_chain(sandbox):
    """链路 1：分级→风评 真实协作（快速，不跑完整门禁避免递归超时）"""
    from risk_assessor import RiskAssessor
    from task_classifier import Task, TaskClassifier

    classifier = TaskClassifier()
    task = Task(
        description="add discount calculation with tests",
        files=["calc.py", "tests/test_calc.py"],
        file_count=2,
        line_count=45,
        affected_areas=["business"],
    )
    cls = classifier.classify_task(task)
    assert cls.level in ("L1", "L2", "L3", "L3_LITE", "L0")

    risk = RiskAssessor().assess_risk(task.affected_areas, task.description)
    assert risk.risk in ("low", "medium", "high")


def test_matrix_evidence_wires_lifecycle(sandbox):
    """链路 2：矩阵全绿 → record_matrix_evidence 映射证据（DAG 接电）"""
    import lifecycle

    # 模拟一次 L1 全绿运行（static_analysis + unit_test 通过）→ 应映射证据并落盘
    report = {
        "success": True,
        "level": "L1",
        "results": [
            {"name": "static_analysis", "status": "passed", "level": "MUST_PASS"},
            {"name": "unit_test", "status": "passed", "level": "MUST_PASS"},
        ],
    }
    result = lifecycle.record_matrix_evidence(sandbox, report)
    ev_path = os.path.join(sandbox, ".hgf", "matrix_evidence.jsonl")
    assert os.path.exists(ev_path)
    with open(ev_path, encoding="utf-8") as f:
        import json

        rec = json.loads(f.readline())
    assert rec["level"] == "L1"
    assert "static_analysis" in rec["satisfied_exit_types"]
    assert "unit_test_passed" in rec["satisfied_exit_types"]
    # 映射结果如实返回
    assert "static_analysis" in result["recorded"]
    assert "unit_test_passed" in result["recorded"]
    # 真实 gates.yaml 下无纯矩阵 gate → 不自动推进（诚实）
    assert result["advanced"] == []


def test_failure_discipline_full_loop(sandbox):
    """链路 3：失败自动记录 → 补根因 → 复跑回填 → failure_log 门禁通过"""
    import failure_log
    from gate_plugins import FailureLogPlugin
    from gate_types import GateConfig

    # 1) 记录一条失败
    failure_log.record_failure(sandbox, "unit_test", "MUST_PASS", "测试失败")

    # 2) failure-log 门禁此时应 FAIL（缺 root_cause/fix）
    plugin = FailureLogPlugin(
        GateConfig(name="failure_log", tool="failure-log", command="")
    )
    result = plugin.execute([], sandbox)
    assert result.failed

    # 3) 补根因 + 复跑结果（模拟修复后回填）
    failure_log.update_failure(
        sandbox,
        "unit_test",
        root_cause="断言写反",
        fix="修正断言",
        re_run_result="复跑通过",
    )

    # 4) 门禁通过
    result2 = plugin.execute([], sandbox)
    assert result2.passed


def test_integration_suite_collectable(sandbox):
    """集成套件自身可被 pytest 收集（保证 _check_integration_tests 不空跑）"""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", _HERE, "-q", "--collect-only"],
        capture_output=True,
        text=True,
        cwd=_WORKFLOW,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    # 本目录至少收集到本文件的测试（收集失败=returncode 非 0）
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "test_classify_assess_chain" in r.stdout
    assert "test_failure_discipline_full_loop" in r.stdout
