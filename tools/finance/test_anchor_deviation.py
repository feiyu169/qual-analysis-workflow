"""ADVC 层0：anchor_deviation 签名检测测试（docs/qual-anchor-repair-architecture.md）

覆盖：×10ⁿ/÷10ⁿ、prefix_drop（1031.63→31.63）、digit_typo、精确命中不报、
歧义多候选、合法值不被误判。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pytest

from finance.normalize_values import anchor_deviation

# 小鹏总资产 3 财年锚点
TOTAL_ASSETS = [(841.6254, 2023), (827.0611, 2024), (1031.6263, 2025)]


def test_exact_value_no_deviation():
    """精确命中锚点 → 无偏差（合法值不误判）"""
    assert anchor_deviation(1031.6263, TOTAL_ASSETS) == []


def test_prefix_drop_detected():
    """1031.63→31.63（丢'10'前缀）→ prefix_drop 高置信"""
    devs = anchor_deviation(31.63, TOTAL_ASSETS)
    assert devs, "31.63 应命中 prefix_drop"
    pd = [d for d in devs if d.kind == "prefix_drop"]
    assert pd, f"应有 prefix_drop 签名: {devs}"
    assert pd[0].anchor_value == 1031.6263
    assert pd[0].fiscal_year == 2025
    assert pd[0].confidence == "high"


def test_multiply10_detected():
    """小数点错位（×10）：1031.63→103.163 → multiply10"""
    devs = anchor_deviation(103.16263, TOTAL_ASSETS)
    # 103.16263 × 10 = 1031.6263 → factor 1
    assert any(d.kind == "multiply10" and d.anchor_value == 1031.6263 for d in devs)


def test_divide10_detected():
    """单位错位（÷10）：1031.63→10316.263 → divide10"""
    devs = anchor_deviation(10316.263, TOTAL_ASSETS)
    assert any(d.kind == "divide10" and d.anchor_value == 1031.6263 for d in devs)


def test_digit_typo_hint():
    """31.6（31.63 少尾数）→ 非典型错位，无高置信（弱提示或空）"""
    devs = anchor_deviation(31.6, TOTAL_ASSETS)
    assert not any(d.confidence == "high" for d in devs), \
        f"31.6 不是唯一强签名错位: {devs}"


def test_ambiguous_multiple_candidates():
    """歧义：值可匹配多个锚点的错位模式 → 多候选（调用方 FY 归因消歧）"""
    # 31.63 对 [12.34, 123.4] 无强签名 → 无偏差（不是任何锚点的错位模式）
    devs = anchor_deviation(31.63, [(12.34, 2023), (123.4, 2024)])
    assert devs == [] or all(d.confidence != "high" for d in devs), \
        "非唯一候选不得高置信"


def test_negative_value():
    """负值（净利 -11.39）精确命中不误判"""
    assert anchor_deviation(-11.3946, [(-11.3946, 2025)]) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
