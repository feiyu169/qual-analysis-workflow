"""
ROICWACCChecker测试

覆盖: 6个用例
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.roic_wacc_checker import ROICWACCChecker


class TestROICWACCChecker(unittest.TestCase):
    """ROICWACCChecker测试"""

    def test_q1_roic_above_wacc_improving(self):
        """Q1: ROIC > WACC, 改善中"""
        checker = ROICWACCChecker()
        result = checker.check(
            roic_current=0.15,
            roic_trend="improving",
            wacc=0.10,
            claim="价值创造确立",
        )

        self.assertEqual(result.quadrant, "Q1")
        self.assertTrue(result.is_creating_value)
        self.assertTrue("合理" in result.message)

    def test_q2_roic_above_wacc_stable(self):
        """Q2: ROIC > WACC, 稳定"""
        checker = ROICWACCChecker()
        result = checker.check(
            roic_current=0.15,
            roic_trend="stable",
            wacc=0.10,
            claim="价值创造稳定",
        )

        self.assertEqual(result.quadrant, "Q2")
        self.assertTrue(result.is_creating_value)
        self.assertTrue("合理" in result.message)

    def test_q3_roic_below_wacc_improving(self):
        """Q3: ROIC < WACC, 改善中"""
        checker = ROICWACCChecker()
        result = checker.check(
            roic_current=0.08,
            roic_trend="improving",
            wacc=0.10,
            claim="拐点临近",
        )

        self.assertEqual(result.quadrant, "Q3")
        self.assertFalse(result.is_creating_value)
        self.assertTrue("合理" in result.message)

    def test_q4_roic_below_wacc_deteriorating(self):
        """Q4: ROIC < WACC, 恶化"""
        checker = ROICWACCChecker()
        result = checker.check(
            roic_current=0.08,
            roic_trend="deteriorating",
            wacc=0.10,
            claim="价值毁损持续",
        )

        self.assertEqual(result.quadrant, "Q4")
        self.assertFalse(result.is_creating_value)
        self.assertTrue("合理" in result.message)

    def test_blocked_claim(self):
        """阻止的声称"""
        checker = ROICWACCChecker()
        result = checker.check(
            roic_current=0.08,  # ROIC < WACC
            roic_trend="deteriorating",  # 恶化
            wacc=0.10,
            claim="价值创造确立",  # Q4不允许
        )

        self.assertFalse("合理" in result.message)
        self.assertTrue("矛盾" in result.message)

    def test_spread_calculation(self):
        """Spread计算"""
        checker = ROICWACCChecker()
        result = checker.check(
            roic_current=0.15,
            roic_trend="improving",
            wacc=0.10,
        )

        self.assertAlmostEqual(result.spread, 0.05, places=2)

    def test_incremental_roic(self):
        """增量ROIC"""
        checker = ROICWACCChecker()
        result = checker.calculate_incremental_roic(
            delta_nopat=20,
            delta_ic=100,
        )

        self.assertAlmostEqual(result.incremental_roic, 0.20, places=2)
        self.assertTrue(result.is_value_creating)

    def test_get_correct_claim(self):
        """获取正确的声称"""
        checker = ROICWACCChecker()
        result = checker.check(
            roic_current=0.15,
            roic_trend="improving",
            wacc=0.10,
        )

        correct_claim = checker.get_correct_claim(result)
        self.assertIn("价值创造", correct_claim)

    def test_generate_report(self):
        """生成报告"""
        checker = ROICWACCChecker()
        result = checker.check(
            roic_current=0.15,
            roic_trend="improving",
            wacc=0.10,
        )

        report = checker.generate_report(result)
        self.assertIn("ROIC", report)
        self.assertIn("WACC", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
