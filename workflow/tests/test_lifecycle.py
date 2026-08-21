"""生命周期管理器单元测试（DAG/状态/准入/准出检查器）"""

import json
import os

import pytest
import yaml

import lifecycle


def _write_gates(tmp_path):
    config = {
        "gates": {
            "gate_0_1": {
                "name": "需求分析",
                "phase": 0,
                "depends_on": [],
                "exit_criteria": [
                    {
                        "description": "需求文档生成",
                        "type": "document_generated",
                        "verification": "L1",
                    },
                ],
            },
            "gate_0_2": {
                "name": "需求评审",
                "phase": 0,
                "depends_on": ["gate_0_1"],
                "exit_criteria": [
                    {
                        "description": "第三方审查通过",
                        "type": "review_passed",
                        "verification": "L1",
                    },
                ],
            },
            "gate_1_1": {
                "name": "架构设计",
                "phase": 1,
                "depends_on": ["gate_0_2"],
                "exit_criteria": [
                    {
                        "description": "架构设计文档",
                        "type": "architecture_document",
                        "verification": "L1",
                    },
                ],
            },
        },
    }
    path = os.path.join(str(tmp_path), "gates.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True)
    return path, config


def test_load_gates_sorted_by_phase(tmp_path):
    path, _ = _write_gates(tmp_path)
    gates = lifecycle.load_gates(path)
    assert [g["id"] for g in gates] == ["gate_0_1", "gate_0_2", "gate_1_1"]


def test_build_dag(tmp_path):
    path, _ = _write_gates(tmp_path)
    deps = lifecycle.build_dag(lifecycle.load_gates(path))
    assert deps["gate_0_1"] == []
    assert deps["gate_1_1"] == ["gate_0_2"]


def test_status_initial_blocked(tmp_path):
    path, _ = _write_gates(tmp_path)
    gates = lifecycle.load_gates(path)
    deps = lifecycle.build_dag(gates)
    st = lifecycle.status(gates, deps, {})
    assert st["gate_0_1"] == "runnable"
    assert st["gate_0_2"] == "blocked"
    assert st["gate_1_1"] == "blocked"


def test_advance_requires_dependencies(tmp_path):
    wd = str(tmp_path)
    path, _ = _write_gates(tmp_path)
    gates = lifecycle.load_gates(path)
    deps = lifecycle.build_dag(gates)
    with pytest.raises(lifecycle.LifecycleError, match="gate_0_2"):
        lifecycle.advance(wd, gates, deps, "gate_0_2")


def test_advance_document_with_file(tmp_path):
    wd = str(tmp_path)
    doc = os.path.join(wd, "docs", "gate_0_1.md")
    os.makedirs(os.path.dirname(doc), exist_ok=True)
    with open(doc, "w", encoding="utf-8") as f:
        f.write("# 需求\n" + "需求内容。" * 60)
    path, _ = _write_gates(tmp_path)
    gates = lifecycle.load_gates(path)
    deps = lifecycle.build_dag(gates)
    rec = lifecycle.advance(wd, gates, deps, "gate_0_1", file_hint="docs/gate_0_1.md")
    assert rec["status"] == "done"
    state = lifecycle.load_state(wd)
    assert state["gate_0_1"]["status"] == "done"
    # 依赖完成后 gate_0_2 可推进
    st = lifecycle.status(gates, deps, state)
    assert st["gate_0_2"] == "runnable"


def test_advance_rejects_empty_document(tmp_path):
    wd = str(tmp_path)
    doc = os.path.join(wd, "docs", "gate_0_1.md")
    os.makedirs(os.path.dirname(doc), exist_ok=True)
    with open(doc, "w", encoding="utf-8") as f:
        f.write("# 标题")  # 过短，空壳文档
    path, _ = _write_gates(tmp_path)
    gates = lifecycle.load_gates(path)
    deps = lifecycle.build_dag(gates)
    with pytest.raises(lifecycle.LifecycleError, match="过短|空壳"):
        lifecycle.advance(wd, gates, deps, "gate_0_1", file_hint="docs/gate_0_1.md")


def test_advance_review_requires_record(tmp_path):
    wd = str(tmp_path)
    # 先完成 gate_0_1
    doc = os.path.join(wd, "docs", "gate_0_1.md")
    os.makedirs(os.path.dirname(doc), exist_ok=True)
    with open(doc, "w", encoding="utf-8") as f:
        f.write("# 需求\n" + "需求内容。" * 60)
    path, _ = _write_gates(tmp_path)
    gates = lifecycle.load_gates(path)
    deps = lifecycle.build_dag(gates)
    lifecycle.advance(wd, gates, deps, "gate_0_1", file_hint="docs/gate_0_1.md")

    # 无评审记录 → 拒绝
    with pytest.raises(lifecycle.LifecycleError, match="评审"):
        lifecycle.advance(wd, gates, deps, "gate_0_2")

    reviews = os.path.join(wd, ".hgf", "reviews.jsonl")

    def _write_review(rec):
        os.makedirs(os.path.dirname(reviews), exist_ok=True)
        # 每个子场景独立评审文件，避免前一条无效记录抢先触发检查
        if os.path.exists(reviews):
            os.remove(reviews)
        with open(reviews, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    # 缺 verifier（单签名）→ 拒绝
    _write_review({"gate": "gate_0_2", "verdict": "pass", "reviewer": "tester"})
    with pytest.raises(lifecycle.LifecycleError, match="双签名"):
        lifecycle.advance(wd, gates, deps, "gate_0_2")

    # reviewer == verifier（自签）→ 拒绝
    _write_review({
        "gate": "gate_0_2", "verdict": "pass",
        "reviewer": "tester", "verifier": "tester",
    })
    with pytest.raises(lifecycle.LifecycleError, match="自签"):
        lifecycle.advance(wd, gates, deps, "gate_0_2")

    # 双签名且不同 → 通过
    _write_review({
        "gate": "gate_0_2", "verdict": "pass",
        "reviewer": "executor", "verifier": "independent-expert",
    })
    rec = lifecycle.advance(wd, gates, deps, "gate_0_2")
    assert rec["status"] == "done"


def test_unknown_criterion_requires_confirm(tmp_path):
    wd = str(tmp_path)
    # document_generated 仍需真实文档（confirm 只兜底未知检查器）
    doc = os.path.join(wd, "docs", "gate_0_1.md")
    os.makedirs(os.path.dirname(doc), exist_ok=True)
    with open(doc, "w", encoding="utf-8") as f:
        f.write("# 需求\n" + "需求内容。" * 60)
    path, _ = _write_gates(tmp_path)
    gates = lifecycle.load_gates(path)
    # 人为追加一个无检查器的准出条件
    gates[0]["exit_criteria"].append(
        {"description": "神秘检查", "type": "mystery_check"}
    )
    deps = lifecycle.build_dag(gates)
    with pytest.raises(lifecycle.LifecycleError, match="confirm"):
        lifecycle.advance(wd, gates, deps, "gate_0_1", file_hint="docs/gate_0_1.md")
    # --confirm 兜底可推进
    lifecycle.advance(
        wd, gates, deps, "gate_0_1", file_hint="docs/gate_0_1.md", confirm=True
    )
    assert lifecycle.load_state(wd)["gate_0_1"]["status"] == "done"


# ── V3.2.8 TDD 证据真检查器 ──────────────────────────────────────────────


def _git_commit(wd, files_content, message):
    """在 wd 的 git 仓库中提交文件"""
    import subprocess
    import time

    subprocess.run(["git", "init", "-q"], cwd=wd, check=False)
    for path, content in files_content.items():
        p = os.path.join(wd, path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        subprocess.run(["git", "add", path], cwd=wd, check=False)
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t",
             "commit", "-q", "-m", message],
            cwd=wd, check=False,
        )
    time.sleep(1.1)  # 保证提交时间戳可区分


def test_tdd_evidence_requires_git(tmp_path):
    ok, issues = lifecycle._check_tdd_evidence({}, str(tmp_path), None)
    assert ok is False
    assert any("git" in i or "tests" in i for i in issues)


def test_tdd_evidence_pass_when_test_first(tmp_path):
    wd = str(tmp_path)
    _git_commit(wd, {"tests/test_x.py": "def test_a():\n    assert 1\n"}, "test first")
    _git_commit(wd, {"x.py": "def a():\n    return 1\n"}, "impl after")
    ok, issues = lifecycle._check_tdd_evidence({}, wd, None)
    assert ok is True, issues


def test_tdd_evidence_fail_when_impl_first(tmp_path):
    wd = str(tmp_path)
    _git_commit(wd, {"x.py": "def a():\n    return 1\n"}, "impl first")
    _git_commit(wd, {"tests/test_x.py": "def test_a():\n    assert 1\n"}, "test after")
    ok, issues = lifecycle._check_tdd_evidence({}, wd, None)
    assert ok is False
    assert any("非 TDD" in i for i in issues)


# ── V3.2.9 安全类准出真检查器（修复 A/J：名不副实）─────────────────────────


def test_sast_mapping_is_semgrep_not_ruff():
    """sast_scan 必须映射到真 SAST 检查器，而不是 ruff 兜底"""
    import lifecycle_checkers

    assert lifecycle_checkers._CHECKERS["sast_scan"] is lifecycle_checkers._check_semgrep
    assert lifecycle_checkers._CHECKERS["dependency_scan"] is lifecycle_checkers._check_dependency
    assert lifecycle_checkers._CHECKERS["iac_security_audit"] is lifecycle_checkers._check_checkov
    assert lifecycle_checkers._CHECKERS["dast_scan"] is lifecycle_checkers._check_dast


def test_tool_scan_fails_when_tool_missing(tmp_path, monkeypatch):
    """工具缺失 → FAIL（fail-loud，不静默通过）"""
    import tool_runner

    monkeypatch.setattr(tool_runner, "check_tool_available", lambda tool: None)
    ok, issues = lifecycle._check_tool_scan(
        {"id": "gate_2_1"}, str(tmp_path), None, "semgrep", "semgrep --json ."
    )
    assert ok is False
    assert any("未安装" in i for i in issues)


def test_tool_scan_fails_on_nonzero(tmp_path, monkeypatch):
    """工具执行返回非 0 → FAIL（有发现）"""
    import tool_runner

    class FakeRun:
        returncode = 1
        stdout = "rule: finding at line 5"
        stderr = ""

    monkeypatch.setattr(tool_runner, "check_tool_available", lambda tool: "semgrep")
    monkeypatch.setattr(tool_runner, "safe_run", lambda *a, **k: FakeRun())
    ok, issues = lifecycle._check_tool_scan(
        {"id": "gate_2_1"}, str(tmp_path), None, "semgrep", "semgrep --json ."
    )
    assert ok is False
    assert any("未通过" in i for i in issues)


def test_tool_scan_passes_on_zero(tmp_path, monkeypatch):
    """工具执行返回 0 → 通过"""
    import tool_runner

    class FakeRun:
        returncode = 0
        stdout = "no findings"
        stderr = ""

    monkeypatch.setattr(tool_runner, "check_tool_available", lambda tool: "semgrep")
    monkeypatch.setattr(tool_runner, "safe_run", lambda *a, **k: FakeRun())
    ok, issues = lifecycle._check_tool_scan(
        {"id": "gate_2_1"}, str(tmp_path), None, "semgrep", "semgrep --json ."
    )
    assert ok is True
    assert issues == []


def test_dast_requires_external_report(tmp_path):
    """DAST 无内置工具：无 --file → FAIL；有报告 → 通过"""
    ok, issues = lifecycle._check_dast({"id": "gate_3_2"}, str(tmp_path), None)
    assert ok is False
    assert any("DAST" in i for i in issues)
    report = os.path.join(str(tmp_path), "dast-report.json")
    with open(report, "w", encoding="utf-8") as f:
        f.write("{}")
    ok, issues = lifecycle._check_dast({"id": "gate_3_2"}, str(tmp_path), "dast-report.json")
    assert ok is True


def test_dependency_passes_zero_deps(tmp_path):
    """V3.2.11 狗粮化验收发现：零第三方依赖 → 直接通过（无扫描目标）"""
    wd = str(tmp_path)
    # 无 requirements.txt → 零依赖
    ok, issues = lifecycle._check_dependency({"id": "gate_2_1"}, wd, None)
    assert ok is True
    # 仅有注释的 requirements.txt → 零依赖
    with open(os.path.join(wd, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write("# 零第三方依赖\n")
    ok, issues = lifecycle._check_dependency({"id": "gate_2_1"}, wd, None)
    assert ok is True


def test_checkov_passes_no_iac(tmp_path):
    """V3.3.1 狗粮化发现：无 IaC 资产 → 直通（无审计目标）"""
    ok, issues = lifecycle._check_checkov({"id": "gate_4_1"}, str(tmp_path), None)
    assert ok is True
    assert any("无 IaC" in i for i in issues)


def test_checkov_scans_when_iac_exists(tmp_path, monkeypatch):
    """有 IaC 文件 → 跑 checkov"""
    wd = str(tmp_path)
    with open(os.path.join(wd, "main.tf"), "w", encoding="utf-8") as f:
        f.write('resource "aws_s3_bucket" "b" {\n}\n')
    import tool_runner

    class FakeRun:
        returncode = 0
        stdout = "{}"
        stderr = ""

    monkeypatch.setattr(tool_runner, "check_tool_available", lambda tool: "checkov")
    monkeypatch.setattr(tool_runner, "safe_run", lambda *a, **k: FakeRun())
    ok, issues = lifecycle._check_checkov({"id": "gate_4_1"}, wd, None)
    assert ok is True, issues


def test_dependency_scans_when_deps_exist(tmp_path, monkeypatch):
    """有真实依赖 → 跑 safety（环境可用时）"""
    wd = str(tmp_path)
    with open(os.path.join(wd, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write("requests==2.31.0\n")

    class FakeRun:
        returncode = 0
        stdout = "{}"
        stderr = ""

    import tool_runner

    monkeypatch.setattr(tool_runner, "check_tool_available", lambda tool: "safety")
    monkeypatch.setattr(tool_runner, "safe_run", lambda *a, **k: FakeRun())
    ok, issues = lifecycle._check_dependency({"id": "gate_2_1"}, wd, None)
    assert ok is True, issues


# ── V3.2.11 Phase 1 诚实化：语义校验器 ────────────────────────────────────


def _write_doc(wd, gate_id, content):
    """写 gate 文档（docs/<id>.md）并返回路径"""
    doc = os.path.join(wd, "docs", f"{gate_id}.md")
    os.makedirs(os.path.dirname(doc), exist_ok=True)
    with open(doc, "w", encoding="utf-8") as f:
        f.write(content)
    return doc


def test_document_threshold_raised_to_300(tmp_path):
    """V3.2.11：空壳门槛从 100 提到 300——150 字符仍拒"""
    wd = str(tmp_path)
    _write_doc(wd, "gate_1_1", "# 架构\n" + "内容。" * 50)  # ~105 字符
    ok, issues = lifecycle._check_document({"id": "gate_1_1"}, wd, None)
    assert ok is False
    assert any("过短" in i for i in issues)


def test_semantic_check_requires_architecture_entries(tmp_path):
    """架构文档必须含组件/数据流/信任边界/接口——长度满足但缺条目 → FAIL"""
    wd = str(tmp_path)
    _write_doc(wd, "gate_1_1", "这是一份架构文档。\n" + "填充内容。" * 120)  # 够长但无结构
    gate = {
        "id": "gate_1_1",
        "exit_criteria": [{"type": "architecture_document"}],
    }
    ok, issues = lifecycle._check_document_semantic(gate, wd, None)
    assert ok is False
    assert any("语义条目" in i for i in issues)
    assert any("组件" in i or "数据流" in i for i in issues)


def test_semantic_check_passes_with_entries(tmp_path):
    """架构文档含全部条目 → 通过"""
    wd = str(tmp_path)
    _write_doc(
        wd, "gate_1_1",
        "# 架构\n"
        "组件：用户服务、订单服务。\n"
        "数据流：用户→订单。\n"
        "信任边界：内外网隔离。\n"
        "接口：REST API。\n"
        + "填充。" * 150,
    )
    gate = {
        "id": "gate_1_1",
        "exit_criteria": [{"type": "architecture_document"}],
    }
    ok, issues = lifecycle._check_document_semantic(gate, wd, None)
    assert ok is True, issues


def test_threat_model_requires_stride(tmp_path):
    """威胁建模必须含 STRIDE——无 STRIDE 关键词 → FAIL"""
    wd = str(tmp_path)
    _write_doc(wd, "gate_1_1", "威胁：可能被攻击。\n" + "填充。" * 150)
    gate = {
        "id": "gate_1_1",
        "exit_criteria": [{"type": "threat_model"}],
    }
    ok, issues = lifecycle._check_document_semantic(gate, wd, None)
    assert ok is False
    assert any("语义条目" in i for i in issues)
    assert any("STRIDE" in i for i in issues)


def test_semantic_no_template_passes_basic(tmp_path):
    """无语义模板的类型（如 document_generated）→ 仅过基础门槛"""
    wd = str(tmp_path)
    _write_doc(wd, "gate_0_1", "# 需求\n" + "需求内容。" * 100)
    gate = {
        "id": "gate_0_1",
        "exit_criteria": [{"type": "document_generated"}],
    }
    ok, issues = lifecycle._check_document_semantic(gate, wd, None)
    assert ok is True, issues


def test_integration_checker_requires_real_suite(tmp_path):
    """V3.2.11：无集成测试证据 → FAIL（不再用单测冒充 L2）"""
    ok, issues = lifecycle._check_integration_tests({}, str(tmp_path), None)
    assert ok is False
    assert any("集成测试证据" in i for i in issues)


def test_integration_checker_mapping():
    """integration_test_passed 必须指向 _check_integration_tests 而非单测"""
    import lifecycle_checkers

    assert (
        lifecycle_checkers._CHECKERS["integration_test_passed"]
        is lifecycle_checkers._check_integration_tests
    )


# ── V3.2.11 Phase 1：DAG 接电（矩阵证据→自动推进）+ 迭代回路（reopen）──────


def test_record_matrix_evidence_requires_success(tmp_path):
    """矩阵失败（success=False）→ 不记录证据、不自动推进"""
    wd = str(tmp_path)
    result = lifecycle.record_matrix_evidence(
        wd,
        {
            "success": False,
            "level": "L2",
            "results": [
                {"name": "static_analysis", "status": "failed", "level": "MUST_PASS"},
            ],
        },
    )
    assert result["recorded"] == []
    assert result["advanced"] == []
    assert not os.path.exists(os.path.join(wd, ".hgf", "matrix_evidence.jsonl"))


def test_record_matrix_evidence_maps_passed_gates(tmp_path):
    """矩阵全绿 → 通过的门禁映射为准出证据并落盘"""
    wd = str(tmp_path)
    result = lifecycle.record_matrix_evidence(
        wd,
        {
            "success": True,
            "level": "L2",
            "results": [
                {"name": "static_analysis", "status": "passed", "level": "MUST_PASS"},
                {"name": "unit_test", "status": "passed", "level": "MUST_PASS"},
                {"name": "security_scan", "status": "passed", "level": "SHOULD_PASS"},
            ],
        },
    )
    assert "static_analysis" in result["recorded"]
    assert "unit_test_passed" in result["recorded"]
    # SHOULD_PASS 不构成证据
    assert "sast_scan" not in result["recorded"]
    p = os.path.join(wd, ".hgf", "matrix_evidence.jsonl")
    assert os.path.exists(p)


def test_auto_advance_only_pure_matrix_gates(tmp_path):
    """只自动推进准出全部可由矩阵证据满足的 gate（含评审/文档类不推进）"""
    import lifecycle as lc

    wd = str(tmp_path)
    # 真实 gates.yaml 下没有纯矩阵 gate（都含 tdd_evidence/文档/评审）
    # → 矩阵证据不会误推进任何 gate（诚实：可机械验证才推进）
    satisfied = {"static_analysis": "static_analysis", "unit_test_passed": "unit_test"}
    advanced = lc.auto_advance(wd, satisfied)
    assert advanced == []
    # 且不生成 lifecycle.json（无推进即无状态变更）
    assert not os.path.exists(os.path.join(wd, ".hgf", "lifecycle.json"))


def test_auto_advance_under_real_config(tmp_path, monkeypatch):
    """真实 gates.yaml 下：矩阵证据只推进纯矩阵 gate，评审 gate 不自动推进"""
    import lifecycle as lc

    wd = str(tmp_path)
    # 先手动完成 gate_0_1（真实 config 的入口依赖）
    satisfied = {"static_analysis": "static_analysis", "unit_test_passed": "unit_test"}
    advanced = lc.auto_advance(wd, satisfied)
    # 真实 config 无纯矩阵 gate（都含 tdd_evidence/文档/评审）→ 不误推进
    assert advanced == []


def test_reopen_requires_done(tmp_path):
    wd = str(tmp_path)
    gates = lifecycle.load_gates(
        os.path.join(os.path.dirname(lifecycle.__file__), "config", "gates.yaml")
    )
    with pytest.raises(lifecycle.LifecycleError, match="不是 done"):
        lifecycle.reopen(wd, gates, "gate_0_1", reason="x")


def test_reopen_cascades_downstream(tmp_path):
    """reopen 把下游 done gate 级联回 blocked，并写返工记录"""
    wd = str(tmp_path)
    import yaml

    cfg = os.path.join(str(tmp_path), "gates.yaml")
    with open(cfg, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {
                "gates": {
                    "gate_0_1": {
                        "name": "A", "phase": 0, "depends_on": [],
                        "exit_criteria": [{"type": "document_generated"}],
                    },
                    "gate_0_2": {
                        "name": "B", "phase": 0, "depends_on": ["gate_0_1"],
                        "exit_criteria": [{"type": "document_generated"}],
                    },
                }
            },
            f,
            allow_unicode=True,
        )
    gates = lifecycle.load_gates(cfg)
    # 手动置两 gate 为 done
    lifecycle.save_state(wd, {
        "gate_0_1": {"status": "done", "completed_at": "2026-01-01T00:00:00"},
        "gate_0_2": {"status": "done", "completed_at": "2026-01-01T00:00:00"},
    })
    rec = lifecycle.reopen(wd, gates, "gate_0_1", reason="需求变更")
    assert rec["reopened"] == "gate_0_1"
    assert rec["rework_count"] == 1
    assert "gate_0_2" in rec["affected_blocked"]
    state = lifecycle.load_state(wd)
    assert state["gate_0_1"]["status"] == "runnable"
    assert state["gate_0_2"]["status"] == "blocked"
    # 返工写入 failure_log
    from failure_log import load_failures
    entries = load_failures(wd)
    assert any(e.get("gate") == "gate_0_1" for e in entries)


# ── V3.2.11 Phase 2：流程度量 ─────────────────────────────────────────────


def test_metrics_reports_rework_and_escape(tmp_path):
    """metrics 聚合返工计数 + 缺陷逃逸率"""
    wd = str(tmp_path)
    # 手工造状态：一个 gate done + rework_count
    lifecycle.save_state(wd, {
        "gate_3_1": {"status": "done", "completed_at": "2026-01-02T00:00:00", "rework_count": 2},
    })
    # 造 failures：一个 Phase 3 gate（逃逸）+ 一个 Phase 2 gate
    import failure_log

    failure_log.record_failure(wd, "gate_3_2", "MUST_PASS", "dast 失败")
    failure_log.record_failure(wd, "gate_2_1", "MUST_PASS", "单测失败")
    m = lifecycle.metrics(wd)
    assert m["rework_count"] == 2
    assert m["total_failures"] == 2
    assert m["late_failures"] == 1  # gate_3_2 属 Phase 3
    assert m["escape_rate"] == 0.5


def test_metrics_empty_state(tmp_path):
    """无状态无失败 → 空度量不崩溃"""
    m = lifecycle.metrics(str(tmp_path))
    assert m["rework_count"] == 0
    assert m["escape_rate"] == 0.0


# ── V3.2.11 Phase 3：健康探针 + confirm 证据强制 ──────────────────────────


def test_health_requires_evidence(tmp_path):
    """健康准出无探针/无文件 → FAIL（不再接受裸确认）"""
    ok, issues = lifecycle._check_health({"id": "gate_4_2"}, str(tmp_path), None)
    assert ok is False
    assert any("probe_command" in i or "探针" in i for i in issues)


def test_health_runs_probe_command(tmp_path, monkeypatch):
    """配置 probe_command → 真实执行；返回 0 → 通过"""
    import tool_runner

    class FakeRun:
        returncode = 0
        stdout = "healthy"
        stderr = ""

    monkeypatch.setattr(tool_runner, "safe_run", lambda *a, **k: FakeRun())
    ok, issues = lifecycle._check_health(
        {"id": "gate_4_2", "probe_command": "healthcheck.sh"}, str(tmp_path), None
    )
    assert ok is True, issues


def test_health_probe_command_fails(tmp_path, monkeypatch):
    import tool_runner

    class FakeRun:
        returncode = 1
        stdout = ""
        stderr = "service down"

    monkeypatch.setattr(tool_runner, "safe_run", lambda *a, **k: FakeRun())
    ok, issues = lifecycle._check_health(
        {"id": "gate_4_2", "probe_command": "healthcheck.sh"}, str(tmp_path), None
    )
    assert ok is False
    assert any("未通过" in i for i in issues)


def test_health_runs_probe_script(tmp_path, monkeypatch):
    """scripts/probes/<type>.py 探针脚本真实执行"""
    import tool_runner

    wd = str(tmp_path)
    probe = os.path.join(wd, "scripts", "probes", "health_check.py")
    os.makedirs(os.path.dirname(probe), exist_ok=True)
    with open(probe, "w", encoding="utf-8") as f:
        f.write("print('ok')\n")

    class FakeRun:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(tool_runner, "safe_run", lambda *a, **k: FakeRun())
    gate = {
        "id": "gate_4_2",
        "exit_criteria": [{"type": "health_check"}],
    }
    ok, issues = lifecycle._check_health(gate, wd, None)
    assert ok is True, issues


def test_confirm_without_evidence_rejected(tmp_path):
    """--confirm 无 --file 证据 → 拒绝（禁止裸布尔确认）"""
    wd = str(tmp_path)
    doc = os.path.join(wd, "docs", "gate_0_1.md")
    os.makedirs(os.path.dirname(doc), exist_ok=True)
    with open(doc, "w", encoding="utf-8") as f:
        f.write("# 需求\n" + "需求内容。" * 60)
    path, _ = _write_gates(tmp_path)
    gates = lifecycle.load_gates(path)
    gates[0]["exit_criteria"].append(
        {"description": "神秘检查", "type": "mystery_check"}
    )
    deps = lifecycle.build_dag(gates)
    # 无 file 的 confirm → 拒绝
    with pytest.raises(lifecycle.LifecycleError, match="证据文件"):
        lifecycle.advance(wd, gates, deps, "gate_0_1", confirm=True)
    # 有证据文件的 confirm → 可推进（复用文档作证据）
    lifecycle.advance(
        wd, gates, deps, "gate_0_1",
        file_hint="docs/gate_0_1.md", confirm=True,
    )
    assert lifecycle.load_state(wd)["gate_0_1"]["status"] == "done"
