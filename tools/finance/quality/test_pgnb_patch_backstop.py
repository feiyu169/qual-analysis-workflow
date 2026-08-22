"""PGNB v4 审查修复层兜底测试（2026-08-22 死循环根治）

背景：审查修复循环中，LLM patch 写错数字（如 营业利润=-55.2 vs 锚点 -44.16）
→ 校验失败 → 整轮回滚 → 原文幻觉残留 → 下轮重复 → 死循环。
修复：patch 应用后、校验前，bind_bare_numbers 把 patch 引入的幻觉数字程序替换
为锚点值（零 LLM 重写），校验通过循环终止。

验证：
1. bind_bare_numbers 对 patch 场景的幻觉数字（-55.2/5.0/59.6）替换为占位符
2. 替换后 bind_placeholders 回填锚点值 → validate_chapter_any_fy 零错误
3. _repair_chapters 的 patch 路径：patch 引入幻觉 → 程序替换 → 不触发回滚死循环
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))

import pytest

from finance.qual_v8.data_anchor import _anchor_cache, get_data_anchor
from finance.qual_v8.numeric_binder import bind_bare_numbers, bind_placeholders

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
        "归母净资产": [363.2853, 312.7479, 303.6859],
    },
    "cashflow": {"经营活动现金流量净额": [9.5616, -20.1234, 82.5853]},
    "_year_labels": {"财年": [2023, 2024, 2025]},
}


def setup_function():
    _anchor_cache.clear()


def _anchor():
    return get_data_anchor(XPENG_WIND)


def test_patch_hallucinated_op_profit_replaced():
    """patch 引入 营业利润=-55.2（锚点 -44.16）→ 程序替换为占位符→回填锚点值"""
    # 模拟 LLM patch 后的内容（replacement 写了错误数字）
    content = "公司FY2025营业利润=-55.2亿元，亏损收窄。"
    bound, fixes = bind_bare_numbers(content, _anchor(), 5)
    assert fixes, f"patch 幻觉数字必须被替换: {fixes}"
    assert "营业利润=[{{营业利润}}]" in bound, f"应替换为占位符: {bound}"
    bound2, unresolved = bind_placeholders(bound, _anchor(), 5)
    assert not unresolved
    assert "FY2025 -44.16" in bound2, f"应回填锚点值: {bound2}"
    assert not _anchor().validate_chapter_any_fy(5, bound2), "替换后必须通过校验器"


def test_patch_hallucinated_net_profit_replaced():
    """patch 引入 归母净利润=5.0（锚点 -11.39）→ 程序替换（第7章实测场景）"""
    content = "归母净利润5.0亿元，扭亏为盈。"
    bound, fixes = bind_bare_numbers(content, _anchor(), 7)
    assert fixes, f"归母净利润幻觉必须被替换: {fixes}"
    bound2, _ = bind_placeholders(bound, _anchor(), 7)
    assert "FY2025 -11.39" in bound2, f"应回填锚点值: {bound2}"
    assert not _anchor().validate_chapter_any_fy(7, bound2)


def test_patch_hallucinated_equity_replaced():
    """patch 引入 归母净资产=59.6（锚点 303.69）→ 程序替换（第6章实测场景）"""
    content = "归母净资产=59.6亿元，同比下滑。"
    bound, fixes = bind_bare_numbers(content, _anchor(), 6)
    assert fixes, f"归母净资产幻觉必须被替换: {fixes}"
    bound2, _ = bind_placeholders(bound, _anchor(), 6)
    assert "FY2025 303.69" in bound2, f"应回填锚点值: {bound2}"
    assert not _anchor().validate_chapter_any_fy(6, bound2)


def test_patch_valid_number_kept():
    """patch 引入正确数字（营收 767.20=锚点）→ 保留（不误改）"""
    content = "公司营业收入767.20亿元，创历史新高。"
    bound, fixes = bind_bare_numbers(content, _anchor(), 5)
    assert not fixes, f"合法数字不应替换: {fixes}"
    assert "767.20" in bound


def test_repair_loop_patch_path_no_rollback_loop():
    """端到端：_repair_chapters 的 patch 路径——LLM 输出错误数字 patch →
    bind_bare_numbers 程序替换 → 校验通过 → 无回滚死循环。

    直接验证关键链路（不经完整循环，避免 LLM 调用）：
    用 apply_patches + PGNB 兜底逻辑等价流程模拟。
    """
    from finance.quality.patch_applier import apply_patches, parse_patch_json

    original = "公司FY2025营业利润=-55.2亿元，亏损收窄。"
    # LLM 输出了错误数字的 patch（target 唯一）
    llm_out = '{"patches": [{"target": "营业利润=-55.2亿元", "replacement": "营业利润=-55.2亿元，同比改善"}]}'
    patches = parse_patch_json(llm_out)
    assert patches, "patch 应可解析"

    result = apply_patches(original, patches, validators=[])
    assert result.ok and result.applied, "patch 应应用成功"

    # PGNB 兜底（_repair_chapters 新增逻辑）：替换 patch 引入的幻觉数字
    bound, fixes = bind_bare_numbers(result.content, _anchor(), 5)
    if fixes:
        bound, _ = bind_placeholders(bound, _anchor(), 5)
    # 最终内容必须通过数字锚点校验（回滚循环的终止条件）
    errs = _anchor().validate_chapter_any_fy(5, bound)
    assert not errs, f"兜底后必须零数字错误: {errs}"
    assert "FY2025 -44.16" in bound, f"应含锚点值: {bound}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
