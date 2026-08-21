"""HGF 评审流程（V3.2.8 / V3.2.11）。

把 heavyskill（K 路并行审议）接入 HGF 生命周期评审：
1. build_pack：生成"审查包"——被审代码内联 + 审查请求模板
   （满足 heavyskill 的输入约束：子代理读不了本地文件，内容必须内联）
2. record_review：评审结论写入 .hgf/reviews.jsonl（双签名：
   reviewer=执行者 / verifier=独立评审者如 heavyskill）
3. 之后 lifecycle advance 的 review_passed 检查器可验证通过。

V3.2.11（Phase 2 权威化，修评审共识 E）：
- 评审诚实化：记录带 kind 字段——`independent`（真独立评审，如异质模型/
  真人/无会话种子的 fresh agent）vs `self-check`（结构化自检，同源 AI）。
  user_acceptance 类 gate **拒绝 self-check**（被审对象不得自证通过）。
- fresh-context 独立二验：verify_fresh 生成"无会话种子"的独立审查请求，
  要求行级 findings（引用具体代码行），任一拒绝则 gate 失败。

流程：
    python workflow_cli.py --review-build <file> [--out pack.md]   # 生成审查包
    （用 heavyskill 工具审查 pack 内容）
    python workflow_cli.py --review-record <gate> --verdict pass --verifier heavyskill [--kind independent|self-check] [--notes ...]
"""

import os
from datetime import datetime

# 允许 self-check 的评审类 gate（结构化自检可接受）；其余需 independent
SELF_CHECK_ALLOWED_GATES = {"review_passed", "manual_review", "feedback_collected"}
# 必须 independent 的 gate（被审对象不得自证通过）
INDEPENDENT_REQUIRED_GATES = {"user_acceptance", "review_checklist"}


def build_pack(working_dir: str, file_path: str, max_chars: int = 20000) -> dict:
    """生成审查包：内联代码 + 审查请求模板（超长截断并标记）"""
    path = os.path.join(working_dir, file_path)
    with open(path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    truncated = len(content) > max_chars
    body = content[:max_chars] + ("\n...[截断，完整内容见文件]..." if truncated else "")
    return {
        "title": f"HGF 评审请求: {file_path}",
        "request": (
            "请以第三方代码审查专家身份审查以下代码。输出："
            "1) 问题清单（严重度 P0/P1/P2，原因，修复建议，**必须引用具体代码行**）"
            "2) 测试与验证充分性 3) 结论：PASS / PASS_WITH_WARNING / FAIL"
        ),
        "code": body,
        "truncated": truncated,
        "full_chars": len(content),
    }


def pack_markdown(pack: dict) -> str:
    """审查包渲染为 markdown（可直接内联进 heavyskill query）"""
    return f"# {pack['title']}\n\n{pack['request']}\n\n```\n{pack['code']}\n```\n" + (
        "\n> 注：内容已截断（完整 {full_chars} 字符）。\n" if pack["truncated"] else ""
    )


def verify_fresh(gate: str, pack_md: str, findings: list[str] | None = None) -> dict:
    """fresh-context 独立二验请求模板（V3.2.11 Phase 2）。

    供 DSH 会话把审查包交给**无会话种子**的 fresh agent（或异质模型）审查；
    findings 为审查方返回的行级问题清单。调用方负责实际派发审查。

    Returns:
        组装好的独立二验请求文本（可直接作为子代理 prompt）。
    """
    request = (
        "你是 HGF 独立二验者（无会话种子，独立判断）。\n"
        f"审查目标 gate: {gate}\n\n"
        f"审查包（内联代码）：\n{pack_md}\n\n"
        "要求：\n"
        "1. 逐行审查，**每条问题必须引用具体代码行**（文件:行号）\n"
        "2. 严重度分级 P0/P1/P2 + 修复建议\n"
        "3. 结论：PASS / FAIL（任一 P0/P1 未解决 → FAIL）\n"
        "最后一行输出：VERDICT: PASS|FAIL"
    )
    if findings is not None:
        return {"request": request, "findings": findings}
    return {"request": request}


def record_review(
    working_dir: str,
    gate: str,
    verdict: str,
    reviewer: str = "agent",
    verifier: str = "heavyskill",
    notes: str = "",
    kind: str = "independent",
) -> dict:
    """评审结论落盘（双签名：reviewer ≠ verifier 才有意义，调用方负责）。

    V3.2.11（Phase 2）：kind 区分独立评审与结构化自检——
    - self-check 只允许在 SELF_CHECK_ALLOWED_GATES；
    - INDEPENDENT_REQUIRED_GATES 拒绝 self-check（被审对象不得自证通过）。
    """
    if kind not in ("independent", "self-check"):
        raise ValueError(f"kind 必须为 independent 或 self-check，got {kind}")
    if kind == "self-check" and gate in INDEPENDENT_REQUIRED_GATES:
        raise ValueError(
            f"gate [{gate}] 要求 independent 评审（被审对象不得自证通过——V3.2.11）"
        )
    rec = {
        "gate": gate,
        "verdict": verdict,
        "reviewer": reviewer,
        "verifier": verifier,
        "kind": kind,
        "notes": notes,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    p = os.path.join(working_dir, ".hgf", "reviews.jsonl")
    try:
        from . import state_io as _io
    except ImportError:
        import state_io as _io
    _io.atomic_append_jsonl(p, rec)
    return rec


# ── V3.4-D 外部独立校准（heavyskill 审查修正）──────────────────────────────
# 修正项：
#   D1 移除伪签名（signed: True 无真实机制）→ 真实标记 external=true +
#      verifier_evidence（外部证据哈希/标识），不承诺不存在的签名
#   D2 verifier 不再硬编码 heavyskill——外部验证必须传外部 verifier 名
#   D3 加 nonce + task_binding + expires_at（防重放/防串用），payload 提示脱敏


def export_external_pack(
    gate: str,
    pack_md: str,
    verifier: str = "human",
    task_binding: str = "",
) -> dict:
    """导出外部验证包（人类专家/异构工具可读格式，V3.4-D 修正）。

    不做伪签名：external=true + verifier_evidence 如实标注"待外部验证"，
    绝不声称"已签名"（D1）。
    """
    import hashlib
    import uuid

    nonce = uuid.uuid4().hex[:16]
    return {
        "schema": "hgf.external-review.v1",
        "gate": gate,
        "verifier": verifier,
        "nonce": nonce,
        "task_binding": task_binding or gate,
        "expires_at": (datetime.now().timestamp() + 86400 * 7),  # 7 天有效
        "request": (
            f"这是 HGF 的 {gate} 评审包（nonce={nonce}）。请作为独立验证方"
            "（非 HGF 生态）审查以下代码/文档，输出：P0/P1/P2 问题 + 行级引用 "
            "+ PASS/FAIL 结论。返回时请回显 nonce 以绑定本请求。"
        ),
        "payload": pack_md,
        "external": True,  # D1：真标记，非伪签名
        "verifier_evidence": "pending",  # 待外部验证填充
        "payload_hash": hashlib.sha256(pack_md.encode("utf-8")).hexdigest()[:16],
    }


def record_external_verdict(
    working_dir: str,
    gate: str,
    verdict: str,
    evidence: str,
    verifier: str,
    nonce: str = "",
    payload_hash: str = "",
) -> dict:
    """记录外部验证结论（D2/D3 修正）。

    独立性保障：
    - reviewer 前缀 external:（可审计区分内部/外部）
    - verifier 传外部方名称（不硬编码 heavyskill）
    - nonce + payload_hash 绑定：防"外部结论被内部代码冒名"
    - 无伪签名：evidence 为外部方提供的实际验证证据（文本/报告摘要）
    """
    if not verifier or verifier == "heavyskill":
        raise ValueError(
            "外部验证必须指定 verifier（heavyskill 是同生态评审，不满足独立校准——V3.4-D）"
        )
    notes = (
        f"外部独立验证: {evidence}"
        + (f" [nonce={nonce}]" if nonce else "")
        + (f" [payload_hash={payload_hash}]" if payload_hash else "")
    )
    return record_review(
        working_dir,
        gate=gate,
        verdict=verdict,
        reviewer=f"external:{verifier}",
        verifier=verifier,
        notes=notes,
        kind="independent",
    )
