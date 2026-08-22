"""PGNB 数字回填器测试（docs/qual-pgnb-architecture.md + heavyskill K8 审查升级 v2）

验证：LLM 占位符 → 程序按锚点回填（零幻觉）；无锚点 → [数据待核]；FY 标注正确；
v2：派生指标程序计算（净利率/ROE/同比）+ 裸数字硬拦截。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pytest

from finance.qual_v8.data_anchor import _anchor_cache, get_data_anchor
from finance.qual_v8.numeric_binder import (
    bind_bare_numbers,
    bind_fuzzy_dates,
    bind_placeholders,
    validate_bare_numbers,
)

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


# ====================================================================
# heavyskill K8 升级 v2：派生指标程序计算 + 裸数字硬拦截
# ====================================================================

def test_bind_derived_net_margin():
    """v2 派生指标：净利率 = 归母净利润/营业收入（程序计算，LLM 不自算）"""
    content = "公司[{{净利率}}]，盈利改善。"
    bound, unresolved = bind_placeholders(content, _anchor(), 3)
    assert not unresolved, f"净利率应有锚点可算: {unresolved}"
    # FY2025: -11.3946/767.1974 = -1.49%
    assert "-1.49%" in bound, f"应回填净利率: {bound}"


def test_bind_derived_roe():
    """v2 派生指标：ROE = 归母净利润/年所有者权益合计"""
    content = "ROE[{{ROE}}]。"
    bound, _ = bind_placeholders(content, _anchor(), 3)
    # FY2025: -11.3946/303.6859 = -3.75%
    assert "-3.75%" in bound, f"应回填 ROE: {bound}"


def test_bind_derived_yoy():
    """v2 派生指标：营收同比 = (FY2025-FY2024)/FY2024"""
    content = "营收同比[{{营收同比}}]。"
    bound, unresolved = bind_placeholders(content, _anchor(), 5)
    assert not unresolved, f"营收同比应有数据可算: {unresolved}"
    # (767.1974-408.6631)/408.6631 = 87.73%
    assert "87.73%" in bound, f"应回填营收同比: {bound}"


def test_bind_derived_unavailable_margin():
    """v2：毛利率无锚点（毛利不可得）→ [数据待核]（不编造）"""
    content = "毛利率[{{毛利率}}]。"
    bound, unresolved = bind_placeholders(content, _anchor(), 3)
    assert "[数据待核:毛利率]" in bound, "毛利率不可派生应数据待核"
    assert unresolved


def test_validate_bare_numbers_catches_hallucination():
    """v2 裸数字硬拦截：LLM 直接写幻觉数字 14.0 → 检出（不依赖 prompt 配合）"""
    content = "公司营业收入14.0亿元。"
    problems = validate_bare_numbers(content, _anchor(), 3)
    assert problems, "裸数字幻觉必须被检出"
    assert "14.0" in problems[0]


def test_validate_bare_numbers_allows_anchored():
    """v2 裸数字：命中锚点（767.20=实际值）→ 不报（合法）"""
    content = "公司营业收入767.20亿元。"
    problems = validate_bare_numbers(content, _anchor(), 3)
    assert not problems, f"命中锚点不应报: {problems}"


def test_validate_bare_numbers_derived_caught():
    """v2 裸数字：净利率幻觉（5.0% vs 实际 -1.49%）→ 检出（百分比类）"""
    content = "公司净利率5.0%，盈利改善。"
    problems = validate_bare_numbers(content, _anchor(), 3)
    # 净利率是派生指标，validate_bare_numbers 的 regex 含净利率 → 检出
    assert problems, "净利率幻觉应被检出"


# ====================================================================
# v3（用户原则：Wind 没有的由财报提供）：运营锚点 + 语义检测 + 原文核对
# ====================================================================

def test_bind_ops_placeholder():
    """v3：运营数据占位符（财报提取锚点——用户原则 Wind 没有的由财报提供）"""
    from finance.qual_v8.numeric_binder import bind_placeholders as _b
    ops = {"deliveries": {"value": 389000, "source": "业务概览", "unit": "辆"},
           "gross_margin": {"value": 0.14, "source": "管理层讨论", "unit": ""}}
    content = "全年交付[{{deliveries}}]，毛利率[{{gross_margin}}]。"
    bound, unresolved = _b(content, _anchor(), 1, ops_data=ops)
    assert not unresolved, f"运营占位符应回填: {unresolved}"
    assert "389000" in bound, f"应回填交付量: {bound}"
    assert "0.14" in bound, f"应回填毛利率: {bound}"


def test_bind_ops_missing_placeholder():
    """v3：运营占位符但无数据 → [数据待核]（不编造）"""
    from finance.qual_v8.numeric_binder import bind_placeholders as _b
    content = "月活[{{mau}}]。"
    bound, unresolved = _b(content, _anchor(), 1, ops_data={"dau": {"value": 1200}})
    assert "[数据待核:mau]" in bound
    assert unresolved


def test_validate_placeholder_semantics_mismatch():
    """v3：占位符语义错配——'毛利率[{{营业收入}}]' 应写 [{{毛利率}}]"""
    from finance.qual_v8.numeric_binder import validate_placeholder_semantics
    content = "公司毛利率[{{营业收入}}]，盈利改善。"
    problems = validate_placeholder_semantics(content)
    assert problems, "毛利率上下文+营业收入占位符应检出错配"
    assert "毛利率" in problems[0]


def test_validate_placeholder_semantics_ok():
    """v3：语义匹配（营收上下文+营业收入占位符）→ 不错配"""
    from finance.qual_v8.numeric_binder import validate_placeholder_semantics
    content = "公司营收[{{营业收入}}]亿元，增长。"
    problems = validate_placeholder_semantics(content)
    assert not problems


def test_validate_bare_numbers_year_exemption():
    """v3：年份豁免——LLM 把财年写 '营业收入2024.0亿元'（2024 是年份非营收值）
    → 豁免（避免误报重试；年份是财年引用，非财务值幻觉）"""
    from finance.qual_v8.numeric_binder import validate_bare_numbers
    content = "FY2024 营业收入2024.0亿元的说法是错误的，实际营收[{{营业收入}}]亿元。"
    problems = validate_bare_numbers(content, _anchor(), 3)
    # 2024.0 是年份 → 豁免；无其他裸数字（767.20 未写）
    assert not problems, f"年份数字应豁免: {problems}"


# ====================================================================
# v4（2026-08-22 实测驱动）：裸数字程序绑定——拦截即替换，零 LLM 重写依赖
# ====================================================================

def test_bind_bare_numbers_replaces_hallucination():
    """v4：LLM 直接写幻觉数字（营业利润=12.5 vs 锚点 -44.16）→ 程序替换为占位符
    （随后 bind_placeholders 回填锚点值——不再触发 LLM 重写/空壳章）"""
    content = "公司营业利润=12.5亿元，亏损收窄。"
    bound, fixes = bind_bare_numbers(content, _anchor(), 5)
    assert fixes, f"幻觉数字必须被替换: {fixes}"
    assert "营业利润=[{{营业利润}}]" in bound, f"应替换为占位符: {bound}"

    # 回填后 → 锚点值 -44.16，且通过校验器（零幻觉闭环）
    bound2, unresolved = bind_placeholders(bound, _anchor(), 5)
    assert not unresolved, f"替换后占位符应可回填: {unresolved}"
    assert "FY2025 -44.16" in bound2, f"应回填锚点值: {bound2}"
    assert not _anchor().validate_chapter_any_fy(5, bound2), "回填后必须通过校验器"


def test_bind_bare_numbers_keeps_anchored():
    """v4：命中锚点的裸数字（总资产1031.63=FY2025）→ 保留（不误改）"""
    content = "公司总资产1031.63亿元。"
    bound, fixes = bind_bare_numbers(content, _anchor(), 6)
    assert not fixes, f"命中锚点不应替换: {fixes}"
    assert bound == content


def test_bind_bare_numbers_keeps_historical():
    """v4：命中历史财年锚点（总资产827.06=FY2024）→ 保留（多财年兼容）"""
    content = "FY2024 总资产827.06亿元，较上年下降。"
    bound, fixes = bind_bare_numbers(content, _anchor(), 6)
    assert not fixes, f"历史财年合法引用不应替换: {fixes}"
    assert bound == content


def test_bind_bare_numbers_keeps_no_anchor():
    """v4：无锚点指标（毛利率等）→ 保留原文（不猜测，validate 收口）"""
    content = "公司毛利率约12.5%。"
    bound, fixes = bind_bare_numbers(content, _anchor(), 5)
    assert not fixes, f"无锚点指标不应替换: {fixes}"
    assert "12.5" in bound


def test_bind_bare_numbers_year_exemption():
    """v4：年份豁免——'营业收入2024.0亿元' 的 2024.0 是年份 → 不替换"""
    content = "FY2024 营业收入2024.0亿元（年份误写，实际[{{营业收入:2024}}]）。"
    bound, fixes = bind_bare_numbers(content, _anchor(), 5)
    assert not fixes, f"年份数字不应替换: {fixes}"
    assert "2024.0" in bound


def test_bind_bare_numbers_derived_pct():
    """v4：派生百分比幻觉（净利率5.0% vs 程序计算 -1.49%）→ 替换为占位符"""
    content = "公司净利率5.0%，盈利改善。"
    bound, fixes = bind_bare_numbers(content, _anchor(), 5)
    assert fixes, f"净利率幻觉应替换: {fixes}"
    assert "净利率[{{净利率}}]" in bound, f"应替换为占位符: {bound}"
    bound2, _ = bind_placeholders(bound, _anchor(), 5)
    assert "-1.49%" in bound2, f"回填后应为程序计算值: {bound2}"


def test_bind_bare_numbers_end_to_end_no_empty_chapter():
    """v4 端到端：复现 2026-08-22 第5章死循环——4 处幻觉数字一次替换，
    不进入 LLM 重写（对比：旧流程重试 3 次后空壳章 0 数字）"""
    content = (
        "公司营业利润=12.5亿元，总资产0.79亿元，资产负债率合理，"
        "营收767.20亿元（命中锚点）。"
    )
    bound, fixes = bind_bare_numbers(content, _anchor(), 5)
    assert len(fixes) == 2, f"应替换 2 处幻觉（营业利润/总资产）: {fixes}"
    assert "营业利润=[{{营业利润}}]" in bound
    assert "总资产[{{总资产}}]" in bound
    assert "767.20" in bound  # 命中锚点的营收保留

    # 回填后全部来自锚点 → 校验器零问题（无空壳章、无重试）
    bound2, unresolved = bind_placeholders(bound, _anchor(), 5)
    assert not unresolved
    assert not _anchor().validate_chapter_any_fy(5, bound2), "回填后必须零错误"


def test_bind_bare_numbers_equity_hallucination():
    """v4：归母净资产幻觉（59.6 vs 锚点 303.69）→ 替换（regex 补全：2026-08-22
    第6章该指标因 regex 缺项未被拦截的回归用例）"""
    content = "归母净资产=59.6亿元，同比下降。"
    bound, fixes = bind_bare_numbers(content, _anchor(), 6)
    assert fixes, f"归母净资产幻觉必须被替换: {fixes}"
    assert "归母净资产=[{{归母净资产}}]" in bound, f"应替换为占位符: {bound}"
    bound2, _ = bind_placeholders(bound, _anchor(), 6)
    assert "FY2025 303.69" in bound2, f"应回填锚点值: {bound2}"
    assert not _anchor().validate_chapter_any_fy(6, bound2), "回填后必须通过校验器"


def test_bind_bare_numbers_capex_no_anchor():
    """v4：购建固定资产（Wind 无该列→无锚点）→ 保留原文（不猜测）"""
    content = "购建固定资产、无形资产和其他长期资产支付的现金约85亿元。"
    bound, fixes = bind_bare_numbers(content, _anchor(), 6)
    assert not fixes, f"无锚点指标不应替换: {fixes}"
    assert "85" in bound


# ====================================================================
# 阶段 2：日期语义治理——bind_fuzzy_dates 上下文感知
# ====================================================================

def test_bind_fuzzy_dates_financial_context():
    """阶段 2：财务语境"当前营收" → "FY2025 营收"（上下文含财务关键词）"""
    content = "当前营收增长强劲，归因于新车型放量。"
    bound, fixes = bind_fuzzy_dates(content, XPENG_WIND, 5)
    assert fixes, f"财务语境应触发替换: {fixes}"
    assert "FY2025" in bound, f"应替换为 FY2025: {bound}"
    assert "当前" not in bound


def test_bind_fuzzy_dates_non_financial_exempt():
    """阶段 2：非财务语境"当前宏观环境" → 保留（豁免）"""
    content = "当前宏观环境面临不确定性，行业竞争加剧。"
    bound, fixes = bind_fuzzy_dates(content, XPENG_WIND, 5)
    assert not fixes, f"非财务语境不应替换: {fixes}"
    assert "当前" in bound


def test_bind_fuzzy_dates_no_wind_data():
    """阶段 2：无 Wind 数据 → 保留原文"""
    content = "当前业绩表现亮眼。"
    bound, fixes = bind_fuzzy_dates(content, {}, 5)
    assert not fixes
    assert bound == content


def test_bind_fuzzy_dates_mixed_context():
    """阶段 2：混合语境——财务部分替换，非财务保留"""
    content = "当前营收767亿元创历史新高，但当前行业竞争日趋激烈。"
    bound, fixes = bind_fuzzy_dates(content, XPENG_WIND, 5)
    assert len(fixes) == 1, f"应只替换财务语境的'当前': {fixes}"
    assert "FY2025" in bound
    assert "当前行业" in bound  # 非财务语境保留


def test_bind_fuzzy_dates_recently():
    """阶段 2："近年来"在财务语境 → 替换"""
    content = "近年来净利润持续改善，亏损收窄趋势明确。"
    bound, fixes = bind_fuzzy_dates(content, XPENG_WIND, 5)
    assert fixes, f"财务语境'近年来'应替换: {fixes}"
    assert "FY2025" in bound


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
