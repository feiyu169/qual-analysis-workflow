"""外部独立校准测试（V3.4-D，heavyskill 审查修正版）。

覆盖：D1 真标记非伪签名 / D2 verifier 传递（拒绝 heavyskill 作外部）/
D3 nonce+payload_hash 绑定 / 记录可审计。
"""

import json
import os

from review import (
    export_external_pack,
    record_external_verdict,
)


def _reviews(tmp_path):
    p = os.path.join(str(tmp_path), ".hgf", "reviews.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def test_export_external_pack_no_fake_signature(tmp_path):
    """D1 修正：无伪签名——external=true + verifier_evidence=pending，而非 signed:True"""
    pack = export_external_pack("gate_5_2", "# code", verifier="human")
    assert pack["external"] is True
    assert "signed" not in pack or pack["signed"] is not True
    assert pack["verifier_evidence"] == "pending"
    assert pack["payload_hash"]  # 内容哈希（绑定用，非签名）


def test_export_external_pack_has_nonce_and_binding(tmp_path):
    """D3 修正：nonce + task_binding + expires_at"""
    pack = export_external_pack(
        "gate_5_2", "# code", verifier="human", task_binding="PR-42"
    )
    assert len(pack["nonce"]) == 16
    assert pack["task_binding"] == "PR-42"
    assert pack["expires_at"] > 0


def test_record_external_rejects_heavyskill_verifier(tmp_path):
    """D2 修正：拒绝 heavyskill 作外部 verifier（同生态不满足独立校准）"""
    try:
        record_external_verdict(str(tmp_path), "gate_5_2", "pass", "ev", "heavyskill")
        assert False, "应拒绝 heavyskill 作外部 verifier"
    except ValueError as e:
        assert "heavyskill" in str(e)


def test_record_external_stores_reviewer_prefix(tmp_path):
    """外部结论 reviewer 带 external: 前缀（可审计区分）"""
    rec = record_external_verdict(
        str(tmp_path), "gate_5_2", "pass", "verified by human expert", "human-reviewer"
    )
    assert rec["reviewer"] == "external:human-reviewer"
    assert rec["kind"] == "independent"
    # 落盘可读
    recs = _reviews(tmp_path)
    assert any(r["reviewer"] == "external:human-reviewer" for r in recs)


def test_record_external_binds_nonce_and_hash(tmp_path):
    """D3 修正：nonce + payload_hash 写入 notes（防重放/防串用）"""
    rec = record_external_verdict(
        str(tmp_path),
        "gate_5_2",
        "pass",
        "ev",
        "human-x",
        nonce="abc123",
        payload_hash="deadbeef",
    )
    assert "[nonce=abc123]" in rec["notes"]
    assert "[payload_hash=deadbeef]" in rec["notes"]
