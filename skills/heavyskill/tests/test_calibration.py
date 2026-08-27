"""二期样本库校准单测：分桶采纳率 / Spearman / AUC / 阈值保护 / 回归集。

运行：
    cd skills/heavyskill && python -m pytest tests/test_calibration.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workflow.sample_registry import (
    MIN_SAMPLES_FOR_QUALITY,
    MIN_SAMPLES_FOR_STATS,
)


def _sample(sid, score, verdict=None):
    """构造样本 dict（payload 含质量分均值 + 裁决）。"""
    return {
        "sample_id": sid,
        "schema": "hsk-sample.v1",
        "payload": {
            "query_summary": f"q-{sid}",
            "quality_score_distribution": {"mean": score, "min": score, "max": score},
            "verdict": verdict,
        },
    }


def test_bucket_adoption_rates_monotonic():
    from scripts.calibration_report import bucket_adoption_rates

    samples = [
        # 低分桶（0-25）：多拒绝
        _sample("s1", 10, "reject"),
        _sample("s2", 15, "reject"),
        _sample("s3", 20, "adopt"),
        # 中分桶（50-75）：一半
        _sample("s4", 55, "reject"),
        _sample("s5", 60, "adopt"),
        # 高分桶（75-100）：全采纳
        _sample("s6", 80, "adopt"),
        _sample("s7", 90, "adopt"),
        _sample("s8", 95, "adopt"),
    ]
    rates = bucket_adoption_rates(samples)
    by_bucket = {r["bucket"]: r["adoption_rate"] for r in rates}
    assert by_bucket["0-25"] < by_bucket["50-75"] < by_bucket["75-100"]
    assert by_bucket["0-25"] == round(1 / 3, 3)


def test_spearman_correlation_monotonic():
    from scripts.calibration_report import spearman_correlation

    # 单调正相关：score 越高越 adopt（二值 y 有大量 ties，
    # scipy 平均秩处理使完美单调的 ρ≈0.87 而非 1——统计上正确且偏保守）
    samples = [
        _sample(f"s{i}", score, "adopt" if i >= 10 else "reject")
        for i, score in enumerate(range(10, 30))
    ]
    r = spearman_correlation(samples)
    assert r is not None
    assert r["rho"] > 0.85
    assert r["n"] == 20


def test_spearman_insufficient_n_returns_none():
    from scripts.calibration_report import spearman_correlation

    assert spearman_correlation([_sample("s1", 50, "adopt")] * 3) is None


def test_roc_auc_perfect_discrimination():
    from scripts.calibration_report import roc_auc

    # 完美判别：正样本分全高于负样本 → AUC=1
    samples = [
        _sample(f"s{score}", score, "adopt" if score > 70 else "reject")
        for score in range(40, 101)
    ]
    a = roc_auc(samples)
    assert a is not None
    assert a["auc"] == 1.0
    assert a["pos"] >= 20 and a["neg"] >= 20


def test_threshold_protection():
    from scripts.calibration_report import compute_calibration

    # N < 20 → insufficient_data；N < 30 → 仅描述性
    small = compute_calibration([_sample(f"s{i}", 50, "adopt") for i in range(5)])
    assert small["quality_score_calibrated"] is False
    assert small["stats_significant"] is False
    assert "insufficient_data" in small["note"]

    mid = compute_calibration([_sample(f"s{i}", 50, "adopt") for i in range(25)])
    assert mid["quality_score_calibrated"] is True
    assert mid["stats_significant"] is False


def test_adoption_rate_and_regression_set():
    from scripts.calibration_report import compute_calibration, regression_set

    samples = [
        _sample("a1", 80, "adopt"),
        _sample("a2", 60, "reject"),
        _sample("a3", 70, None),  # pending
    ]
    report = compute_calibration(samples)
    assert report["total_samples"] == 3
    assert report["adoption_rate"] == round(1 / 3, 3)
    assert report["regression_set_count"] == 1
    reg = regression_set(samples)
    assert len(reg) == 1 and reg[0]["sample_id"] == "a2"


def test_calibration_status_in_registry_consistent():
    """sample_registry.quality_calibration_status 与 calibration 阈值一致。"""
    from scripts.calibration_report import MIN_SAMPLES_FOR_QUALITY as Q2

    assert Q2 == MIN_SAMPLES_FOR_QUALITY
    assert MIN_SAMPLES_FOR_STATS >= MIN_SAMPLES_FOR_QUALITY
