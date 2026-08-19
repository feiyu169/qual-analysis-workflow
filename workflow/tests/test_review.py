"""HGF 评审流程单元测试（审查包生成 + 双签名落盘 + lifecycle 联动）"""

import os

import lifecycle
import review


def test_build_pack_inlines_code(tmp_path):
    wd = str(tmp_path)
    with open(os.path.join(wd, "x.py"), "w", encoding="utf-8") as f:
        f.write("def a():\n    return 1\n")
    pack = review.build_pack(wd, "x.py")
    assert pack["truncated"] is False
    assert "def a():" in pack["code"]
    assert "PASS" in pack["request"]
    md = review.pack_markdown(pack)
    assert "def a():" in md


def test_build_pack_truncates(tmp_path):
    wd = str(tmp_path)
    with open(os.path.join(wd, "big.py"), "w", encoding="utf-8") as f:
        f.write("#" * 50000)
    pack = review.build_pack(wd, "big.py", max_chars=1000)
    assert pack["truncated"] is True
    assert len(pack["code"]) <= 1100


def test_record_review_dual_signature(tmp_path):
    wd = str(tmp_path)
    rec = review.record_review(wd, "gate_0_3", "pass",
                               reviewer="agent", verifier="heavyskill")
    assert rec["reviewer"] == "agent"
    assert rec["verifier"] == "heavyskill"
    assert rec["reviewer"] != rec["verifier"]
    # lifecycle 双签名检查器应认可
    ok, issues = lifecycle._check_review({"id": "gate_0_3"}, wd, None)
    assert ok is True, issues
    assert issues == []


def test_record_review_self_signature_rejected_by_lifecycle(tmp_path):
    wd = str(tmp_path)
    review.record_review(wd, "gate_0_3", "pass",
                         reviewer="agent", verifier="agent")
    ok, issues = lifecycle._check_review({"id": "gate_0_3"}, wd, None)
    assert ok is False
    assert any("自签" in i for i in issues)


# ── V3.2.11 Phase 2：评审诚实化（kind 语义）────────────────────────────────


def test_record_review_invalid_kind_rejected(tmp_path):
    wd = str(tmp_path)
    import pytest

    with pytest.raises(ValueError, match="independent|self-check"):
        review.record_review(wd, "gate_0_3", "pass", kind="bogus")


def test_self_check_rejected_for_user_acceptance(tmp_path):
    """user_acceptance 拒绝 self-check（被审对象不得自证通过）"""
    wd = str(tmp_path)
    import pytest

    with pytest.raises(ValueError, match="independent"):
        review.record_review(
            wd, "user_acceptance", "pass",
            reviewer="agent", verifier="heavyskill", kind="self-check",
        )


def test_self_check_allowed_for_review_passed(tmp_path):
    """review_passed 允许 self-check（结构化自检）"""
    wd = str(tmp_path)
    rec = review.record_review(
        wd, "review_passed", "pass",
        reviewer="agent", verifier="heavyskill", kind="self-check",
    )
    assert rec["kind"] == "self-check"
    ok, issues = lifecycle._check_review({"id": "review_passed"}, wd, None)
    assert ok is True, issues


def test_lifecycle_rejects_self_check_user_acceptance(tmp_path):
    """即使绕过 record_review 直接写 self-check 记录，lifecycle 也拒绝"""
    import json

    wd = str(tmp_path)
    p = os.path.join(wd, ".hgf", "reviews.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "gate": "user_acceptance", "verdict": "pass",
            "reviewer": "agent", "verifier": "heavyskill",
            "kind": "self-check",
        }) + "\n")
    ok, issues = lifecycle._check_review({"id": "user_acceptance"}, wd, None)
    assert ok is False
    assert any("自证" in i for i in issues)


def test_verify_fresh_requires_line_findings():
    """fresh-context 独立二验请求模板要求行级 findings"""
    req = review.verify_fresh("gate_2_2", "# pack\n```\ncode\n```\n")
    assert "文件:行号" in req["request"]
    assert "VERDICT" in req["request"]
    assert "无会话种子" in req["request"]


# ── V3.2.11 待办 4：user_acceptance 人工证据通道 ───────────────────────────


def test_user_acceptance_requires_human_evidence(tmp_path):
    """独立评审记录不足：user_acceptance 还需人工验收证据文件"""
    import json

    wd = str(tmp_path)
    p = os.path.join(wd, ".hgf", "reviews.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "gate": "user_acceptance", "verdict": "pass",
            "reviewer": "agent", "verifier": "heavyskill",
            "kind": "independent",
        }) + "\n")
    # 无人工证据 → 拒绝（即使独立评审记录存在）
    ok, issues = lifecycle._check_review({"id": "user_acceptance"}, wd, None)
    assert ok is False
    assert any("人工验收" in i for i in issues)


def test_user_acceptance_passes_with_evidence(tmp_path):
    """独立评审记录 + 人工验收文件（含'验收'≥100 字符）→ 通过"""
    import json

    wd = str(tmp_path)
    p = os.path.join(wd, ".hgf", "reviews.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "gate": "user_acceptance", "verdict": "pass",
            "reviewer": "agent", "verifier": "heavyskill",
            "kind": "independent",
        }) + "\n")
    doc = os.path.join(wd, "docs", "user_acceptance.md")
    os.makedirs(os.path.dirname(doc), exist_ok=True)
    with open(doc, "w", encoding="utf-8") as f:
        f.write("# 用户验收\n" + "验收结论：功能满足需求，测试全部通过。" * 20)
    ok, issues = lifecycle._check_review({"id": "user_acceptance"}, wd, None)
    assert ok is True, issues
