"""
TerminalValueArbitrator测试

覆盖: 5个用例
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.terminal_value_arbitrator import TerminalValueArbitrator


class TestTerminalValueArbitrator(unittest.TestCase):
    """TerminalValueArbitrator测试"""
    
    def test_arbitrate_close(self):
        """仲裁: 差异<10%"""
        arbitrator = TerminalValueArbitrator()
        
        result = arbitrator.arbitrate(
            tv_perpetuity=100,
            tv_exit_multiple=105,
        )
        
        self.assertEqual(result.chosen_method, "dual_average")
        self.assertEqual(result.confidence, "high")
    
    def test_arbitrate_moderate(self):
        """仲裁: 10-25%差异"""
        arbitrator = TerminalValueArbitrator()
        
        result = arbitrator.arbitrate(
            tv_perpetuity=100,
            tv_exit_multiple=120,
        )
        
        self.assertEqual(result.chosen_method, "conservative")
        self.assertEqual(result.confidence, "medium")
        self.assertEqual(result.chosen_tv, 100)  # 取保守值
    
    def test_arbitrate_large(self):
        """仲裁: 25-50%差异"""
        arbitrator = TerminalValueArbitrator()
        
        result = arbitrator.arbitrate(
            tv_perpetuity=100,
            tv_exit_multiple=140,
        )
        
        self.assertEqual(result.chosen_method, "conservative_with_sensitivity")
        self.assertEqual(result.confidence, "low")
        self.assertTrue(any("敏感性分析" in w for w in result.warnings))
    
    def test_arbitrate_too_large(self):
        """仲裁: ≥50%差异阻断"""
        arbitrator = TerminalValueArbitrator()
        
        with self.assertRaises(ValueError):
            arbitrator.arbitrate(
                tv_perpetuity=100,
                tv_exit_multiple=200,
            )
    
    def test_validate_tv_ev_ratio(self):
        """验证TV/EV比例"""
        arbitrator = TerminalValueArbitrator()
        
        result = arbitrator.validate_tv_ev_ratio(
            tv=800,
            ev=1000,
        )
        
        self.assertEqual(result["ratio"], 0.8)
        self.assertFalse(result["passed"])  # 80% > 75%
        self.assertIsNotNone(result["warning"])
    
    def test_tv_ev_ratio_pass(self):
        """TV/EV比例: 通过"""
        arbitrator = TerminalValueArbitrator()
        
        result = arbitrator.validate_tv_ev_ratio(
            tv=600,
            ev=1000,
        )
        
        self.assertEqual(result["ratio"], 0.6)
        self.assertTrue(result["passed"])  # 60% < 75%
    
    def test_generate_arbitration_report(self):
        """生成仲裁报告"""
        arbitrator = TerminalValueArbitrator()
        
        result = arbitrator.arbitrate(
            tv_perpetuity=100,
            tv_exit_multiple=105,
        )
        
        report = arbitrator.generate_arbitration_report(result)
        
        self.assertIn("终值仲裁报告", report)
        self.assertIn("选定方法", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
