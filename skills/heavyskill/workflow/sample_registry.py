"""P54-增强-二期：样本库（sample registry，一期埋采集 hook）。

存储：skills/heavyskill/data/samples.jsonl（hsk.v1 信封，HeavySkill 私有——
保持自包含，与 HGF 的 .hgf/ 零依赖；格式与 hgf.v1 同构，未来可无损迁移）。

一期职责：record_sample（采集占位，pipeline 后自动调用）、read_samples（tail 语义）、
adjudicate（人工裁决 + audit log + adjudicator 双签名字段）。
二期职责：quality_score 校准统计、采纳率、回归测试集（scripts/calibration_report.py）。

校准阈值（裁判裁定）：样本 <20 时 quality_score 标记 insufficient_data；
N<30 只做描述性统计（分桶采纳率）。
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent.parent  # skills/heavyskill/
DEFAULT_SAMPLE_DIR = _HERE / "data"
SAMPLE_FILE = "samples.jsonl"
AUDIT_FILE = "samples-audit.jsonl"

# 校准阈值（裁判裁定）
MIN_SAMPLES_FOR_QUALITY = 20  # <20 时 quality_score 标记 insufficient_data
MIN_SAMPLES_FOR_STATS = 30  # <30 只做描述性统计


def _sample_path(sample_dir: Optional[str] = None) -> Path:
    d = Path(sample_dir) if sample_dir else DEFAULT_SAMPLE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d / SAMPLE_FILE


def _audit_path(sample_dir: Optional[str] = None) -> Path:
    d = Path(sample_dir) if sample_dir else DEFAULT_SAMPLE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d / AUDIT_FILE


def _append_jsonl(path: Path, record: dict) -> None:
    """JSONL 追加写（append-only；并发写风险低——CLI/桥低频，损坏只影响单行）。"""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def record_sample(
    result,
    config,
    sample_dir: Optional[str] = None,
    query_summary: str = "",
) -> str:
    """记录一次审查为样本（hsk.v1 信封），返回 sample_id。

    Args:
        result: HeavySkillResult（或带 to_dict() 的结果对象）。
        config: HeavySkillConfig（记录模型/预算配置）。
        sample_dir: 覆盖样本目录（默认 skills/heavyskill/data/）。
        query_summary: query 摘要（前 200 字符；默认从 result.query 截取）。

    Returns:
        sample_id。
    """
    d = result.to_dict()
    q = query_summary or (d.get("query") or "")[:200]
    sid = f"hsk-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
    record = {
        "schema": "hsk-sample.v1",
        "kind": "hsk-sample",
        "writer": "hsk-sample",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sample_id": sid,
        "payload": {
            "query_summary": q,
            "final_answer": d.get("final_answer") or "",
            "consensus_answer": d.get("consensus_answer") or "",
            "truncation": d.get("truncation", {}),
            "k_extended": d.get("k_extended", False),
            "k": getattr(config, "reason_k", None),
            "mode": "enhanced"
            if getattr(config, "enable_validator", False)
            else "basic",
            "model": getattr(config, "model", None),
            "validator_model": getattr(config, "validator_model", None),
            "total_tokens": d.get("total_tokens"),
            "latency_seconds": d.get("total_latency_seconds"),
            "validation_verdict": (d.get("validation") or {}).get("verdict"),
            "second_review_verdict": (d.get("second_review") or {}).get(
                "final_verdict"
            ),
            "second_review_conflict": (d.get("second_review") or {}).get("conflict"),
            # 人工裁决（null=待裁决）；质量分校准的基础字段
            "verdict": None,
            "verdict_notes": None,
            "verdict_timestamp": None,
            "adjudicator": None,
            # quality_score 分布（可用时）
            "quality_score_distribution": _quality_distribution(result),
        },
    }
    _append_jsonl(_sample_path(sample_dir), record)
    return sid


def _quality_distribution(result) -> Optional[Dict[str, float]]:
    """从 cache_stats 提取轨迹质量分分布（无则 None）。"""
    stats = (
        (result.to_dict().get("cache_stats") or {})
        if hasattr(result, "to_dict")
        else {}
    )
    return stats.get("quality_distribution") or None


def read_samples(
    sample_dir: Optional[str] = None,
    limit: int = 50,
    verdict_filter: Optional[str] = None,
) -> List[dict]:
    """读取最近 N 条样本（tail 语义，不全量解析超大文件）。"""
    path = _sample_path(sample_dir)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out: List[dict] = []
    for line in lines[-limit:]:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # 容忍单行损坏（并发写/中断）
        if verdict_filter and rec.get("payload", {}).get("verdict") != verdict_filter:
            continue
        out.append(rec)
    return out


def adjudicate(
    sample_id: str,
    verdict: str,
    notes: str = "",
    adjudicator: str = "agent",
    sample_dir: Optional[str] = None,
) -> bool:
    """更新样本的人工裁决（双签名：adjudicator + audit 追加）。

    防伪造（裁判准出）：裁决写入 audit log（samples-audit.jsonl），
    记录 adjudicator / 原 verdict / 新 verdict / 时间。
    """
    if verdict not in ("adopt", "reject", "amend"):
        raise ValueError(f"verdict 必须为 adopt/reject/amend，got {verdict}")
    path = _sample_path(sample_dir)
    if not path.exists():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("sample_id") == sample_id:
            old_verdict = rec.get("payload", {}).get("verdict")
            rec["payload"]["verdict"] = verdict
            rec["payload"]["verdict_notes"] = notes
            rec["payload"]["verdict_timestamp"] = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            )
            rec["payload"]["adjudicator"] = adjudicator
            lines[i] = json.dumps(rec, ensure_ascii=False)
            found = True
            # audit log（防伪造）
            _append_jsonl(
                _audit_path(sample_dir),
                {
                    "schema": "hsk-audit.v1",
                    "kind": "hsk-audit",
                    "writer": adjudicator,
                    "timestamp": datetime.now(timezone.utc).isoformat(
                        timespec="seconds"
                    ),
                    "sample_id": sample_id,
                    "old_verdict": old_verdict,
                    "new_verdict": verdict,
                    "notes": notes,
                },
            )
            break
    if not found:
        return False
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def quality_calibration_status(sample_dir: Optional[str] = None) -> Dict[str, Any]:
    """样本库校准状态（二期统计的前置：样本量是否足够）。"""
    samples = read_samples(sample_dir, limit=100000)
    adopted = sum(
        1 for s in samples if (s.get("payload") or {}).get("verdict") == "adopt"
    )
    rejected = sum(
        1 for s in samples if (s.get("payload") or {}).get("verdict") == "reject"
    )
    n = len(samples)
    return {
        "total_samples": n,
        "adopted": adopted,
        "rejected": rejected,
        "adoption_rate": round(adopted / n, 3) if n else None,
        "quality_score_calibrated": n >= MIN_SAMPLES_FOR_QUALITY,
        "stats_significant": n >= MIN_SAMPLES_FOR_STATS,
        "note": (
            f"样本 {n} 条：{'≥20 可校准 quality_score' if n >= MIN_SAMPLES_FOR_QUALITY else '<20 quality_score 标记 insufficient_data（裁判裁定）'}；"
            f"{'≥30 可做统计检验' if n >= MIN_SAMPLES_FOR_STATS else '<30 仅描述性统计'}"
        ),
    }
