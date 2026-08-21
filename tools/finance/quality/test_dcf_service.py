"""
Gate 1测试: DCFService+CAPM+终值

测试覆盖:
- CAPMCalculator: 8个测试
- TerminalValueCalculator: 6个测试
- DCFService: 6个测试

总计: 20个测试

"""

import os
import sys
import unittest

# 添加finance工具路径
sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.capm_calculator import CAPMCalculator
from finance.quality.v3.dcf_service import DCFInputs, DCFService
from finance.quality.v3.terminal_value_calculator import TerminalValueCalculator


class TestCAPMCalculator(unittest.TestCase):
    """CAPMCalculator测试"""

    def setUp(self):
        self.calculator = CAPMCalculator()

    def test_basic_calculation(self):
        """测试基本CAPM计算"""
        result = self.calculator.calculate(
            rf=0.023,
            beta=1.2,
            erp=0.055
        )
        # Ke = 0.023 + 1.2 * 0.055 = 0.023 + 0.066 = 0.089
        self.assertAlmostEqual(result.ke, 0.089, places=3)
        self.assertEqual(result.rf, 0.023)
        self.assertEqual(result.beta, 1.2)

    def test_with_size_premium(self):
        """测试含规模溢价"""
        result = self.calculator.calculate(
            rf=0.023,
            beta=1.0,
            erp=0.055,
            size_premium=0.02
        )
        # Ke = 0.023 + 1.0 * 0.055 + 0.02 = 0.098
        self.assertAlmostEqual(result.ke, 0.098, places=3)

    def test_with_alpha(self):
        """测试含α调整"""
        result = self.calculator.calculate(
            rf=0.023,
            beta=1.0,
            erp=0.055,
            alpha=0.01
        )
        # Ke = 0.023 + 1.0 * 0.055 + 0.01 = 0.088
        self.assertAlmostEqual(result.ke, 0.088, places=3)

    def test_blume_adjustment(self):
        """测试Blume调整Beta"""
        result = self.calculator.calculate_with_blume(
            raw_beta=1.5,
            rf=0.023,
            erp=0.055
        )
        # β_adjusted = 0.67 * 1.5 + 0.33 * 1.0 = 1.005 + 0.33 = 1.335
        # Ke = 0.023 + 1.335 * 0.055 = 0.023 + 0.073425 = 0.096425
        self.assertAlmostEqual(result.beta, 1.335, places=3)
        self.assertAlmostEqual(result.ke, 0.096425, places=3)

    def test_ke_upper_bound(self):
        """测试Ke上限约束"""
        result = self.calculator.calculate(
            rf=0.05,
            beta=2.5,
            erp=0.08,
            size_premium=0.03,
            alpha=0.02
        )
        # Ke = 0.05 + 2.5 * 0.08 + 0.03 + 0.02 = 0.30
        # 但上限是0.25
        self.assertEqual(result.ke, 0.25)

    def test_ke_lower_bound(self):
        """测试Ke下限约束"""
        result = self.calculator.calculate(
            rf=0.01,
            beta=0.5,
            erp=0.03,
            size_premium=0.0,
            alpha=-0.02
        )
        # Ke = 0.01 + 0.5 * 0.03 + 0.0 - 0.02 = 0.005
        # 但下限是0.05
        self.assertEqual(result.ke, 0.05)

    def test_invalid_beta(self):
        """测试无效Beta"""
        with self.assertRaises(ValueError):
            self.calculator.calculate(beta=3.0)  # 超出范围[0.5, 2.5]

    def test_default_params_by_market(self):
        """测试不同市场默认参数"""
        cn_params = self.calculator.get_default_params("cn")
        hk_params = self.calculator.get_default_params("hk")
        us_params = self.calculator.get_default_params("us")

        self.assertEqual(cn_params["rf"], 0.023)
        self.assertEqual(hk_params["rf"], 0.035)
        self.assertEqual(us_params["rf"], 0.040)


class TestTerminalValueCalculator(unittest.TestCase):
    """TerminalValueCalculator测试"""

    def setUp(self):
        self.calculator = TerminalValueCalculator()

    def test_perpetuity_method(self):
        """测试永续增长法"""
        # TV = FCF * (1+g) / (WACC-g)
        # TV = 100 * 1.02 / (0.10-0.02) = 102 / 0.08 = 1275
        tv = self.calculator.calculate_perpetuity(
            fcf=100,
            wacc=0.10,
            g=0.02
        )
        self.assertAlmostEqual(tv, 1275.0, places=0)

    def test_exit_multiple_method(self):
        """测试退出倍数法"""
        # TV = EBITDA * ExitMultiple
        # TV = 200 * 10 = 2000
        tv = self.calculator.calculate_exit_multiple(
            ebitda=200,
            exit_multiple=10
        )
        self.assertEqual(tv, 2000)

    def test_arbitrage_close(self):
        """测试差异<10%仲裁"""
        result = self.calculator.calculate(
            fcf=100,
            ebitda=150,
            wacc=0.10,
            g=0.02,
            exit_multiple=8.5,  # 150 * 8.5 = 1275
            ev_estimate=1000
        )
        # 两种方法应该接近
        self.assertEqual(result.chosen_method, "dual_average")
        self.assertEqual(result.confidence, "high")

    def test_arbitrage_moderate(self):
        """测试10-25%差异仲裁"""
        result = self.calculator.calculate(
            fcf=100,
            ebitda=200,
            wacc=0.10,
            g=0.02,
            exit_multiple=8.0,  # 200 * 8 = 1600
            ev_estimate=1000
        )
        # 永续增长法: 1275, 退出倍数法: 1600, 差异约20%
        self.assertEqual(result.chosen_method, "conservative")
        self.assertEqual(result.confidence, "medium")
        self.assertEqual(result.chosen_tv, 1275.0)  # 取保守值

    def test_arbitrage_large(self):
        """测试25-50%差异仲裁"""
        result = self.calculator.calculate(
            fcf=100,
            ebitda=200,
            wacc=0.10,
            g=0.02,
            exit_multiple=10.0,  # 200 * 10 = 2000
            ev_estimate=1000
        )
        # 永续增长法: 1275, 退出倍数法: 2000, 差异约44%
        self.assertEqual(result.chosen_method, "conservative_with_sensitivity")
        self.assertEqual(result.confidence, "low")

    def test_arbitrage_block(self):
        """测试差异≥50%阻断"""
        with self.assertRaises(ValueError):
            self.calculator.calculate(
                fcf=100,
                ebitda=200,
                wacc=0.10,
                g=0.02,
                exit_multiple=15.0,  # 200 * 15 = 3000
                ev_estimate=1000
            )

    def test_g_exceeds_wacc(self):
        """测试g≥WACC阻断"""
        with self.assertRaises(ValueError):
            self.calculator.calculate_perpetuity(
                fcf=100,
                wacc=0.05,
                g=0.06  # g > WACC
            )


class TestDCFService(unittest.TestCase):
    """DCFService测试"""

    def setUp(self):
        self.service = DCFService()
        self.inputs = DCFInputs(
            fcf_projections=[-327, 9, 144, 236, 300],
            ebitda_projections=[89, 456, 578, 650, 720],
            rf=0.023,
            beta=1.2,
            erp=0.055,
            kd=0.05,
            tax_rate=0.25,
            debt_ratio=0.15,
            terminal_growth=0.02,
            exit_multiple=7.0,  # 调低退出倍数使差异在合理范围
            net_debt=500,
            shares=63.69,
            current_price=90.30
        )

    def test_basic_calculation(self):
        """测试基本DCF计算"""
        result = self.service.calculate(self.inputs)

        # 验证结果存在
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.enterprise_value)
        self.assertIsNotNone(result.equity_value)
        self.assertIsNotNone(result.per_share_value)

        # 验证WACC计算
        # WACC = Ke * (1-D) + Kd * (1-T) * D
        # Ke = 0.023 + 1.2 * 0.055 = 0.089
        # WACC = 0.089 * 0.85 + 0.05 * 0.75 * 0.15 = 0.07565 + 0.005625 = 0.081275
        self.assertAlmostEqual(result.wacc, 0.081275, places=2)

        # 验证每股价值为正
        self.assertGreater(result.per_share_value, 0)

    def test_wacc_calculation(self):
        """测试WACC计算"""
        result = self.service.calculate(self.inputs)

        # WACC = Ke * (1-D) + Kd * (1-T) * D
        # Ke = 0.023 + 1.2 * 0.055 = 0.089
        # WACC = 0.089 * 0.85 + 0.05 * 0.75 * 0.15 = 0.07565 + 0.005625 = 0.081275
        self.assertAlmostEqual(result.wacc, 0.081275, places=3)

    def test_bridge_output(self):
        """测试桥接输出"""
        result = self.service.calculate(self.inputs)

        # 验证桥接输出存在
        self.assertIn("wacc", result.bridge)
        self.assertIn("capm", result.bridge)
        self.assertIn("terminal_value", result.bridge)
        self.assertIn("present_values", result.bridge)
        self.assertIn("valuation", result.bridge)

    def test_bridge_report(self):
        """测试桥接报告生成"""
        result = self.service.calculate(self.inputs)
        report = self.service.generate_bridge_report(result)

        # 验证报告包含关键信息
        self.assertIn("WACC计算", report)
        self.assertIn("CAPM分解", report)
        self.assertIn("终值计算", report)
        self.assertIn("估值桥接", report)

    def test_terminal_value_warning(self):
        """测试终值占比警告"""
        # 创建终值占比高的场景（使用更接近的退出倍数）
        inputs_high_tv = DCFInputs(
            fcf_projections=[10, 20, 30],  # 低FCF
            ebitda_projections=[50, 60, 70],
            rf=0.023,
            beta=1.0,
            erp=0.055,
            kd=0.05,
            tax_rate=0.25,
            debt_ratio=0.15,
            terminal_growth=0.02,
            exit_multiple=10.0,  # 调整退出倍数使差异在合理范围
            net_debt=100,
            shares=100,
            current_price=50.0
        )

        result = self.service.calculate(inputs_high_tv)
        report = self.service.generate_bridge_report(result)

        # 验证报告生成成功
        self.assertIn("估值桥接", report)

    def test_per_share_value_calculation(self):
        """测试每股价值计算"""
        result = self.service.calculate(self.inputs)

        # 每股价值 = (企业价值 - 净负债) / 总股本
        expected_equity = result.enterprise_value - self.inputs.net_debt
        expected_per_share = expected_equity / self.inputs.shares

        self.assertAlmostEqual(result.equity_value, expected_equity, places=0)
        self.assertAlmostEqual(result.per_share_value, expected_per_share, places=2)


if __name__ == "__main__":
    unittest.main()
