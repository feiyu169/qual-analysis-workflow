"""PGNB 数字回填器测试（docs/qual-pgnb-architecture.md）

验证：LLM 占位符 → 程序按锚点回填（零幻觉）；无锚点 → [数据待核]；FY 标注正确。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pytest

from finance.qual_v8.data_anchor import _anchor_cache, get_data_anchor
from finance.qual_v8.numeric_binder import bind_placeholders

XPENG_WIND = {
    "income": {
        "归母净利润": [-103.7578, -57.9026, -11.3946],
        "营业收入": [306.7607, 408.6631, 767.1974],
        "营业利润": [-113.8436, -74.8161, -44.1552],
    },
    "balance": {
        "总资产": [841.6254, 827.0611, 1031.6263],
        "年负债合计": [478.3401, 514.3132, 727.9404],
        "年所有者权益合计": [363.2853, 312.7479, 303.6859],
    },
    "cashflow": {"经营活动现金流量净额": [9.5616, -20.1234, 82.5853]},
    "_year_labels": {"财年": [2023, 2024, 2025]},
}


def setup_function():
    _anchor_cache.clear()


def _anchor():
    return get_data_anchor(XPENG_WIND)


def test_bind_latest_fy():
    """占位符默认回填最新财年值（LLM 幻觉根治——数字全部程序注入）"""
    content = "公司营业收入[{{营业收入}}]亿元，规模扩大。"
    bound, unresolved = bind_placeholders(content, _anchor(), 6)
    assert "FY2025 767.20" in bound, f"应回填 FY2025 营收: {bound}"
    assert not unresolved


def test_bind_specific_fy():
    """指定财年回填（[{{指标:2023}}] → FY2023 值）"""
    content = "2023年总资产[{{总资产:2023}}]亿元。"
    bound, _ = bind_placeholders(content, _anchor(), 6)
    assert "FY2023 841.63" in bound, f"应回填 FY2023 总资产: {bound}"


def test_bind_negative_value_keeps_sign():
    """负值（亏损）回填保留符号（正负号不得改动铁律）"""
    content = "归母净利润[{{归母净利润}}]亿元，亏损收窄。"
    bound, _ = bind_placeholders(content, _anchor(), 3)
    assert "FY2025 -11.39" in bound, f"应回填 FY2025 净利（负值）: {bound}"


def test_bind_unresolved_keeps_marker():
    """无锚点占位符 → 保留 [数据待核] + warning（不静默，不编造）"""
    content = "研发费用[{{研发费用}}]亿元。"
    bound, unresolved = bind_placeholders(content, _anchor(), 6)
    assert "[数据待核:研发费用]" in bound, f"无锚点应保留数据待核: {bound}"
    assert unresolved, "应有未解析记录"


def test_bind_no_placeholder_passthrough():
    """无占位符内容原样返回（不误改）"""
    content = "公司经营稳健，毛利率持续改善。"
    bound, unresolved = bind_placeholders(content, _anchor(), 6)
    assert bound == content
    assert not unresolved


def test_bind_multi_placeholders():
    """多占位符一次回填（营收+净利）"""
    content = "营收[{{营业收入}}]亿元，净利[{{归母净利润}}]亿元。"
    bound, _ = bind_placeholders(content, _anchor(), 5)
    assert "FY2025 767.20" in bound
    assert "FY2025 -11.39" in bound


def test_bind_no_hallucination_when_llm_compliant():
    """端到端：LLM 按占位符规范输出 → 零幻觉数字（对比：旧方式 LLM 写 14.0）"""
    # 旧方式：LLM 自由写 → 幻觉 14.0（不匹配任一财年锚点）
    llm_bad = "公司营业收入14.0亿元。"
    bad_errors = _anchor().validate_chapter_any_fy(3, llm_bad)
    assert bad_errors, "旧方式幻觉数字被校验器拦截（但消耗预算返工）"

    # PGNB：LLM 写占位符 → 程序回填 → 零幻觉
    llm_placeholder = "公司营业收入[{{营业收入}}]亿元。"
    bound, _ = bind_placeholders(llm_placeholder, _anchor(), 3)
    assert "767.20" in bound
    errors_after = _anchor().validate_chapter_any_fy(3, bound)
    assert not errors_after, f"PGNB 回填后必须通过校验器: {errors_after}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
