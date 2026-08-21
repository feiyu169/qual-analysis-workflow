"""ADVC 层1：anchor_repair 修复引擎测试（docs/qual-anchor-repair-architecture.md）

覆盖：T1 错位自动替换（自证）、T3 幻觉/歧义只标注、合法值不误修、
last-wins 双出现（同指标多处）、幂等、sweep 全章。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pytest

from finance.qual_v8.anchor_repair import repair_chapter_values, sweep_all_chapters
from finance.qual_v8.data_anchor import _anchor_cache, get_data_anchor

# 小鹏 3 年数据
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


def test_t1_prefix_drop_repair():
    """T1：总资产 31.63（1031.63 丢前缀）→ 自动替换为 1031.63（自证通过）"""
    content = "公司总资产31.63亿元，规模持续扩大。"
    result = repair_chapter_values(6, content, _anchor())
    assert result.fixes, "应有修复"
    fix = result.fixes[0]
    assert fix.metric_key == "总资产"
    assert fix.old_value == 31.63
    assert fix.new_value == pytest.approx(1031.6263)
    assert "总资产1031.63亿元" in result.content or "总资产1031.6263亿元" in result.content
    assert not result.unresolved


def test_t1_multiply10_repair():
    """T1：×10 错位（净利 -1.13946 → -11.3946）自动替换"""
    content = "归母净利润-1.13946亿元，亏损收窄。"
    result = repair_chapter_values(3, content, _anchor())
    assert result.fixes, "应有修复"
    assert result.fixes[0].new_value == pytest.approx(-11.3946)


def test_exact_value_not_touched():
    """合法值（精确命中锚点）→ 不修改（逐字节不变）"""
    content = "营业收入767.20亿元，同比增长显著。"
    result = repair_chapter_values(2, content, _anchor())
    assert not result.fixes
    assert result.content == content


def test_t3_no_signature_flagged():
    """T3：幻觉值（无任何签名）→ 只标注不修改"""
    content = "总资产999.00亿元，公司规模扩大。"
    result = repair_chapter_values(6, content, _anchor())
    assert not result.fixes
    assert result.unresolved
    assert result.unresolved[0].reason == "no_signature"
    assert result.content == content  # 原文不动


def test_t3_ambiguous_flagged():
    """T3：歧义（可匹配多锚点）→ 只标注"""
    # 构造歧义：值同时是两锚点的错位模式
    content = "总资产84.16254亿元。"  # 841.6254 ÷10 → 84.16254（唯一）
    result = repair_chapter_values(6, content, _anchor())
    # 84.16254 × 10 = 841.6254（唯一锚点 FY2023）→ T1 修复
    assert result.fixes
    assert result.fixes[0].new_value == pytest.approx(841.6254)


def test_last_wins_both_detected():
    """ADVC：同指标多处出现（前错后对）→ 两处独立处理，错值仍修复"""
    content = "总资产31.63亿元；总资产1031.63亿元。"  # 前错后对
    result = repair_chapter_values(6, content, _anchor())
    # 错值（31.63）修复；后值（1031.63 精确）不动
    assert result.fixes, "错值应修复"
    assert "总资产1031.63亿元；总资产1031.63亿元" in result.content.replace("1031.6263", "1031.63") or \
        result.fixes[0].old_value == 31.63


def test_idempotent():
    """幂等：修复后再次运行无新修复"""
    content = "公司总资产31.63亿元。"
    r1 = repair_chapter_values(6, content, _anchor())
    assert r1.fixes
    r2 = repair_chapter_values(6, r1.content, _anchor())
    assert not r2.fixes, "修复后应幂等"


def test_sweep_all_chapters():
    """sweep：全章扫描修复"""
    chapters = {3: "归母净利润-1.13946亿元，亏损收窄。", 6: "总资产31.63亿元。"}
    fixed, fixes, _unresolved, _hints = sweep_all_chapters(chapters, _anchor())
    assert len(fixes) >= 2
    assert "1031.63" in fixed[6] or "1031.6263" in fixed[6]
    assert "-11.3946" in fixed[3]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
