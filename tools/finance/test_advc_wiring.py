"""ADVC 层2：接线测试（生成清洗层 + 修复循环分层）

覆盖：
- _generate_chapter 清洗层：mock LLM 产错位值 → ADVC 修正 → 1 次调用不重试
- _repair_chapters 分层：mock LLM 恒产错 → 值类问题不进 prompt、sweep 已修
"""
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pytest

from finance.qual_v8.data_anchor import _anchor_cache

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


def test_generate_chapter_cleans_misaligned_value():
    """层2：_generate_chapter 清洗层——LLM 产错位值被 ADVC 修正（不重试）"""
    # mock DataContext（wind 有锚点）
    from unittest.mock import Mock

    from finance.workflow import _generate_chapter

    ctx = Mock()
    ctx.market = "hk"
    ctx.wind = Mock()
    ctx.wind.__dict__ = {"quote": {"最新价": 46.52}}
    # _wind_to_dict(ctx.wind) 需要 income/balance/cashflow

    with patch("finance.workflow._wind_to_dict", return_value=XPENG_WIND), \
         patch("finance.quality.structural_check.structural_check") as mock_struct, \
         patch("finance.quality.numeric_guard.check_chapter_gates") as mock_gates, \
         patch("finance.workflow.clean_ai_artifacts",
               side_effect=lambda c: (c, [])):

        # LLM 返回错位值（总资产 31.63 应为 1031.63）——ADVC 应修正后通过
        caller_calls = {"n": 0}

        def fake_caller(name, prompt):
            caller_calls["n"] += 1
            return "公司总资产31.63亿元，规模扩大。"  # 错位值

        class _Pass:
            passed = True

            def __init__(self):
                self.issues = []

        mock_struct.return_value = _Pass()
        mock_gates.return_value = Mock(passed=True, violations=[])

        # 需要 CHAPTERS 注册表有 ch6
        import finance.workflow as m
        ch6_def = dict(m.CHAPTERS[6])
        with patch.dict(m.CHAPTERS, {6: ch6_def}, clear=False):
            content = _generate_chapter(6, "prompt", ctx, fake_caller,
                                        max_format_retries=2)

        assert caller_calls["n"] == 1, f"ADVC 修正后不应重试，实调 {caller_calls['n']} 次"
        assert "1031.63" in content or "1031.6263" in content, "错位值应被 ADVC 修正"


def test_repair_chapters_triage_value_issues():
    """层2：_repair_chapters——值类问题不进 LLM prompt（sweep 先修）"""
    from finance.quality.review_repair_loop import _repair_chapters

    chapters = {6: "公司总资产31.63亿元，规模扩大。"}
    issues = ["第6章 [跨章节一致性] 总资产(最新财年)在第3章=1031.63亿，第6章=31.63亿"]
    llm_calls = {"n": 0}

    def fake_caller(name, prompt):
        llm_calls["n"] += 1
        return '{"patches": []}'

    _repair_chapters(chapters, issues, fake_caller, XPENG_WIND)  # 就地修改 chapters
    # sweep 已修值类 → LLM 不该被调（仅剩值类问题）
    assert llm_calls["n"] == 0, f"值类问题不应进 LLM，实调 {llm_calls['n']}"
    assert "1031.63" in chapters[6] or "1031.6263" in chapters[6], "sweep 应已修正错位值"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
