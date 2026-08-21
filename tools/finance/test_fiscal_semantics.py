"""FiscalSemantics 财年语义单源化测试（架构级长效方案）

三层防线：
- L1 归因服务：attribute_value 数值→财年（DataAnchor 单源）
- L2 跨章检查器：未标注引用按归因分桶（消除"历史引用挤进最新桶"误报）
- L3 生成时校验：validate_fiscal_references 前移拦截未标注历史引用
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pytest

from finance.qual_v8.data_anchor import (
    _anchor_cache,
    get_data_anchor,
    validate_fiscal_references,
)

# 小鹏 3 年数据（xpev-wind.json 同构）
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


# ===== L1 归因服务（合并为单用例——归因/未命中/历史标记一次覆盖） =====

def test_attribute_attribution():
    """L1：归因服务——命中→财年、未命中→None、历史/最新标记"""
    anchor = get_data_anchor(XPENG_WIND)
    # 命中历史/最新锚点
    assert anchor.attribute_value("总资产", 841.6254)[0] == 2023
    assert anchor.attribute_value("总资产", 1031.6263)[0] == 2025
    # 未命中 → None
    fy, matched = anchor.attribute_value("总资产", 9999.0)
    assert fy is None and matched is None
    # 历史/最新标记
    r = anchor.attribute_text_value("总资产", 841.6254)
    assert r["fiscal_year"] == 2023 and r["is_historical"] is True and r["is_latest"] is False
    r2 = anchor.attribute_text_value("总资产", 1031.6263)
    assert r2["fiscal_year"] == 2025 and r2["is_historical"] is False and r2["is_latest"] is True


# ===== L2 跨章归因（消除历史引用误报） =====

def test_cross_chapter_historical_attribution_no_false_positive():
    """L2：ch6 写 841.63（FY2023 未标注）vs ch3 写 1031.63（FY2025）→ 不同桶不误报"""
    from finance.quality.cross_chapter_consistency import (
        check_cross_chapter_consistency,
    )

    chapters = {
        3: "总资产1031.63亿元，公司规模持续扩大。",
        6: "总资产841.63亿元，较历史高点有所波动。",  # 841.63 = FY2023 值（历史引用）
    }
    result = check_cross_chapter_consistency(chapters, wind_data=XPENG_WIND)
    # 归因后 ch6 的 841.63 进 FY2023 桶，ch3 的 1031.63 进 FY2025 桶 → 无同桶冲突
    cross_conflicts = [i for i in result.issues if i.issue_type == "data_conflict"]
    assert not cross_conflicts, f"历史引用归因后不应跨章误报: {cross_conflicts}"


def test_cross_chapter_same_year_conflict_still_detected():
    """L2：同财年真冲突仍拦截（归因不掩盖真实错误）"""
    from finance.quality.cross_chapter_consistency import (
        check_cross_chapter_consistency,
    )

    chapters = {
        3: "总资产1031.63亿元。",
        5: "总资产999.00亿元。",  # 最新财年桶内的真冲突（999 vs 1031.63）
    }
    result = check_cross_chapter_consistency(chapters, wind_data=XPENG_WIND)
    cross_conflicts = [i for i in result.issues if i.issue_type == "data_conflict"]
    assert cross_conflicts, "同财年真冲突应仍被拦截"


# ===== L3 生成时校验（问题前移） =====

def test_minimal_e2e_gate4_no_historical_false_positive(monkeypatch):
    """最小端到端：复现 Gate4 失败根因场景（ch3 当期 1031.63 vs ch6 历史 841.63 未标注）

    走 review_and_repair_loop 静态审查路径（LLM 审查 mock 掉，仅 deep 静态跨章归因）——
    验证 FiscalSemantics 后不再报"总资产最新财年矛盾"（Gate4 失败项消除）。
    """
    from unittest.mock import MagicMock

    import finance.quality.review_repair_loop as m
    from finance.quality.review_repair_loop import review_and_repair_loop

    monkeypatch.setattr(m, "_run_substantive_review", lambda *a, **k: [])

    # 精确复现小鹏 Gate4 失败场景：ch3 写 1031.63（FY2025 当期）、ch6 写 841.63（FY2023 历史未标注）
    chapters = {
        3: "总资产1031.63亿元，公司规模持续扩大。",
        6: "总资产841.63亿元，财务结构稳健。",
    }

    def fake_caller(name, prompt):
        return '{"patches": []}'

    result = review_and_repair_loop(
        chapters=chapters,
        ctx=MagicMock(),
        llm_caller=fake_caller,
        wind_data=XPENG_WIND,
        max_rounds=1,
        skip_repair=True,
    )

    # 归因后 ch6 的 841.63 进 FY2023 桶 → 不再与 ch3 的 FY2025 值判矛盾
    false_positives = [
        i for i in result.remaining_issues
        if "总资产" in i and "最新财年" in i
    ]
    assert not false_positives, f"历史引用不应报最新财年矛盾: {false_positives}"

def test_validate_fiscal_references_detects_unlabeled_historical():
    """L3：未标注历史引用（841.63 无 FY 标注）→ 记问题"""
    issues = validate_fiscal_references(6, "总资产841.63亿元，财务结构稳健。", XPENG_WIND)
    assert issues, "未标注历史引用应被拦截"
    assert any("历史财年" in i for i in issues)


def test_validate_fiscal_references_labeled_historical_pass():
    """L3：带 FY 标注的历史引用 → 通过"""
    issues = validate_fiscal_references(6, "FY2023总资产841.63亿元，较当前1031.63亿元下降。", XPENG_WIND)
    # FY2023 显式标注 → 归因时不进 unattributed_historical
    assert not issues, f"带标注历史引用应通过: {issues}"


def test_validate_fiscal_references_no_wind_pass():
    """L3：无 wind_data → 跳过（不误报）"""
    assert validate_fiscal_references(6, "总资产841.63亿元。", {}) == []


def test_generate_chapter_wires_fiscal_check():
    """L3：_generate_chapter 接线 fiscal_issues（生成时拦截）"""
    import inspect

    from finance.workflow import _generate_chapter
    src = inspect.getsource(_generate_chapter)
    assert "validate_fiscal_references" in src, "生成时校验应接线"
    assert "fiscal_issues" in src


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
