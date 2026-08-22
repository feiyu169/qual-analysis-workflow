"""B2b-1 + B5-1：财务 100% Wind + Wind 缺失字段处置表测试

验收（路线图 B2b-1/B5-1）：
- 财务字段不从 LLM 提取（100% Wind）
- 无源字段（有息负债/现金）显式"未披露"，禁止启发式回填
- 派生字段带公式标注
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pytest

from finance.wind_field_disposition import (
    FINANCIAL_FIELD_DISPOSITION,
    resolve_financial_from_wind,
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


def test_disposition_table_covers_all_financial_fields():
    """B5-1：处置表覆盖 FinancialFacts 全部 12 个财务字段"""
    from finance.fact_extractor import FinancialFacts
    fields = {f for f in FinancialFacts.__dataclass_fields__ if not f.startswith("_")}
    covered = set(FINANCIAL_FIELD_DISPOSITION.keys())
    assert fields == covered, f"处置表缺字段: {fields - covered}"


def test_source_fields_from_wind_latest():
    """有源字段取 Wind 最新财年值"""
    vals, _ = resolve_financial_from_wind(XPENG_WIND)
    assert vals["revenue"] == pytest.approx(767.1974)
    assert vals["net_profit"] == pytest.approx(-11.3946)
    assert vals["total_assets"] == pytest.approx(1031.6263)
    assert vals["operating_cashflow"] == pytest.approx(82.5853)


def test_unavailable_fields_not_backfilled():
    """无源字段（现金/有息负债）→ None + 未披露标注（禁止启发式回填）"""
    vals, annotations = resolve_financial_from_wind(XPENG_WIND)
    assert vals["interest_bearing_debt"] is None
    assert vals["cash_and_equivalents"] is None
    joined = " ".join(annotations)
    assert "未披露" in joined
    assert "有息负债" in joined


def test_derived_fields_with_formula_annotation():
    """派生字段带公式标注（operating_margin/net_margin）"""
    vals, annotations = resolve_financial_from_wind(XPENG_WIND)
    # 营业利润/营收 = -44.1552/767.1974
    assert vals["operating_margin"] == pytest.approx(-44.1552 / 767.1974)
    joined = " ".join(annotations)
    assert "派生" in joined
    assert "营业利润 / 营业收入" in joined


def test_gross_margin_not_masqueraded_as_operating_margin():
    """双专家 P0（2026-08-22）：毛利率不得用营业利润率顶替——
    Wind canonical 无毛利率列 → unavailable（None + 未披露标注），防误导"""
    vals, annotations = resolve_financial_from_wind(XPENG_WIND)
    assert vals["gross_margin"] is None, "毛利率必须 None（不派生为营业利润率）"
    joined = " ".join(annotations)
    assert "未披露" in joined, "毛利率应标注未披露"
    assert "营业利润率顶替" in joined or "顶替" in joined, "应明示禁用营业利润率顶替"
    # operating_margin 独立存在（派生自营业利润/营收）
    assert vals["operating_margin"] is not None


def test_net_debt_no_heuristic_backfill():
    """双专家 P0（2026-08-22）：extract_dcf_params 净负债弃用
    总负债近似 + ×0.3 启发式——Wind 无源 → None + 显式标注（禁止启发式回填）"""
    from finance.workflow import extract_dcf_params

    params = extract_dcf_params(XPENG_WIND)
    assert params["net_debt"] is None, "净负债不可得必须为 None（不启发式回填）"
    joined = " ".join(params.get("warnings", []))
    assert "净负债不可得" in joined, "应显式标注净负债不可得"
    assert "启发式" in joined, "应明示禁止启发式回填"


def test_beta_explicit_degradation_not_silent():
    """双专家 P0（2026-08-22）：β 无源时显式降级标注（不静默 1.2），
    调用方可传真实 β"""
    from finance.workflow import extract_dcf_params

    # 无 β → 默认 1.2 + 显式警告（非静默）
    p1 = extract_dcf_params(XPENG_WIND)
    joined1 = " ".join(p1.get("warnings", []))
    assert "β 无源" in joined1, "无源 β 必须显式标注"
    assert "敏感性" in joined1 or "默认假设" in joined1, "应提示敏感性/默认假设"

    # 调用方传 β=2.0 → 使用并标注来源
    p2 = extract_dcf_params(XPENG_WIND, beta=2.0)
    joined2 = " ".join(p2.get("warnings", []))
    assert "调用方提供" in joined2, "应标注 β 来源"


def test_resolve_financial_fiscal_year_aware():
    """双专家 P1（2026-08-22）：resolve_financial_from_wind 按目标财年取值——
    财务填充感知 fiscal_year（防财年标签与数值脱钩）"""
    # FY2023 营收 = 306.7607（非最新 767.1974）
    vals, ann = resolve_financial_from_wind(XPENG_WIND, fiscal_year=2023)
    assert vals["revenue"] == pytest.approx(306.7607), "FY2023 营收应为 306.76"
    assert vals["net_profit"] == pytest.approx(-103.7578), "FY2023 净利应为 -103.76"

    # 不传财年 → 最新财年
    vals_latest, _ = resolve_financial_from_wind(XPENG_WIND)
    assert vals_latest["revenue"] == pytest.approx(767.1974), "默认取最新财年"

    # 目标财年无标签 → 回退最新
    vals_fallback, _ = resolve_financial_from_wind(XPENG_WIND, fiscal_year=2020)
    assert vals_fallback["revenue"] == pytest.approx(767.1974), "未知财年回退最新"


def test_missing_wind_returns_none_with_annotation():
    """Wind 缺 income/balance → 全部字段 None + 标注"""
    vals, annotations = resolve_financial_from_wind({})
    assert all(v is None for v in vals.values())
    assert annotations, "应有缺失标注"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
