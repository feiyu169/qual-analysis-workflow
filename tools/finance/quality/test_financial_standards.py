"""
FinancialStandards测试

覆盖: 5个用例
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.financial_standards import FinancialStandards


class TestFinancialStandards(unittest.TestCase):
    """FinancialStandards测试"""

    def test_normalize_profit(self):
        """标准化利润口径"""
        standards = FinancialStandards()

        result = standards.normalize_profit(
            net_profit_parent=100,
            minority_interest=20,
        )

        self.assertEqual(result["归母净利润"], 100)
        self.assertEqual(result["净利润"], 120)

    def test_validate_profit_consistency_pass(self):
        """利润一致性验证: 通过"""
        standards = FinancialStandards()

        # 归母净利润=100，总净利润=120，差异16.7%，设置tolerance=0.20
        issues = standards.validate_profit_consistency(
            net_profit_parent=100,
            net_profit_total=120,
            tolerance=0.20,
        )

        self.assertEqual(len(issues), 0)

    def test_validate_profit_consistency_fail(self):
        """利润一致性验证: 失败"""
        standards = FinancialStandards()

        issues = standards.validate_profit_consistency(
            net_profit_parent=100,
            net_profit_total=50,  # 归母大于总净利润
        )

        self.assertTrue(len(issues) > 0)

    def test_normalize_fcf(self):
        """标准化FCF口径"""
        standards = FinancialStandards()

        result = standards.normalize_fcf(
            operating_cashflow=150,
            capex=50,
            net_income=100,
            depreciation=30,
            working_capital_change=10,
            net_borrowing=20,
            tax_rate=0.25,
            ebit=120,
        )

        self.assertIn("LFCF", result)
        self.assertEqual(result["LFCF"], 100)  # 150 - 50
        self.assertIn("FCFF", result)
        self.assertIn("FCFE", result)

    def test_validate_fcf_consistency(self):
        """FCF一致性验证"""
        standards = FinancialStandards()

        issues = standards.validate_fcf_consistency(
            fcf=100,
            operating_cashflow=150,
            net_income=120,
        )

        # FCF/OCF = 0.67 > 0.5, FCF/NI = 0.83 in [0.3, 3.0]
        self.assertEqual(len(issues), 0)

    def test_calculate_roic(self):
        """计算ROIC"""
        standards = FinancialStandards()

        roic = standards.calculate_roic(
            nopat=50,
            invested_capital=200,
        )

        self.assertAlmostEqual(roic, 0.25, places=2)

    def test_calculate_invested_capital(self):
        """计算投入资本"""
        standards = FinancialStandards()

        ic = standards.calculate_invested_capital(
            total_equity=100,
            total_debt=150,
            cash=30,
            non_operating_assets=20,
        )

        self.assertEqual(ic, 200)  # 100 + 150 - 30 - 20

    def test_generate_standards_report(self):
        """生成口径报告"""
        standards = FinancialStandards()

        report = standards.generate_standards_report()
        self.assertIn("利润口径", report)
        self.assertIn("FCF口径", report)
        self.assertIn("归母净利润", report)
        self.assertIn("FCFF", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
