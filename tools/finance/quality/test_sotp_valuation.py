"""
SOTP 分部估值测试
"""
import pytest
from quality.sotp_valuation import compute_sotp_valuation, BusinessSegment, SOTPResult


class TestSOTPValuation:
    """SOTP 估值测试"""

    def test_single_segment_ev_revenue(self):
        """单分部 EV/Revenue 估值"""
        segments = [
            BusinessSegment(
                name="直播",
                revenue=100.0,
                comparable_multiple=3.0,
                multiple_type="EV/Revenue",
            )
        ]
        result = compute_sotp_valuation(segments=segments, shares=10.0)

        assert result.total_segment_value == 300.0
        assert result.equity_value == 300.0
        assert result.value_per_share == 30.0

    def test_multi_segment(self):
        """多分部估值"""
        segments = [
            BusinessSegment(name="直播", revenue=100.0, comparable_multiple=3.0),
            BusinessSegment(name="电商", revenue=50.0, comparable_multiple=5.0),
            BusinessSegment(name="广告", revenue=30.0, comparable_multiple=8.0),
        ]
        result = compute_sotp_valuation(segments=segments, shares=10.0)

        assert result.segment_values["直播"] == 300.0
        assert result.segment_values["电商"] == 250.0
        assert result.segment_values["广告"] == 240.0
        assert result.total_segment_value == 790.0

    def test_ebitda_multiple(self):
        """EV/EBITDA 估值"""
        segments = [
            BusinessSegment(
                name="业务A",
                revenue=100.0,
                ebitda=20.0,
                comparable_multiple=10.0,
                multiple_type="EV/EBITDA",
            )
        ]
        result = compute_sotp_valuation(segments=segments, shares=10.0)

        assert result.total_segment_value == 200.0

    def test_corporate_expense_deduction(self):
        """集团费用扣除"""
        segments = [
            BusinessSegment(name="业务A", revenue=100.0, comparable_multiple=3.0),
        ]
        result = compute_sotp_valuation(
            segments=segments,
            corporate_expense=10.0,
            shares=10.0,
        )

        # 集团费用现值 = 10 / (0.10 - 0.03) = 142.86
        assert result.corporate_expense_pv > 0
        assert result.equity_value < result.total_segment_value

    def test_net_debt_deduction(self):
        """净负债扣除"""
        segments = [
            BusinessSegment(name="业务A", revenue=100.0, comparable_multiple=3.0),
        ]
        result = compute_sotp_valuation(
            segments=segments,
            net_debt=50.0,
            shares=10.0,
        )

        assert result.equity_value == 250.0  # 300 - 50

    def test_fx_conversion(self):
        """港元转换"""
        segments = [
            BusinessSegment(name="业务A", revenue=100.0, comparable_multiple=3.0),
        ]
        result = compute_sotp_valuation(
            segments=segments,
            shares=10.0,
            fx_rate=1.087,
        )

        assert result.value_per_share == 30.0
        assert result.value_per_share_hkd == pytest.approx(32.61, abs=0.01)

    def test_upside_calculation(self):
        """上行空间计算"""
        segments = [
            BusinessSegment(name="业务A", revenue=100.0, comparable_multiple=3.0),
        ]
        result = compute_sotp_valuation(
            segments=segments,
            shares=10.0,
            current_price=25.0,
            fx_rate=1.0,
        )

        assert result.upside == pytest.approx(0.20, abs=0.01)  # 20%

    def test_negative_ebitda_warning(self):
        """EBITDA 为负时警告"""
        segments = [
            BusinessSegment(
                name="业务A",
                revenue=100.0,
                ebitda=-10.0,
                comparable_multiple=10.0,
                multiple_type="EV/EBITDA",
            )
        ]
        result = compute_sotp_valuation(segments=segments, shares=10.0)

        assert len(result.warnings) > 0
        assert "EBITDA 为负" in result.warnings[0]
