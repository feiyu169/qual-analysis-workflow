"""B5-2 数值转写归一预处理器测试

验收（路线图 B5-2）：
- 约/以上/区间/千分位/单位归一
- 拦截"4.102亿→410.2亿"类单位错误
- 复核命中原文才保留（未命中 → confidence=low）
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pytest

from finance.normalize_values import (
    parse_number_with_unit,
    unit_error_detect,
    verify_value_against_source,
)


def test_plain_yi():
    r = parse_number_with_unit("4.1亿")
    assert r["value_yi"] == pytest.approx(4.1)
    assert not r["approx"]


def test_approx_prefix():
    r = parse_number_with_unit("约4.1亿")
    assert r["value_yi"] == pytest.approx(4.1)
    assert r["approx"]


def test_thousand_sep_and_wan():
    """千分位 + 万 → 亿"""
    r = parse_number_with_unit("4,102.5万")
    assert r["value_yi"] == pytest.approx(0.41025, abs=5e-4)


def test_baiwan():
    """百万 → 亿"""
    r = parse_number_with_unit("410.2百万")
    assert r["value_yi"] == pytest.approx(4.102)


def test_range():
    r = parse_number_with_unit("4.1-4.3亿")
    assert r["value_yi"] == pytest.approx(4.2)
    assert r["range"]


def test_lower_bound():
    r = parse_number_with_unit("4亿以上")
    assert r["value_yi"] == pytest.approx(4.0)
    assert r["lower_bound"]


def test_unit_error_100x_detected():
    """拦截 100 倍单位错位：原文 4.102 亿，提取 410.2（万误作亿）"""
    assert unit_error_detect("日活用户4.102亿", 410.2) is False


def test_unit_error_10x_detected():
    """拦截 10 倍错位：原文 4.102 亿，提取 41.02"""
    assert unit_error_detect("日活用户4.102亿", 41.02) is False


def test_match_high_confidence():
    """原文数量级匹配 → high"""
    assert verify_value_against_source("日活用户4.102亿", 4.102) == "high"
    assert verify_value_against_source("约4.1亿", 4.1) == "high"


def test_mismatch_low_confidence():
    """原文未命中 → low"""
    assert verify_value_against_source("日活用户4.102亿", 410.2) == "low"


def test_unverifiable_defaults_high():
    """原文无法解析（非数值句）→ 不误报"""
    assert unit_error_detect("业务持续增长", 4.1) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
