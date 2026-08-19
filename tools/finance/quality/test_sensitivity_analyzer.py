"""
SensitivityAnalyzer测试

覆盖: 5个用例
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.sensitivity_analyzer import SensitivityAnalyzer, SensitivityConfig


class TestSensitivityAnalyzer(unittest.TestCase):
    """SensitivityAnalyzer测试"""
    
    def test_wacc_sensitivity(self):
        """WACC敏感性分析"""
        analyzer = SensitivityAnalyzer()
        results = analyzer.analyze_wacc_sensitivity(
            base_wacc=0.10,
            base_g=0.025,
            base_fcf=100,
            net_debt=50,
            shares=10.0,
        )
        
        self.assertIn(0, results)  # 基准点
        self.assertIsNotNone(results[0])
        self.assertGreater(results[0], 0)
    
    def test_growth_sensitivity(self):
        """增长率敏感性分析"""
        analyzer = SensitivityAnalyzer()
        results = analyzer.analyze_growth_sensitivity(
            base_wacc=0.10,
            base_g=0.025,
            base_fcf=100,
            net_debt=50,
            shares=10.0,
        )
        
        self.assertIn(0, results)  # 基准点
        self.assertIsNotNone(results[0])
    
    def test_fcf_sensitivity(self):
        """FCF敏感性分析"""
        analyzer = SensitivityAnalyzer()
        results = analyzer.analyze_fcf_sensitivity(
            base_wacc=0.10,
            base_g=0.025,
            base_fcf=100,
            net_debt=50,
            shares=10.0,
        )
        
        self.assertIn(0, results)  # 基准点
        self.assertIsNotNone(results[0])
    
    def test_full_analysis(self):
        """完整敏感性分析"""
        analyzer = SensitivityAnalyzer()
        result = analyzer.analyze(
            base_wacc=0.10,
            base_g=0.025,
            base_fcf=100,
            net_debt=50,
            shares=10.0,
        )
        
        self.assertGreater(result.base_value, 0)
        self.assertTrue(len(result.wacc_sensitivity) > 0)
        self.assertTrue(len(result.growth_sensitivity) > 0)
        self.assertTrue(len(result.fcf_sensitivity) > 0)
        self.assertTrue(len(result.tornado_data) > 0)
    
    def test_tornado_ranking(self):
        """龙卷风图排名"""
        analyzer = SensitivityAnalyzer()
        result = analyzer.analyze(
            base_wacc=0.10,
            base_g=0.025,
            base_fcf=100,
            net_debt=50,
            shares=10.0,
        )
        
        # 龙卷风图应按影响范围排序
        if len(result.tornado_data) > 1:
            for i in range(len(result.tornado_data) - 1):
                self.assertGreaterEqual(
                    result.tornado_data[i]["range"],
                    result.tornado_data[i + 1]["range"]
                )
    
    def test_breakeven(self):
        """Breakeven分析"""
        analyzer = SensitivityAnalyzer()
        result = analyzer.analyze(
            base_wacc=0.10,
            base_g=0.025,
            base_fcf=100,
            net_debt=50,
            shares=10.0,
        )
        
        # 应有breakeven数据
        self.assertTrue(len(result.breakeven) > 0)
    
    def test_generate_matrix(self):
        """生成敏感性矩阵"""
        analyzer = SensitivityAnalyzer()
        result = analyzer.analyze(
            base_wacc=0.10,
            base_g=0.025,
            base_fcf=100,
            net_debt=50,
            shares=10.0,
        )
        
        matrix = analyzer.generate_sensitivity_matrix(result)
        self.assertIn("WACC敏感性", matrix)
        self.assertIn("永续增长率敏感性", matrix)
        self.assertIn("FCF敏感性", matrix)


if __name__ == "__main__":
    unittest.main(verbosity=2)
