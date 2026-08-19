"""失败日志模块单元测试（记录 / 补充 / 一致性检查）"""


from failure_log import (
    check_failure_log,
    is_resolved,
    load_failures,
    record_failure,
    unresolved_failures,
    update_failure,
)


def test_record_and_load_roundtrip(tmp_path):
    wd = str(tmp_path)
    record_failure(wd, "unit_test", "MUST_PASS", "测试失败")
    entries = load_failures(wd)
    assert len(entries) == 1
    assert entries[0]["gate"] == "unit_test"
    assert entries[0]["root_cause"] is None


def test_update_failure_fills_root_cause(tmp_path):
    wd = str(tmp_path)
    record_failure(wd, "unit_test", "MUST_PASS", "测试失败")
    updated = update_failure(
        wd, "unit_test", root_cause="契约冲突", fix="统一为 clamp 语义"
    )
    assert updated["root_cause"] == "契约冲突"
    ok, issues = check_failure_log(wd)
    assert ok is True
    assert issues == []


def test_check_flags_missing_root_cause(tmp_path):
    wd = str(tmp_path)
    record_failure(wd, "unit_test", "MUST_PASS", "测试失败")
    ok, issues = check_failure_log(wd)
    assert ok is False
    assert any("root_cause" in i for i in issues)
    assert any("fix" in i for i in issues)


def test_check_passes_when_empty(tmp_path):
    ok, issues = check_failure_log(str(tmp_path))
    assert ok is True
    assert issues == []


def test_is_resolved_convention(tmp_path):
    """V3.2.8-A：re_run_result 非空即视为已解决（无需 resolved 状态位）"""
    assert is_resolved({"gate": "a", "re_run_result": "复跑通过"}) is True
    assert is_resolved({"gate": "a", "re_run_result": "  "}) is False
    assert is_resolved({"gate": "a", "re_run_result": None}) is False
    assert is_resolved({"gate": "a"}) is False


def test_unresolved_failures_filters_resolved(tmp_path):
    wd = str(tmp_path)
    record_failure(wd, "unit_test", "MUST_PASS", "测试失败")
    record_failure(wd, "static_analysis", "MUST_PASS", "lint 失败")
    # 第二条补充 re_run_result → 视为已解决
    update_failure(wd, "static_analysis", re_run_result="修复后通过")
    unresolved = unresolved_failures(wd)
    assert [e["gate"] for e in unresolved] == ["unit_test"]
    assert len(load_failures(wd)) == 2
