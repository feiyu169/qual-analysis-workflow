"""
FCFCalculator测试

覆盖: 6个用例
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.fcf_calculator import FCFCalculator, FCFConfig


class TestFCFCalculator(unittest.TestCase):
    """FCFCalculator测试"""
    
    def test_fcff_formula(self):
        """FCFF公式"""
        calc = FCFCalculator()
        result = calc.calculate_fcff(
            ebit=100,
            tax_rate=0.25,
            depreciation=50,
            capex=80,
            working_capital_change=10,
        )
        
        # FCFF = 100*(1-0.25) + 50 - 80 - 10 = 75 + 50 - 80 - 10 = 35
        self.assertEqual(result.method, "FCFF")
        self.assertAlmostEqual(result.fcf, 35.0, places=1)
        self.assertIn("FCFF =", result.formula)
    
    def test_fcfe_formula(self):
        """FCFE公式"""
        calc = FCFCalculator()
        result = calc.calculate_fcfe(
            net_income=80,
            depreciation=50,
            capex=80,
            working_capital_change=10,
            net_borrowing=20,
        )
        
        # FCFE = 80 + 50 - 80 - 10 + 20 = 60
        self.assertEqual(result.method, "FCFE")
        self.assertAlmostEqual(result.fcf, 60.0, places=1)
        self.assertIn("FCFE =", result.formula)
    
    def test_lfcf_formula(self):
        """LFCF公式"""
        calc = FCFCalculator()
        result = calc.calculate_lfcf(
            operating_cashflow=150,
            capex=80,
        )
        
        # LFCF = 150 - 80 = 70
        self.assertEqual(result.method, "LFCF")
        self.assertAlmostEqual(result.fcf, 70.0, places=1)
        self.assertIn("LFCF =", result.formula)
    
    def test_calculate_main_entry(self):
        """主计算入口"""
        calc = FCFCalculator()
        
        result = calc.calculate(
            method="FCFF",
            ebit=100,
            tax_rate=0.25,
            depreciation=50,
            capex=80,
            working_capital_change=10,
        )
        
        self.assertEqual(result["method"], "FCFF")
        self.assertAlmostEqual(result["fcf"], 35.0, places=1)
    
    def test_consistency_check_pass(self):
        """一致性检查: 通过"""
        calc = FCFCalculator()
        result = calc.check_consistency(
            fcf=100,
            net_income=120,
            operating_cashflow=150,
            negative_fcf_years=0,
        )
        
        self.assertTrue(result.passed)
        self.assertTrue(len(result.warnings) == 0)
    
    def test_consistency_check_fail_ratio(self):
        """一致性检查: FCF/NI比值异常"""
        calc = FCFCalculator()
        result = calc.check_consistency(
            fcf=10,
            net_income=100,  # FCF/NI = 0.1 < 0.3
            operating_cashflow=150,
            negative_fcf_years=0,
        )
        
        self.assertFalse(result.passed)
        self.assertTrue(any("FCF/NI" in w for w in result.warnings))
    
    def test_consistency_check_fail_ocf(self):
        """一致性检查: FCF/OCF比值异常"""
        calc = FCFCalculator()
        result = calc.check_consistency(
            fcf=10,
            net_income=50,
            operating_cashflow=100,  # FCF/OCF = 0.1 < 0.5
            negative_fcf_years=0,
        )
        
        self.assertFalse(result.passed)
        self.assertTrue(any("FCF/OCF" in w for w in result.warnings))
    
    def test_consistency_check_fail_negative_years(self):
        """一致性检查: 连续负FCF年数过多"""
        calc = FCFCalculator()
        result = calc.check_consistency(
            fcf=-10,
            net_income=50,
            operating_cashflow=100,
            negative_fcf_years=3,  # > 2
        )
        
        self.assertFalse(result.passed)
        self.assertTrue(any("负FCF" in w for w in result.warnings))
    
    def test_annotate_fcf(self):
        """FCF标注"""
        calc = FCFCalculator()
        annotation = calc.annotate_fcf(100.5, "FCFF")
        
        self.assertIn("FCFF", annotation)
        self.assertIn("100.5", annotation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
