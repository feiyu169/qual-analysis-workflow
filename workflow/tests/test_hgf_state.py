"""HGF 状态目录规范单元测试（信封/旧格式兼容/注册表）"""

import json
import os

import hgf_state


def test_record_and_records_roundtrip(tmp_path):
    wd = str(tmp_path)
    hgf_state.record("failures", wd, {"gate": "a", "root_cause": None}, writer="failure_log")
    entries = hgf_state.records("failures", wd)
    assert len(entries) == 1
    assert entries[0]["gate"] == "a"
    # 文件里是信封（含 schema/kind/writer）
    with open(os.path.join(wd, ".hgf", "failures.jsonl"), encoding="utf-8") as f:
        raw = json.loads(f.readline())
    assert raw["schema"] == "hgf.v1"
    assert raw["kind"] == "failures"
    assert raw["writer"] == "failure_log"
    assert raw["payload"]["gate"] == "a"


def test_records_tolerates_legacy_bare_records(tmp_path):
    wd = str(tmp_path)
    p = os.path.join(wd, ".hgf", "runs.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    # 旧版裸记录（无 schema 信封）
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"success": True, "level": "L1"}) + "\n")
    # 新版信封
    hgf_state.record("runs", wd, {"success": False, "level": "L2"}, writer="run_history")
    entries = hgf_state.records("runs", wd)
    assert len(entries) == 2
    assert entries[0]["success"] is True
    assert entries[1]["success"] is False


def test_ensure_state_dir_creates_registry(tmp_path):
    wd = str(tmp_path)
    hgf_dir = hgf_state.ensure_state_dir(wd)
    assert os.path.exists(os.path.join(hgf_dir, "STATE.md"))
    with open(os.path.join(hgf_dir, "STATE.md"), encoding="utf-8") as f:
        content = f.read()
    assert "failures.jsonl" in content
    # 幂等
    hgf_state.ensure_state_dir(wd)
    assert os.path.exists(os.path.join(hgf_dir, "STATE.md"))
