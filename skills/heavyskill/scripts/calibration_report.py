"""二期：样本库校准报告（calibration_report）。

用样本库积累的人工裁决（adopt/reject）校准 quality_score 与结论可信度：
- 采纳率统计（total/adopted/rejected/pending/adoption_rate）
- 分桶采纳率（quality_score 4 桶，应单调递增）
- Spearman 秩相关（quality_score 排序 vs 采纳排序，N≥30 才做显著性检验）
- ROC-AUC（adopt=1/reject=0 的判别能力，>0.7 才有意义）
- 回归测试集（被 reject 的样本，供重放防退化）

阈值保护（裁判裁定）：N<20 quality_score 标记 insufficient_data；N<30 仅描述性统计。
依赖：scipy/numpy（工作区已装）。

用法：
    python scripts/calibration_report.py [--dir skills/heavyskill/data] [--json] [--regression]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)

from workflow.sample_registry import (
    MIN_SAMPLES_FOR_QUALITY,
    MIN_SAMPLES_FOR_STATS,
    read_samples,
)

try:
    import numpy as np
    from scipy import stats as sp_stats

    _HAS_SCIPY = True
except ImportError:  # pragma: no cover - 环境缺 scipy 时降级
    np = None
    sp_stats = None
    _HAS_SCIPY = False


# quality_score 分桶边界（与裁决书一致）
BUCKETS = [(0, 25), (25, 50), (50, 75), (75, 101)]


def _score_mean(payload: dict) -> Optional[float]:
    """从样本 payload 提取轨迹质量分均值（无则 None）。"""
    dist = payload.get("quality_score_distribution") or {}
    return dist.get("mean")


def _adoption_label(samples: List[dict]) -> List[int]:
    """adopt=1 / reject=0；pending/其他忽略（返回对应过滤后的样本与标签）。"""
    labeled = []
    for s in samples:
        v = (s.get("payload") or {}).get("verdict")
        if v == "adopt":
            labeled.append((s, 1))
        elif v == "reject":
            labeled.append((s, 0))
    return [s for s, _ in labeled], [l for _, l in labeled]


def bucket_adoption_rates(samples: List[dict]) -> List[Dict[str, Any]]:
    """按 quality_score 分桶统计采纳率（应单调递增；无分样本跳过）。"""
    rates = []
    for lo, hi in BUCKETS:
        bucket = [
            s
            for s in samples
            if (_score_mean(s.get("payload") or {}) or 0) >= lo
            and (_score_mean(s.get("payload") or {}) or 0) < hi
        ]
        if not bucket:
            continue
        adopted = sum(
            1 for s in bucket if (s.get("payload") or {}).get("verdict") == "adopt"
        )
        labeled = sum(
            1
            for s in bucket
            if (s.get("payload") or {}).get("verdict") in ("adopt", "reject")
        )
        rates.append(
            {
                "bucket": f"{lo}-{min(hi, 100)}",
                "samples": len(bucket),
                "labeled": labeled,
                "adoption_rate": round(adopted / labeled, 3) if labeled else None,
            }
        )
    return rates


def spearman_correlation(samples: List[dict]) -> Optional[Dict[str, Any]]:
    """quality_score vs 采纳 的 Spearman 秩相关（N≥30 才有统计意义）。"""
    labeled, labels = _adoption_label(samples)
    scored = [
        (s, l)
        for s, l in zip(labeled, labels)
        if _score_mean(s.get("payload") or {}) is not None
    ]
    if len(scored) < 10:
        return None
    xs = [(_score_mean(s.get("payload") or {}) or 0) for s, _ in scored]
    ys = [l for _, l in scored]
    if _HAS_SCIPY:
        rho, p = sp_stats.spearmanr(xs, ys)
        return {
            "rho": round(float(rho), 3),
            "p_value": round(float(p), 4),
            "n": len(scored),
            "significant": len(scored) >= MIN_SAMPLES_FOR_STATS and float(p) < 0.05,
        }

    # 降级：手算 Spearman（rank 后 Pearson）
    def _rank(vals):
        order = sorted(enumerate(vals), key=lambda x: x[1])
        ranks = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and order[j + 1][1] == order[i][1]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[order[k][0]] = avg
            i = j + 1
        return ranks

    rx, ry = _rank(xs), _rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    rho = num / den if den else 0.0
    return {
        "rho": round(rho, 3),
        "p_value": None,
        "n": len(scored),
        "significant": None,
    }


def roc_auc(samples: List[dict]) -> Optional[Dict[str, Any]]:
    """ROC-AUC：quality_score 预测 adopt/reject（Mann-Whitney U 等价）。"""
    labeled, labels = _adoption_label(samples)
    scored = [
        (_score_mean(s.get("payload") or {}) or 0, l)
        for s, l in zip(labeled, labels)
        if _score_mean(s.get("payload") or {}) is not None
    ]
    pos = [x for x, l in scored if l == 1]
    neg = [x for x, l in scored if l == 0]
    if not pos or not neg:
        return None
    if _HAS_SCIPY:
        # AUC = P(正样本分 > 负样本分)，用 Mann-Whitney U
        u_stat, p = sp_stats.mannwhitneyu(pos, neg, alternative="two-sided")
        auc = u_stat / (len(pos) * len(neg))
        return {
            "auc": round(float(auc), 3),
            "p_value": round(float(p), 4),
            "pos": len(pos),
            "neg": len(neg),
        }
    # 降级：枚举法（样本少时可用）
    wins = sum(1 for x in pos for y in neg if x > y)
    ties = sum(1 for x in pos for y in neg if x == y)
    auc = (wins + 0.5 * ties) / (len(pos) * len(neg))
    return {"auc": round(auc, 3), "p_value": None, "pos": len(pos), "neg": len(neg)}


def regression_set(samples: List[dict], limit: int = 20) -> List[Dict[str, Any]]:
    """回归测试集：被 reject 的样本（防退化重放）。"""
    out = []
    for s in samples:
        if (s.get("payload") or {}).get("verdict") == "reject":
            p = s.get("payload") or {}
            out.append(
                {
                    "sample_id": s.get("sample_id"),
                    "query_summary": (p.get("query_summary") or "")[:120],
                    "output_file": p.get("output_file"),
                }
            )
        if len(out) >= limit:
            break
    return out


def compute_calibration(samples: List[dict]) -> Dict[str, Any]:
    """完整校准报告（含阈值保护）。"""
    n = len(samples)
    adopted = sum(
        1 for s in samples if (s.get("payload") or {}).get("verdict") == "adopt"
    )
    rejected = sum(
        1 for s in samples if (s.get("payload") or {}).get("verdict") == "reject"
    )
    pending = n - adopted - rejected

    return {
        "total_samples": n,
        "adopted": adopted,
        "rejected": rejected,
        "pending": pending,
        "adoption_rate": round(adopted / n, 3) if n else None,
        "quality_score_calibrated": n >= MIN_SAMPLES_FOR_QUALITY,
        "stats_significant": n >= MIN_SAMPLES_FOR_STATS,
        "buckets": bucket_adoption_rates(samples),
        "spearman": spearman_correlation(samples),
        "roc_auc": roc_auc(samples),
        "regression_set_count": sum(
            1 for s in samples if (s.get("payload") or {}).get("verdict") == "reject"
        ),
        "note": _threshold_note(n),
    }


def _threshold_note(n: int) -> str:
    if n < MIN_SAMPLES_FOR_QUALITY:
        return (
            f"样本 {n} 条 < {MIN_SAMPLES_FOR_QUALITY}：quality_score 标记 "
            "insufficient_data，不参与决策（裁判裁定）"
        )
    if n < MIN_SAMPLES_FOR_STATS:
        return (
            f"样本 {n} 条 < {MIN_SAMPLES_FOR_STATS}：仅描述性统计"
            "（分桶采纳率），不做统计检验"
        )
    return f"样本 {n} 条 ≥ {MIN_SAMPLES_FOR_STATS}：可做统计检验（Spearman/AUC）"


def render_text(report: dict) -> str:
    lines = [
        "=" * 56,
        "HeavySkill 样本库校准报告",
        "=" * 56,
        (
            f"样本: {report['total_samples']} | 采纳 {report['adopted']} / "
            f"拒绝 {report['rejected']} / 待裁决 {report['pending']}"
        ),
        f"采纳率: {report['adoption_rate']}",
        (
            f"quality_score 校准: "
            f"{'✅ 可用' if report['quality_score_calibrated'] else '⚠️ insufficient_data'} | "
            f"统计显著: {'✅' if report['stats_significant'] else '⚠️ 仅描述性'}"
        ),
        report["note"],
    ]
    if report["buckets"]:
        lines.append("")
        lines.append("分桶采纳率（quality_score → 采纳率，应单调递增）:")
        for b in report["buckets"]:
            lines.append(
                f"  [{b['bucket']}): {b['labeled']} 条已裁决, "
                f"采纳率 {b['adoption_rate']}"
            )
    if report["spearman"]:
        s = report["spearman"]
        lines.append(
            f"Spearman ρ={s['rho']} (n={s['n']}"
            + (f", p={s['p_value']}" if s["p_value"] is not None else "")
            + (", 显著" if s["significant"] else "")
            + ")"
        )
    if report["roc_auc"]:
        a = report["roc_auc"]
        lines.append(f"ROC-AUC={a['auc']} (pos={a['pos']}, neg={a['neg']})")
    if report["regression_set_count"]:
        lines.append(f"回归测试集: {report['regression_set_count']} 条被拒绝样本")
    lines.append("=" * 56)
    return "\n".join(lines)


def main() -> int:
    # Windows 控制台 GBK 无法编码 emoji（⚠️/✅），强制 UTF-8
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, OSError):
                pass

    parser = argparse.ArgumentParser(description="HeavySkill 样本库校准报告")
    parser.add_argument(
        "--dir", default=None, help="样本库目录（默认 skills/heavyskill/data）"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--regression", action="store_true", help="列出回归测试集")
    args = parser.parse_args()

    samples = read_samples(sample_dir=args.dir, limit=100000)
    report = compute_calibration(samples)
    if args.regression:
        report["regression_set"] = regression_set(samples)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
        if args.regression:
            for r in report.get("regression_set", []):
                print(f"  reject: {r['sample_id']} | {r['query_summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
