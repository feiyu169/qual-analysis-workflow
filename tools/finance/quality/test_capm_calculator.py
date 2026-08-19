"""
CAPMCalculator测试

覆盖: 8个用例
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.capm_calculator import (
    CAPMCalculator, CAPMConfig, CAPMResult
)


class TestCAPMCalculator(unittest.TestCase):
    """CAPMCalculator测试"""
    
    def test_basic_ke_calculation(self):
        """基础Ke计算"""
        calc = CAPMCalculator()
        result = calc.calculate_ke(
            regression_beta=1.2,
            regression_r_squared=0.5
        )
        
        self.assertGreater(result.ke, 0)
        self.assertIn("Ke =", result.formula)
    
    def test_beta_blume_adjustment(self):
        """Blume调整"""
        config = CAPMConfig(blume_adjustment=True)
        calc = CAPMCalculator(config=config)
        
        beta_result = calc.calculate_beta(regression_beta=1.5)
        expected = 0.67 * 1.5 + 0.33 * 1.0
        self.assertAlmostEqual(beta_result.final_beta, expected, places=2)
    
    def test_beta_no_blume(self):
        """无Blume调整"""
        config = CAPMConfig(blume_adjustment=False)
        calc = CAPMCalculator(config=config)
        
        beta_result = calc.calculate_beta(regression_beta=1.5)
        self.assertEqual(beta_result.final_beta, 1.5)
    
    def test_alpha_size_premium(self):
        """规模溢价"""
        calc = CAPMCalculator()
        alpha_result = calc.calculate_alpha(size_premium=0.02)
        
        self.assertEqual(alpha_result.size_premium, 0.02)
    
    def test_alpha_size_premium_cap(self):
        """规模溢价上限"""
        calc = CAPMCalculator()
        alpha_result = calc.calculate_alpha(size_premium=0.05)  # 超过3%上限
        
        self.assertEqual(alpha_result.size_premium, 0.03)  # 被截断到3%
    
    def test_alpha_total_cap(self):
        """Alpha总上限"""
        config = CAPMConfig(
            total_alpha_cap=0.06,
            size_premium_enabled=True,
            size_premium_cap=0.05,  # 放宽单项上限
            liquidity_premium_enabled=True,
            liquidity_premium_value=0.03,
            governance_premium_enabled=True,
            governance_premium_value=0.02
        )
        calc = CAPMCalculator(config=config)
        
        alpha_result = calc.calculate_alpha(
            size_premium=0.04,
            liquidity_premium=0.03,
            governance_premium=0.02
        )
        
        # 总和=0.04+0.03+0.02=0.09，超过上限0.06
        self.assertEqual(alpha_result.total, 0.06)
        self.assertTrue(alpha_result.capped)
    
    def test_ke_in_range(self):
        """Ke在合理区间"""
        calc = CAPMCalculator()
        result = calc.calculate_ke(
            regression_beta=1.0,
            regression_r_squared=0.5
        )
        
        self.assertTrue(calc.validate_ke(result.ke))
    
    def test_formula_output(self):
        """公式输出"""
        calc = CAPMCalculator()
        result = calc.calculate_ke(
            regression_beta=1.0,
            regression_r_squared=0.5
        )
        
        self.assertIn("Ke =", result.formula)
    
    def test_r_squared_threshold(self):
        """R²阈值"""
        config = CAPMConfig(beta_method="blended", regression_weight=0.6)
        calc = CAPMCalculator(config=config)
        
        beta_result = calc.calculate_beta(
            regression_beta=1.5,
            regression_r_squared=0.2,
            bottom_up_beta=1.0
        )
        
        self.assertEqual(beta_result.method, "bottom_up")
    
    def test_beta_source_annotation(self):
        """Beta来源标注"""
        calc = CAPMCalculator()
        beta_result = calc.calculate_beta(
            regression_beta=1.2,
            regression_r_squared=0.5,
            bottom_up_beta=1.0
        )
        
        self.assertIn(beta_result.method, ["regression", "bottom_up", "blended", "default"])
    
    def test_custom_risk_free_rate(self):
        """自定义无风险利率"""
        calc = CAPMCalculator()
        result = calc.calculate_ke(
            risk_free_rate=0.03,
            market_risk_premium=0.06
        )
        
        self.assertEqual(result.rf, 0.03)
        self.assertEqual(result.mrp, 0.06)


if __name__ == "__main__":
    unittest.main(verbosity=2)
