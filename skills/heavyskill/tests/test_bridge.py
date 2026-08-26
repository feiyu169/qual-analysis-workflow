"""一期插件化单测：桥协议（serve 循环）与样本库。

覆盖（裁判准出）：
- serve 循环：畸形 JSON / 未知命令 / 中文往返（不触发真实 LLM）
- history / adjudicate（无需 LLM 的命令）
- sample_registry：record/read/adjudicate/audit/校准阈值

运行：
    cd skills/heavyskill && python -m pytest tests/test_bridge.py -v
"""

import io
import json
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _run_serve(input_lines):
    """在隔离的 stdin/stdout 上跑桥的 serve 循环（同步），返回所有 stdout 行。"""
    import heavyskill_bridge as bridge

    old_in, old_out = sys.stdin, sys.stdout
    try:
        sys.stdin = io.StringIO("\n".join(input_lines) + "\n")
        out = io.StringIO()
        sys.stdout = out
        with mock.patch.object(bridge, "_force_utf8", lambda: None):
            bridge.serve()
    finally:
        sys.stdin, sys.stdout = old_in, old_out
    return [l for l in out.getvalue().strip().splitlines() if l]


# ---------- 桥协议 ----------


def test_serve_malformed_json_returns_error_not_crash():
    lines = _run_serve(["{not-json"])
    assert len(lines) == 1
    resp = json.loads(lines[0])
    assert resp["ok"] is False
    assert "不是合法 JSON" in resp["error"]


def test_serve_unknown_command_returns_error_not_crash():
    lines = _run_serve(['{"id": 1, "command": "nope", "args": {}}'])
    assert len(lines) == 1
    resp = json.loads(lines[0])
    assert resp["ok"] is False
    assert "未知命令" in resp["error"]


def test_serve_history_empty_db():
    with mock.patch("workflow.sample_registry.read_samples", return_value=[]):
        lines = _run_serve(['{"id": 2, "command": "history", "args": {}}'])
    resp = json.loads(lines[0])
    assert resp["ok"] is True
    assert resp["id"] == 2
    assert resp["result"]["total"] == 0


def test_serve_chinese_roundtrip():
    # 中文命令/参数经 UTF-8 往返不损坏（桥协议层）
    with mock.patch("workflow.sample_registry.read_samples") as mock_read:
        mock_read.return_value = [
            {"sample_id": "hsk-中文-id", "payload": {"final_answer": "审查通过"}}
        ]
        lines = _run_serve(['{"id": 3, "command": "history", "args": {"limit": 5}}'])
    resp = json.loads(lines[0])
    assert resp["ok"] is True
    assert resp["result"]["samples"][0]["sample_id"] == "hsk-中文-id"


# ---------- 样本库 ----------


def test_sample_registry_record_and_read(tmp_path):
    from configuration import HeavySkillConfig
    from workflow.pipeline import HeavySkillResult
    from workflow.sample_registry import read_samples, record_sample

    result = HeavySkillResult(
        query="q",
        final_answer="f",
        consensus_answer="c",
        total_tokens=10,
        total_latency=1.0,
    )
    cfg = HeavySkillConfig(api_key="k", reason_k=4)
    sid = record_sample(result, cfg, sample_dir=str(tmp_path))
    assert sid.startswith("hsk-")
    samples = read_samples(sample_dir=str(tmp_path))
    assert len(samples) == 1
    assert samples[0]["sample_id"] == sid
    assert samples[0]["schema"] == "hsk-sample.v1"
    assert samples[0]["payload"]["final_answer"] == "f"


def test_sample_registry_adjudicate_with_audit(tmp_path):
    from configuration import HeavySkillConfig
    from workflow.pipeline import HeavySkillResult
    from workflow.sample_registry import (
        adjudicate,
        read_samples,
        record_sample,
    )

    result = HeavySkillResult(query="q", final_answer="f", consensus_answer="c")
    sid = record_sample(result, HeavySkillConfig(api_key="k"), sample_dir=str(tmp_path))
    ok = adjudicate(
        sid,
        "reject",
        notes="结论不完整",
        adjudicator="reviewer-x",
        sample_dir=str(tmp_path),
    )
    assert ok is True
    samples = read_samples(sample_dir=str(tmp_path))
    assert samples[0]["payload"]["verdict"] == "reject"
    assert samples[0]["payload"]["adjudicator"] == "reviewer-x"
    # audit log 存在（防伪造）
    audit = tmp_path / "samples-audit.jsonl"
    assert audit.exists()
    rec = json.loads(audit.read_text(encoding="utf-8").strip().splitlines()[0])
    assert rec["sample_id"] == sid
    assert rec["new_verdict"] == "reject"
    assert rec["writer"] == "reviewer-x"


def test_sample_registry_adjudicate_unknown_id(tmp_path):
    from workflow.sample_registry import adjudicate

    assert adjudicate("hsk-nonexistent", "adopt", sample_dir=str(tmp_path)) is False


def test_sample_registry_calibration_threshold(tmp_path):
    from configuration import HeavySkillConfig
    from workflow.pipeline import HeavySkillResult
    from workflow.sample_registry import quality_calibration_status, record_sample

    cfg = HeavySkillConfig(api_key="k")
    for i in range(5):
        record_sample(
            HeavySkillResult(query=f"q{i}", final_answer=f"f{i}", consensus_answer="c"),
            cfg,
            sample_dir=str(tmp_path),
        )
    status = quality_calibration_status(sample_dir=str(tmp_path))
    assert status["total_samples"] == 5
    # 裁判裁定：<20 不校准 / <30 仅描述性统计
    assert status["quality_score_calibrated"] is False
    assert status["stats_significant"] is False


def test_sample_registry_read_tolerates_corrupt_line(tmp_path):
    """JSONL 单行损坏容忍（并发写/中断）。"""
    from configuration import HeavySkillConfig
    from workflow.pipeline import HeavySkillResult
    from workflow.sample_registry import read_samples, record_sample

    record_sample(
        HeavySkillResult(query="q", final_answer="f", consensus_answer="c"),
        HeavySkillConfig(api_key="k"),
        sample_dir=str(tmp_path),
    )
    f = tmp_path / "samples.jsonl"
    f.write_text(f.read_text(encoding="utf-8") + "{corrupt-line}\n", encoding="utf-8")
    samples = read_samples(sample_dir=str(tmp_path))
    assert len(samples) == 1  # 损坏行被跳过，不崩溃
