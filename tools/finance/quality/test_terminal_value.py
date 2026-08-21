"""
TerminalValueCalculator测试

覆盖: 6个用例
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.terminal_value import TerminalValueCalculator, TerminalValueConfig


class TestTerminalValueCalculator(unittest.TestCase):
    """TerminalValueCalculator测试"""

    def test_perpetuity_growth_basic(self):
        """永续增长法基础"""
        calc = TerminalValueCalculator()
        result = calc.calculate_perpetuity_growth(
            final_year_fcf=100,
            wacc=0.10,
            g=0.025
        )

        self.assertGreater(result.tv, 0)
        self.assertEqual(result.g, 0.025)
        self.assertEqual(result.wacc, 0.10)
        self.assertIn("TV =", result.formula)

    def test_perpetuity_growth_g_exceeds_wacc(self):
        """g>=WACC时报错"""
        calc = TerminalValueCalculator()

        with self.assertRaises(ValueError):
            calc.calculate_perpetuity_growth(
                final_year_fcf=100,
                wacc=0.02,
                g=0.03
            )

    def test_exit_multiple_peer_median(self):
        """退出倍数法: 可比公司中位数"""
        config = TerminalValueConfig(multiple_source="peer_median")
        calc = TerminalValueCalculator(config=config)

        result = calc.calculate_exit_multiple(
            terminal_metric=500,
            peer_multiples=[8, 10, 12, 14, 16]
        )

        self.assertEqual(result.multiple, 12)  # 中位数
        self.assertEqual(result.tv, 6000)  # 500 * 12

    def test_exit_multiple_custom(self):
        """退出倍数法: 自定义倍数"""
        calc = TerminalValueCalculator()

        result = calc.calculate_exit_multiple(
            terminal_metric=500,
            custom_multiple=15.0
        )

        self.assertEqual(result.multiple, 15.0)
        self.assertEqual(result.tv, 7500)  # 500 * 15

    def test_tv_pct_validation_pass(self):
        """TV占比验证: 通过"""
        calc = TerminalValueCalculator()
        result = calc.validate_tv_pct(tv=600, pv_fcf=400)

        self.assertEqual(result.tv_pct, 0.6)  # 60%
        self.assertTrue(result.passed)  # < 75%

    def test_tv_pct_validation_fail(self):
        """TV占比验证: 失败"""
        calc = TerminalValueCalculator()
        result = calc.validate_tv_pct(tv=800, pv_fcf=200)

        self.assertEqual(result.tv_pct, 0.8)  # 80%
        self.assertFalse(result.passed)  # > 75%
        self.assertIsNotNone(result.warning)

    def test_dual_method(self):
        """双轨方法"""
        config = TerminalValueConfig(primary_method="dual_method")
        calc = TerminalValueCalculator(config=config)

        result = calc.calculate_tv(
            final_year_fcf=100,
            wacc=0.10,
            terminal_metric=500,
            peer_multiples=[10, 12, 14]
        )

        self.assertEqual(result.method, "dual_method")
        self.assertIsNotNone(result.tv_perpetuity)
        self.assertIsNotNone(result.tv_exit_multiple)
        self.assertEqual(result.weight_perpetuity, 0.5)

    def test_perpetuity_growth_method(self):
        """永续增长法主入口"""
        config = TerminalValueConfig(primary_method="perpetuity_growth")
        calc = TerminalValueCalculator(config=config)

        result = calc.calculate_tv(
            final_year_fcf=100,
            wacc=0.10,
            terminal_metric=500  # 不使用
        )

        self.assertEqual(result.method, "perpetuity_growth")
        self.assertGreater(result.tv, 0)

    def test_exit_multiple_method(self):
        """退出倍数法主入口"""
        config = TerminalValueConfig(primary_method="exit_multiple")
        calc = TerminalValueCalculator(config=config)

        result = calc.calculate_tv(
            final_year_fcf=100,  # 不使用
            wacc=0.10,  # 不使用
            terminal_metric=500,
            peer_multiples=[10, 12, 14]
        )

        self.assertEqual(result.method, "exit_multiple")
        self.assertGreater(result.tv, 0)

    def test_arbitrate_close(self):
        """仲裁: 差异<10%"""
        calc = TerminalValueCalculator()
        result = calc.arbitrate(tv_perpetuity=100, tv_exit_multiple=105)

        self.assertEqual(result["method"], "dual_average")
        self.assertEqual(result["confidence"], "high")

    def test_arbitrate_moderate(self):
        """仲裁: 10-25%差异"""
        calc = TerminalValueCalculator()
        result = calc.arbitrate(tv_perpetuity=100, tv_exit_multiple=120)

        self.assertEqual(result["method"], "conservative")
        self.assertEqual(result["confidence"], "medium")
        self.assertEqual(result["chosen_tv"], 100)  # 取保守值

    def test_arbitrate_large(self):
        """仲裁: 25-50%差异"""
        calc = TerminalValueCalculator()
        result = calc.arbitrate(tv_perpetuity=100, tv_exit_multiple=140)

        self.assertEqual(result["method"], "conservative_with_sensitivity")
        self.assertEqual(result["confidence"], "low")

    def test_arbitrate_too_large(self):
        """仲裁: ≥50%差异阻断"""
        calc = TerminalValueCalculator()

        with self.assertRaises(ValueError):
            calc.arbitrate(tv_perpetuity=100, tv_exit_multiple=200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
