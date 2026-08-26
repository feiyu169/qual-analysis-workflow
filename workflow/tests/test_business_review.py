"""业务缺陷评审检查器测试（V3.4.1 P56 分层收益模型）。

覆盖：独立评审通过 / self-check 拒绝 / verifier 内部拒绝 /
无缺陷发现拒绝 / 无记录拒绝。
"""

import json
import os

from lifecycle_checkers import _check_business_review


def _gate():
    return {
        "id": "gate_2_2",
        "exit_criteria": [
            {"type": "business_review", "verification": "L1"},
        ],
    }


def _mk_wd(tmp_path, reviews: list[dict]) -> str:
    wd = str(tmp_path)
    os.makedirs(os.path.join(wd, ".hgf"), exist_ok=True)
    with open(os.path.join(wd, ".hgf", "reviews.jsonl"), "w", encoding="utf-8") as f:
        for r in reviews:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return wd


def _review(
    gate="gate_2_2",
    verdict="pass",
    reviewer="agent",
    verifier="heavyskill",
    kind="independent",
    notes="业务缺陷审查发现 P1 边界问题",
):
    return {
        "gate": gate,
        "verdict": verdict,
        "reviewer": reviewer,
        "verifier": verifier,
        "kind": kind,
        "notes": notes,
    }


def test_passes_with_independent_review(tmp_path):
    wd = _mk_wd(tmp_path, [_review()])
    ok, issues = _check_business_review(_gate(), wd, None)
    assert ok is True, issues


def test_rejects_self_check(tmp_path):
    """P56：self-check 拒绝（被审代码不得自证业务无缺陷）"""
    wd = _mk_wd(tmp_path, [_review(kind="self-check")])
    ok, issues = _check_business_review(_gate(), wd, None)
    assert ok is False
    assert any("self-check" in i for i in issues)


def test_rejects_internal_verifier(tmp_path):
    """P56：verifier 为内部（agent）拒绝——业务评审需外部独立方"""
    wd = _mk_wd(tmp_path, [_review(reviewer="dev-1", verifier="agent")])
    ok, issues = _check_business_review(_gate(), wd, None)
    assert ok is False
    assert any("内部" in i for i in issues)


def test_rejects_no_findings(tmp_path):
    """P56：notes 无缺陷发现记录拒绝"""
    wd = _mk_wd(tmp_path, [_review(notes="一切正常，无问题")])
    ok, issues = _check_business_review(_gate(), wd, None)
    assert ok is False
    assert any("缺陷" in i for i in issues)


def test_rejects_missing_records(tmp_path):
    wd = _mk_wd(tmp_path, [])
    ok, issues = _check_business_review(_gate(), wd, None)
    assert ok is False


def test_rejects_wrong_gate_or_verdict(tmp_path):
    wd = _mk_wd(tmp_path, [_review(gate="gate_2_1"), _review(verdict="fail")])
    ok, issues = _check_business_review(_gate(), wd, None)
    assert ok is False
