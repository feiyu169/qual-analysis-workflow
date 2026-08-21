"""
test_quality_enhancer.py — 质量增强模块端到端测试
"""

import sys

sys.path.insert(0, '.')

from finance.base_valuation import compute_base_valuation
from finance.data_repair import repair_report, validate_pe_against_wind
from finance.depth_enhancer import run_depth_enhancement
from finance.quality_enhancer import enhance_report_quality
from finance.valuation_engine import compute_full_valuation


def test_data_repair():
    """测试数据修复"""
    chapters = {
        5: "### 第5章\n经营现金流281.08亿。好的，作为您的资深分析师，收入增长12.5%。",
        7: "### 第7章\nPE估算12-15倍。经营现金流267.16亿。快手2023年年报显示...",
    }

    wind_valuation = {"pe_ttm": 21.3}
    wind_financials = {
        "income": {"年净利润": [186.17], "年营业总收入": [1427.76]},
        "cashflow": {"过去三年每年经营活动产生的现金流量净额": [267.16]},
    }

    fixed, result = repair_report(chapters, wind_valuation, wind_financials, 2025)  # noqa: RUF059

    # 验证AI痕迹被清除
    assert "好的，作为您的" not in fixed[5], "AI痕迹未清除"
    print("✅ 数据修复: AI痕迹清除成功")

    # 验证来源标注修复
    assert "快手2025年年报" in fixed[7] or "2023" not in fixed[7], "来源标注未修复"
    print("✅ 数据修复: 来源标注修复成功")


def test_pe_validation():
    """测试PE校验"""
    # 正常PE
    report = validate_pe_against_wind("PE约为21倍", {"pe_ttm": 21.0})
    assert report.is_valid, "正常PE应通过"
    print("✅ PE校验: 正常值通过")

    # 异常PE
    report = validate_pe_against_wind("PE估算12-15倍", {"pe_ttm": 21.0})
    assert not report.is_valid, "异常PE应失败"
    print("✅ PE校验: 异常值检测成功")


def test_base_valuation():
    """测试基础估值"""
    financials = {
        "income": {"年净利润": [186.17], "年营业总收入": [1427.76]},
        "balance": {"最近3年每年所有者权益合计": [795.84]},
    }

    bv = compute_base_valuation("1024.HK", "快手", {"pe_ttm": 21.3, "pb": 3.2}, financials, 43.0)
    assert bv.pe_ttm == 21.3, f"PE应为21.3，实际{bv.pe_ttm}"
    assert bv.pb == 3.2, f"PB应为3.2，实际{bv.pb}"
    assert bv.is_valid, "估值应有效"
    print("✅ 基础估值: PE/PB正确")


def test_valuation_engine():
    """测试估值引擎"""
    financials = {
        "income": {"年营业总收入": [1134.7, 1268.98, 1427.76], "年净利润": [63.96, 153.35, 186.17]},
        "balance": {"最近3年每年负债合计": [572.22, 778.49, 849.20], "最近3年每年流动资产合计": [603.61, 628.69, 775.49]},
    }

    result = compute_full_valuation("1024.HK", "快手", financials, 43.0, 41.6)
    assert result.dcf is not None, "DCF应存在"
    assert result.dcf.value_per_share > 0, "DCF每股价值应>0"
    assert result.target_price_bull is not None, "牛市目标价应存在"
    assert result.target_price_bear is not None, "熊市目标价应存在"
    print(f"✅ 估值引擎: DCF={result.dcf.value_per_share:.1f}元, 目标价={result.target_price_bull:.1f}/{result.target_price_base:.1f}/{result.target_price_bear:.1f}")


def test_depth_enhancer():
    """测试深度优化"""
    chapters = {5: "### 第5章\n建议关注风险。如果DAU下降则减持。"}
    financials = {
        "income": {"年营业总收入": [1134.7, 1268.98, 1427.76], "年净利润": [63.96, 153.35, 186.17], "年营业利润": [50.43, 130.72, 184.86]},
    }

    result = run_depth_enhancement(chapters, financials, 57.7, 41.6, 43.0, base_wacc=0.081)
    assert len(result.scenarios) > 0, "应有情景分析"
    assert len(result.yoy_changes) > 0, "应有同比变化"
    assert result.overall_insight_score > 0, "洞察评分应>0"
    print(f"✅ 深度优化: 情景={len(result.scenarios)}个, 同比={len(result.yoy_changes)}个, 洞察={result.overall_insight_score:.0f}")


def test_integration():
    """集成测试"""
    chapters = {
        5: "### 第5章\nDAU达4.102亿，收入增长12.5%。经营现金流281.08亿。",
        7: "### 第7章\nPE估算12-15倍。经营现金流267.16亿。",
    }
    financials = {
        "income": {"年营业总收入": [1134.7, 1268.98, 1427.76], "年净利润": [63.96, 153.35, 186.17], "年营业利润": [50.43, 130.72, 184.86]},
        "balance": {"最近3年每年负债合计": [572.22, 778.49, 849.20], "最近3年每年流动资产合计": [603.61, 628.69, 775.49], "最近3年每年所有者权益合计": [490.74, 620.24, 795.84]},
        "cashflow": {"过去三年每年经营活动产生的现金流量净额": [207.81, 297.87, 267.16]},
    }
    wind_valuation = {"pe_ttm": 21.3, "pb": 3.2, "price": 41.6}

    enhanced, result = enhance_report_quality(
        chapters=chapters,
        financials=financials,
        wind_valuation=wind_valuation,
        company_name="快手",
        ticker="1024.HK",
        shares=43.0,
        current_price=41.6,
        enable_debate=False,
        enable_valuation=True,
        enable_depth=True,
    )

    assert result.valuation_result is not None, "应有估值结果"
    assert result.depth_result is not None, "应有深度结果"
    assert 7 in enhanced, "第7章应存在"
    assert "DCF" in enhanced[7] or "估值" in enhanced[7], "第7章应包含估值内容"


def test_valuation_currency_hkd():
    """B2a-2：港股估值注入统一港元（无人民币混用）"""
    chapters = {7: "### 第7章\n估值分析。", 5: "### 第5章\n盈利稳定。"}
    financials = {
        "income": {"年营业总收入": [100.0, 120.0, 150.0], "年净利润": [15.0, 18.0, 22.0], "年营业利润": [20.0, 25.0, 30.0]},
        "balance": {"年负债合计": [50.0, 55.0, 60.0], "年流动资产合计": [80.0, 90.0, 100.0]},
        "cashflow": {"经营活动现金流量净额": [10.0, 12.0, 15.0]},
    }

    enhanced, result = enhance_report_quality(
        chapters=dict(chapters),
        financials=financials,
        company_name="港股公司",
        ticker="1234.HK",
        shares=10.0,
        current_price=12.0,
        market="hk",  # B2a-2
        enable_debate=False,
        enable_valuation=True,
        enable_depth=False,
    )
    assert "港元" in enhanced[7], "港股估值应标注港元"
    assert "元\n" not in enhanced[7].replace("港元", ""), "不应有未标注的裸'元'"

    # A 股：仍用元
    enhanced_cn, _ = enhance_report_quality(
        chapters=dict(chapters),
        financials=financials,
        company_name="A股公司",
        ticker="600000.SH",
        shares=10.0,
        current_price=12.0,
        market="cn",
        enable_debate=False,
        enable_valuation=True,
        enable_depth=False,
    )
    assert "元\n" in enhanced_cn[7], "A 股估值用元"
    print(f"✅ 集成测试: 修复={result.total_fixes}处, 估值=DCF{result.valuation_result['dcf_value']:.1f}元")


if __name__ == "__main__":
    print("=" * 50)
    print("质量增强模块端到端测试")
    print("=" * 50)

    test_pe_validation()
    test_data_repair()
    test_base_valuation()
    test_valuation_engine()
    test_depth_enhancer()
    test_integration()

    print("\n" + "=" * 50)
    print("✅ 全部测试通过")
    print("=" * 50)
