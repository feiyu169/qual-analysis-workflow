"""P53 元门禁自律检查器测试（V3.3.3 V2 记忆长效机制）。

覆盖 4 项机械验证 + self_audit 自身失败隔离：
1. failures.jsonl 无 failure_log 自身不完整记录（S1 防回归）
2. baseline.json 可解析（S2 防回归）
3. requirements-hgf.txt pip 可解析且版本固定（S3 防回归）
4. docs/lessons/ 索引完整性（L2 配套）
"""

import json
import os

from lifecycle_checkers import _check_self_audit


def _mk_working_dir(tmp_path, *rel_paths):
    """构造含 .hgf/ 与指定空文件的工作目录"""
    wd = str(tmp_path)
    os.makedirs(os.path.join(wd, ".hgf"), exist_ok=True)
    for rel in rel_paths:
        path = os.path.join(wd, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write("")
    return wd


def _gate():
    return {
        "id": "gate_5_3",
        "exit_criteria": [{"type": "self_audit", "verification": "L1"}],
    }


def test_self_audit_passes_when_clean(tmp_path):
    """干净状态：无 failures 自锁记录 + baseline 有效 + requirements 固定 + 无 lessons"""
    wd = _mk_working_dir(
        tmp_path,
        ".hgf/failures.jsonl",
        ".hgf/baseline.json",
    )
    # 有效 baseline
    with open(os.path.join(wd, ".hgf", "baseline.json"), "w", encoding="utf-8") as f:
        json.dump({"config_sha256": "abc", "tool_versions": {}}, f)
    ok, issues = _check_self_audit(_gate(), wd, None)
    assert ok is True, issues
    assert issues == []


def test_self_audit_flags_failure_log_lock(tmp_path):
    """S1 防回归：failures.jsonl 有 failure_log 自身不完整记录 → FAIL"""
    wd = _mk_working_dir(tmp_path, ".hgf/failures.jsonl")
    records = [
        {
            "schema": "hgf.v1",
            "kind": "failures",
            "writer": "failure_log",
            "timestamp": "2026-08-18T12:59:39",
            "payload": {
                "gate": "failure_log",
                "level": "MUST_PASS",
                "message": "记录不完整",
                "root_cause": None,
                "fix": None,
            },
        }
    ]
    with open(os.path.join(wd, ".hgf", "failures.jsonl"), "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    ok, issues = _check_self_audit(_gate(), wd, None)
    assert ok is False
    assert any("failure_log" in i and "S1" in i for i in issues)


def test_self_audit_ignores_own_records(tmp_path):
    """self_audit 自身记录（source=self_audit）被隔离，不触发 S1"""
    wd = _mk_working_dir(tmp_path, ".hgf/failures.jsonl")
    records = [
        {
            "schema": "hgf.v1",
            "kind": "failures",
            "writer": "failure_log",
            "timestamp": "2026-08-21T20:00:00",
            "payload": {
                "gate": "failure_log",
                "level": "MUST_PASS",
                "source": "self_audit",  # 自身记录隔离标记
                "message": "self_audit 失败",
                "root_cause": None,
                "fix": None,
            },
        }
    ]
    with open(os.path.join(wd, ".hgf", "failures.jsonl"), "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    ok, issues = _check_self_audit(_gate(), wd, None)
    assert ok is True, issues


def test_self_audit_flags_corrupt_baseline(tmp_path):
    """S2 防回归：baseline.json 损坏 → FAIL"""
    wd = _mk_working_dir(
        tmp_path,
        ".hgf/failures.jsonl",
        ".hgf/baseline.json",
    )
    with open(os.path.join(wd, ".hgf", "baseline.json"), "w", encoding="utf-8") as f:
        f.write('{"a": 1}\n}')  # 无效 JSON
    ok, issues = _check_self_audit(_gate(), wd, None)
    assert ok is False
    assert any("baseline" in i for i in issues)


def test_self_audit_flags_unpinned_requirements(tmp_path):
    """S3 防回归：requirements-hgf.txt 裸包名未固定版本 → FAIL"""
    wd = _mk_working_dir(
        tmp_path,
        ".hgf/failures.jsonl",
        "requirements-hgf.txt",
    )
    with open(os.path.join(wd, "requirements-hgf.txt"), "w", encoding="utf-8") as f:
        f.write("ruff\n")  # 无版本约束
    ok, issues = _check_self_audit(_gate(), wd, None)
    assert ok is False
    assert any("未固定版本" in i for i in issues)


def test_self_audit_accepts_valid_requirements(tmp_path):
    """S3：合法 requirements（含 ==、注释、-r 选项行）→ 通过"""
    wd = _mk_working_dir(
        tmp_path,
        ".hgf/failures.jsonl",
        "requirements-hgf.txt",
    )
    with open(os.path.join(wd, "requirements-hgf.txt"), "w", encoding="utf-8") as f:
        f.write("# comment\nruff==0.16.3\npytest>=7.0,<10\n-r other.txt\n")
    ok, issues = _check_self_audit(_gate(), wd, None)
    assert ok is True, issues


def test_self_audit_flags_missing_lessons_index(tmp_path):
    """L2 配套：lessons/ 下档案无 README 索引 → FAIL"""
    wd = _mk_working_dir(
        tmp_path,
        ".hgf/failures.jsonl",
        "docs/lessons/2026-08-21-self-audit.md",
    )
    with open(
        os.path.join(wd, "docs/lessons/2026-08-21-self-audit.md"), "w", encoding="utf-8"
    ) as f:
        f.write("# Self Audit Lessons\n\n内容占位。")
    ok, issues = _check_self_audit(_gate(), wd, None)
    assert ok is False
    assert any("索引" in i or "README" in i for i in issues)


def test_self_audit_passes_with_indexed_lessons(tmp_path):
    """L2：lessons 档案在 README 索引中 → 通过"""
    wd = _mk_working_dir(
        tmp_path,
        ".hgf/failures.jsonl",
        "docs/lessons/README.md",
        "docs/lessons/2026-08-21-self-audit.md",
    )
    with open(os.path.join(wd, "docs/lessons/README.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Lessons Index\n\n| 档案 | 主题 |\n|---|---|\n| 2026-08-21-self-audit.md | 自审查 P0 根因 |\n"
        )
    with open(
        os.path.join(wd, "docs/lessons/2026-08-21-self-audit.md"), "w", encoding="utf-8"
    ) as f:
        f.write("# Self Audit Lessons\n\n内容占位。")
    ok, issues = _check_self_audit(_gate(), wd, None)
    assert ok is True, issues
