"""state_io 原子写入单元测试（V3.3-R1，架构评审修复 C）。

验证：
- atomic_write_json 原子替换（写临时文件→os.replace）；
- atomic_append_jsonl 追加且行完整；
- failure_log.update_failure 原子重写不丢数据（此前"先删后写"崩溃丢全部）；
- 中途异常时临时文件被清理。
"""

import json
import os

import state_io


def test_atomic_write_json_creates_file(tmp_path):
    p = os.path.join(str(tmp_path), "x.json")
    state_io.atomic_write_json(p, {"a": 1, "b": "中文"})
    assert os.path.exists(p)
    data = json.loads(open(p, encoding="utf-8").read())
    assert data == {"a": 1, "b": "中文"}


def test_atomic_write_json_no_tmp_left(tmp_path):
    p = os.path.join(str(tmp_path), "x.json")
    state_io.atomic_write_json(p, {"k": "v"})
    leftovers = [f for f in os.listdir(str(tmp_path)) if f.endswith(".tmp")]
    assert leftovers == []


def test_atomic_append_jsonl_lines_intact(tmp_path):
    p = os.path.join(str(tmp_path), "y.jsonl")
    for i in range(3):
        state_io.atomic_append_jsonl(p, {"n": i})
    lines = [ln for ln in open(p, encoding="utf-8").read().splitlines() if ln.strip()]
    assert len(lines) == 3
    assert json.loads(lines[0])["n"] == 0
    assert json.loads(lines[2])["n"] == 2


def test_update_failure_atomic_rewrite(tmp_path):
    """V3.3-R1：update_failure 原子重写——记录不丢失、字段被更新"""
    import failure_log

    wd = str(tmp_path)
    failure_log.record_failure(wd, "unit_test", "MUST_PASS", "测试失败")
    failure_log.record_failure(wd, "static_analysis", "MUST_PASS", "lint 失败")
    updated = failure_log.update_failure(
        wd, "unit_test", root_cause="断言反", fix="修正", re_run_result="通过"
    )
    assert updated is not None
    entries = failure_log.load_failures(wd)
    assert len(entries) == 2  # 两条记录都在（未被"先删后写"丢失）
    unit = [e for e in entries if e["gate"] == "unit_test"][0]
    assert unit["root_cause"] == "断言反"
    assert unit["fix"] == "修正"


def test_atomic_write_cleans_tmp_on_failure(tmp_path, monkeypatch):
    """异常时临时文件被清理（不遗留 .tmp）"""
    p = os.path.join(str(tmp_path), "x.json")
    import state_io as _sio

    def boom(src, dst):
        raise OSError("simulated crash")

    monkeypatch.setattr(_sio.os, "replace", boom)
    try:
        state_io.atomic_write_json(p, {"k": "v"})
    except OSError:
        pass
    leftovers = [f for f in os.listdir(str(tmp_path)) if f.endswith(".tmp")]
    assert leftovers == []
    assert not os.path.exists(p)  # 原文件未产生
