"""ADVC 黄金回归集（P2：T3 案例回流负样本——防校验器回退，docs/qual-numeric-repair-blueprint.md §六）

历史错例固化为 golden set：任何校验/回填改动必须全量通过
（防"修好一个错位、放开十个错位"）。

正样本（必须修复）：真实转写错位（1031.63→31.63 等）
负样本（必须不动）：合法精确值 / 历史财年引用 / 近似语境 / 幻觉值只标注不替换
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pytest

from finance.qual_v8.anchor_repair import repair_chapter_values, sweep_all_chapters
from finance.qual_v8.data_anchor import _anchor_cache, get_data_anchor

# 小鹏 3 年数据（真实 Wind 锚点——2023/2024/2025）
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


# ============ 正样本：真实错位必须修复 ============

GOLDEN_POSITIVE = [
    # (场景, 内容, 章节, 期望修复后的数值串)
    ("prefix_drop 总资产", "公司总资产31.63亿元，规模扩大。", 6, "1031.63"),
    ("multiply10 归母净利润", "归母净利润-1.13946亿元，亏损收窄。", 3, "-11.3946"),
    ("divide10 营业收入", "营业收入76.71974亿元。", 2, "767.1974"),
    ("prefix_drop 总资产(2023锚点)", "2023年总资产84.16254亿元。", 6, "841.6254"),
]


@pytest.mark.parametrize("scene,content,ch,expected", GOLDEN_POSITIVE)
def test_golden_positive_must_fix(scene, content, ch, expected):
    """黄金正样本：历史真实错位必须被确定性修复（自证通过）"""
    result = repair_chapter_values(ch, content, _anchor())
    assert result.fixes, f"[{scene}] 应有修复: {content}"
    assert expected in result.content, (
        f"[{scene}] 修复后应含 {expected}，实为: {result.content}"
    )
    # 自证：修复后整章必须通过校验器（fail-closed 同一把尺）
    assert not _anchor().validate_chapter_any_fy(ch, result.content), \
        f"[{scene}] 修复后自证必须通过"


# ============ 负样本：合法值必须不动 ============

GOLDEN_NEGATIVE_UNTOUCHED = [
    # (场景, 内容, 章节)
    ("精确命中最新财年", "总资产1031.63亿元，规模扩大。", 6),
    ("历史财年引用(2024)", "2024年总资产827.06亿元，较上年增长。", 6),
    ("历史财年引用(2023)", "2023年总资产841.63亿元。", 6),
    ("精确命中营收", "营业收入767.20亿元，同比增长显著。", 2),
    ("近似语境(约)", "总资产约1031.63亿元。", 6),
]


@pytest.mark.parametrize("scene,content,ch", GOLDEN_NEGATIVE_UNTOUCHED)
def test_golden_negative_untouched(scene, content, ch):
    """黄金负样本：合法/近似值必须原样保留（逐字节不动，零误修）"""
    result = repair_chapter_values(ch, content, _anchor())
    assert not result.fixes, f"[{scene}] 不应有修复: {content}"
    assert result.content == content, f"[{scene}] 内容不应被改动"


# ============ 负样本：幻觉值只标注不替换 ============

def test_golden_hallucination_annotate_only():
    """幻觉值（无任何错位签名）→ T3 只标注，内容不动（绝不猜测替换）"""
    content = "总资产999.00亿元，公司规模扩大。"
    result = repair_chapter_values(6, content, _anchor())
    assert not result.fixes
    assert result.unresolved, "幻觉值应进 T3 未解决清单"
    assert result.unresolved[0].reason == "no_signature"
    assert result.content == content


# ============ P2：digit_typo 弱提示（hints 通道，不阻断） ============

def test_digit_typo_hint_not_blocking():
    """弱签名（百位单字差异：1131.63 vs 锚点 1031.63）→ hints 提示，不修复不阻断（T2 关）"""
    content = "总资产1131.63亿元。"  # 数字串"113163" vs "103163" 差 1 位 → digit_typo 弱签名
    result = repair_chapter_values(6, content, _anchor())
    assert not result.fixes, "弱签名默认不自动替换（T2 关）"
    assert result.hints, "弱签名应进 hints 提示通道"
    assert all(h.reason == "digit_typo_hint" for h in result.hints)
    assert result.content == content, "提示不改内容"


# ============ P1：T2 低置信开关 ============

def test_t2_enable_low_confidence_repair():
    """T2 开：弱签名 + FY 上下文唯一目标 → 仍可替换（自证兜底）"""
    from finance.qual_v8.data_anchor import DataAnchor

    # 单锚点指标（归母净资产仅 FY2025=100.0）→ FY 上下文唯一
    anchor = DataAnchor()
    anchor.set_anchor("归母净资产", 100.0, "亿元", "Wind", fiscal_year=2025)
    content = "归母净资产103.0亿元。"  # 103 vs 100：超1%容差 + 编辑距离1 → digit_typo 弱签名
    result_off = repair_chapter_values(5, content, anchor)
    assert not result_off.fixes, "T2 默认关：弱签名不替换"
    assert result_off.hints, "T2 关时弱签名进 hints"

    result_on = repair_chapter_values(5, content, anchor, enable_t2=True)
    assert result_on.fixes, "T2 开：唯一目标弱签名可替换"
    assert result_on.fixes[0].confidence == "low"
    assert "100" in result_on.content.replace("100.0", "100"), \
        f"修复后应含 100.0，实为: {result_on.content}"


def test_t2_ambiguous_weak_signature_stays_hint():
    """T2 开但弱签名目标歧义（多候选）→ 仍只提示不替换"""
    from finance.qual_v8.data_anchor import DataAnchor

    # 双锚点（100.0 / 101.0）：103 对两者均 digit_typo → 多候选歧义
    anchor = DataAnchor()
    anchor.set_anchor("归母净资产", 100.0, "亿元", "Wind", fiscal_year=2024)
    anchor.set_anchor("归母净资产", 101.0, "亿元", "Wind", fiscal_year=2025)
    content = "归母净资产103.0亿元。"
    result = repair_chapter_values(5, content, anchor, enable_t2=True)
    assert not result.fixes, "多候选弱签名不得替换（歧义不猜测）"
    assert result.hints, "歧义弱签名应进 hints"
    assert result.content == content


# ============ 幂等：修复后重跑无新修复 ============

def test_golden_idempotent():
    """黄金回归：修复后再次运行零新修复（防重复改写）"""
    content = "公司总资产31.63亿元。"
    r1 = repair_chapter_values(6, content, _anchor())
    assert r1.fixes
    r2 = repair_chapter_values(6, r1.content, _anchor())
    assert not r2.fixes, "修复后应幂等"


# ============ sweep 4 元组契约 ============

def test_sweep_returns_hints_channel():
    """sweep 返回 4 元组（fixed, fixes, unresolved, hints）——P2 hints 通道契约"""
    # 幻觉值放独立章节——避免与错位修复同章触发"自证失败→整体回滚"（设计如此）
    chapters = {6: "总资产31.63亿元。", 7: "总资产999.00亿元。"}
    _fixed, fixes, unresolved, hints = sweep_all_chapters(chapters, _anchor())
    assert fixes, "错位应修复"
    assert unresolved, "幻觉值应进未解决"
    assert isinstance(hints, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
