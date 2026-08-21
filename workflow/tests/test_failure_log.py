"""失败日志模块单元测试（记录 / 补充 / 一致性检查 / 归档）"""

from failure_log import (
    archive_incomplete,
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


def test_archive_incomplete_moves_missing_fields(tmp_path):
    """V3.3.2 S1：缺 root_cause/fix 的历史记录归档到 archived 文件，主文件保留完整记录"""
    wd = str(tmp_path)
    # 2 条不完整（缺 root_cause/fix）+ 1 条完整
    record_failure(wd, "unit_test", "MUST_PASS", "测试失败")
    record_failure(wd, "failure_log", "MUST_PASS", "记录不完整")
    record_failure(
        wd,
        "static_analysis",
        "MUST_PASS",
        "lint 失败",
        root_cause="规则升级",
        fix="更新代码",
    )
    result = archive_incomplete(wd)
    assert result["archived"] == 2
    assert result["kept"] == 1
    assert result["dry_run"] is False
    # 主文件只剩完整记录
    kept = load_failures(wd)
    assert [e["gate"] for e in kept] == ["static_analysis"]
    # 归档文件存在且含 2 条带 archived 标记的记录
    import json

    archived_path = wd + "/.hgf/failures-archived.jsonl"
    with open(archived_path, encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 2
    assert all(line["payload"].get("archived") == "v3.3.2-incomplete" for line in lines)
    # 归档后 failure_log 门禁通过
    ok, issues = check_failure_log(wd)
    assert ok is True
    assert issues == []


def test_archive_dry_run_does_not_write(tmp_path):
    """V3.3.2 S1：dry-run 只统计不落盘"""
    wd = str(tmp_path)
    record_failure(wd, "unit_test", "MUST_PASS", "测试失败")
    result = archive_incomplete(wd, dry_run=True)
    assert result["dry_run"] is True
    assert result["archived"] == 1
    # 主文件未被修改
    assert len(load_failures(wd)) == 1
    # 归档文件未创建
    import os

    assert not os.path.exists(wd + "/.hgf/failures-archived.jsonl")


def test_archive_all_keeps_empty_file(tmp_path):
    """V3.3.2 S1：全部归档时主文件写空（保持文件存在，不删除）"""
    wd = str(tmp_path)
    record_failure(wd, "unit_test", "MUST_PASS", "测试失败")
    result = archive_incomplete(wd)
    assert result["archived"] == 1
    assert result["kept"] == 0
    assert load_failures(wd) == []
