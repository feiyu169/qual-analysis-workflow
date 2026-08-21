"""
ConclusionSynthesizer测试

覆盖: 6个用例
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.conclusion_synthesizer import ConclusionSynthesizer


class TestConclusionSynthesizer(unittest.TestCase):
    """ConclusionSynthesizer测试"""

    def test_synthesize_buy(self):
        """综合: 买入评级"""
        synthesizer = ConclusionSynthesizer()

        result = synthesizer.synthesize(
            dcf_value=60,
            pe_value=55,
            comparable_value=50,
            current_price=40,
        )

        self.assertEqual(result.rating, "买入")
        self.assertGreater(result.target_price, 40)

    def test_synthesize_hold(self):
        """综合: 持有评级"""
        synthesizer = ConclusionSynthesizer()

        result = synthesizer.synthesize(
            dcf_value=45,
            pe_value=42,
            comparable_value=40,
            current_price=40,
        )

        self.assertEqual(result.rating, "持有")

    def test_synthesize_sell(self):
        """综合: 卖出评级"""
        synthesizer = ConclusionSynthesizer()

        result = synthesizer.synthesize(
            dcf_value=30,
            pe_value=25,
            comparable_value=28,
            current_price=40,
        )

        self.assertEqual(result.rating, "卖出")

    def test_weighted_target_price(self):
        """加权目标价"""
        synthesizer = ConclusionSynthesizer()

        result = synthesizer.synthesize(
            dcf_value=60,
            dcf_weight=0.5,
            pe_value=50,
            pe_weight=0.3,
            comparable_value=40,
            comparable_weight=0.2,
        )

        # 加权: 60*0.5 + 50*0.3 + 40*0.2 = 30 + 15 + 8 = 53
        self.assertAlmostEqual(result.target_price, 53.0, places=1)

    def test_check_evidence(self):
        """检查证据"""
        synthesizer = ConclusionSynthesizer()

        has_evidence = synthesizer.check_evidence(
            claim="估值50元",
            evidence_list=["DCF估值", "PE估值"],
        )

        self.assertTrue(has_evidence)

    def test_falsification_conditions(self):
        """可证伪条件"""
        synthesizer = ConclusionSynthesizer()

        result = synthesizer.synthesize(
            dcf_value=60,
            pe_value=55,
            current_price=40,
        )

        self.assertTrue(len(result.falsification_conditions) > 0)

    def test_generate_report(self):
        """生成报告"""
        synthesizer = ConclusionSynthesizer()

        result = synthesizer.synthesize(
            dcf_value=60,
            pe_value=55,
            current_price=40,
        )

        report = synthesizer.generate_report(result)

        self.assertIn("投资结论", report)
        self.assertIn("评级", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
