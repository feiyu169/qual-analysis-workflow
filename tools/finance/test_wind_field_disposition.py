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
    """派生字段带公式标注（gross_margin/operating_margin/net_margin）"""
    vals, annotations = resolve_financial_from_wind(XPENG_WIND)
    # 营业利润/营收 = -44.1552/767.1974
    assert vals["operating_margin"] == pytest.approx(-44.1552 / 767.1974)
    joined = " ".join(annotations)
    assert "派生" in joined
    assert "营业利润 / 营业收入" in joined


def test_missing_wind_returns_none_with_annotation():
    """Wind 缺 income/balance → 全部字段 None + 标注"""
    vals, annotations = resolve_financial_from_wind({})
    assert all(v is None for v in vals.values())
    assert annotations, "应有缺失标注"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
