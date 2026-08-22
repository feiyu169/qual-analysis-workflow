"""B2a-3 亏损公司 DCF fail-fast 降级链测试

验收（路线图 B2a-3）：负 FCF/亏损公司不输出无意义目标价——
full_dcf → comparable(PE 仅盈利/PS 亏损) → 降级标注。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pytest

from finance.valuation_engine import compute_dcf, compute_full_valuation

# 亏损公司（小鹏样本：2025 营收 767.20 亿，净利润 -11.39 亿）
LOSS_FINANCIALS = {
    "income": {
        "年营业总收入": [306.76, 408.66, 767.20],
        "年营业利润": [-113.84, -74.82, -44.16],
        "年净利润": [-103.76, -57.90, -11.39],
    },
    "balance": {"年负债合计": [478.34, 514.31, 727.94], "年流动资产合计": [500.0, 550.0, 600.0]},
    "cashflow": {"经营活动现金流量净额": [9.56, -20.12, 82.59]},
}

# 盈利公司（正常路径）
PROFIT_FINANCIALS = {
    "income": {
        "年营业总收入": [100.0, 120.0, 150.0],
        "年营业利润": [20.0, 25.0, 30.0],
        "年净利润": [15.0, 18.0, 22.0],
    },
    "balance": {"年负债合计": [50.0, 55.0, 60.0], "年流动资产合计": [80.0, 90.0, 100.0]},
    "cashflow": {"经营活动现金流量净额": [10.0, 12.0, 15.0]},
}


def test_loss_company_dcf_failfast():
    """亏损公司：DCF fail-fast，不输出无意义正目标价"""
    r = compute_dcf(LOSS_FINANCIALS, shares=18.87)
    assert r.value_per_share == 0.0, f"亏损公司 DCF 应 fail-fast（value=0），实为 {r.value_per_share}"
    assert r.warnings, "应有 fail-fast 说明 warning"
    assert any("亏损" in w for w in r.warnings), "warning 应注明亏损"


def test_profit_company_dcf_normal():
    """盈利公司：DCF 正常输出"""
    r = compute_dcf(PROFIT_FINANCIALS, shares=10.0)
    assert r.value_per_share > 0, "盈利公司 DCF 应有正值"
    assert r.fcf_projections, "应有 FCF 预测"


def test_loss_company_full_valuation_ps_degrade():
    """亏损公司完整估值：DCF fail → PS 降级（不用 PE 负 EPS）"""
    r = compute_full_valuation("9868.HK", "小鹏集团-W", LOSS_FINANCIALS, shares=18.87, current_price=46.52)
    assert r.degraded is True, "亏损公司应标记降级"
    assert "PS" in r.degradation_reason, f"应降级到 PS 法，实为: {r.degradation_reason}"
    # PS 降级值 = 可比 median_ps × 每股营收（正值）
    assert r.value_per_share is not None and r.value_per_share > 0, "PS 降级应有正值估值"
    # 不得使用 PE 负 EPS 产出负目标价
    assert not (r.target_price_base and r.target_price_base < 0), "不得输出负目标价"
    assert any("亏损" in w for w in r.warnings), "warning 应注明亏损降级"


def test_profit_company_full_valuation_dcf_primary():
    """盈利公司：DCF 为主，无降级标记"""
    r = compute_full_valuation("1024.HK", "盈利公司", PROFIT_FINANCIALS, shares=10.0, current_price=12.0)
    assert r.dcf is not None and r.dcf.value_per_share > 0, "盈利公司 DCF 应正常"
    assert not r.degraded, "盈利公司不应标记降级"


# ============ 双专家 P0：可比公司 ============

def test_comparables_no_disney_and_static_snapshot_flag():
    """双专家 P0（2026-08-22）：
    - 迪士尼（行业错配）已从补充可比池移除
    - 静态池使用标记 comparables_static_snapshot=True（报告应标注静态快照）"""
    from finance.valuation_engine import SUPPLEMENTARY_COMPARABLES, build_comparable_analysis

    # 迪士尼移除
    assert "迪士尼" not in SUPPLEMENTARY_COMPARABLES, "迪士尼（流媒体巨头）不得混入在线阅读可比"
    names = list(SUPPLEMENTARY_COMPARABLES.keys())
    assert all("迪士尼" != n for n in names)

    # 静态快照标记
    companies, medians = build_comparable_analysis()
    assert medians.get("static_snapshot") is True, "默认池应标记 static_snapshot=True"
    # 调用方传实时可比 → static_snapshot=False
    _, medians2 = build_comparable_analysis(
        core_comps={"腾讯": {"ticker": "0700.HK", "pe": 20.0}},
        supplementary_comps={},
    )
    assert medians2.get("static_snapshot") is False, "实时可比应标记 static_snapshot=False"


def test_full_valuation_surfaces_static_snapshot():
    """compute_full_valuation 应携带 comparables_static_snapshot 标记"""
    r = compute_full_valuation("1024.HK", "盈利公司", PROFIT_FINANCIALS, shares=10.0, current_price=12.0)
    assert getattr(r, "comparables_static_snapshot", True) is True, "默认池应标记静态快照"
    assert "静态快照" in str(r.warnings) or getattr(r, "comparables_static_snapshot", None) is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
