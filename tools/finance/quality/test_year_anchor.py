"""
YearAnchor测试

覆盖: 6个用例
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.year_anchor import YearAnchor, YearErrorDetector, YearPromptBuilder, YearTextFixer


class TestYearAnchor(unittest.TestCase):
    """YearAnchor测试"""

    def test_prompt_builder_output(self):
        """Prompt注入输出"""
        builder = YearPromptBuilder(fiscal_year=2025)
        output = builder.build()

        self.assertIn("FY2025", output)
        self.assertIn("禁止使用", output)
        self.assertIn("2024财年", output)

    def test_error_detector_finds_mismatch(self):
        """检测年份错标"""
        detector = YearErrorDetector(fiscal_year=2025)
        content = "2024财年，顺丰控股实现营收3,082亿元"
        errors = detector.detect(content)

        self.assertTrue(len(errors) > 0)
        self.assertIn("年份错标", errors[0])

    def test_error_detector_no_false_positive(self):
        """无误报"""
        detector = YearErrorDetector(fiscal_year=2025)
        content = "2025财年，顺丰控股实现营收3,082亿元"
        errors = detector.detect(content)

        self.assertEqual(len(errors), 0)

    def test_text_fixer_corrects(self):
        """修正年份表述"""
        fixer = YearTextFixer(target_year=2025)
        content = "2024财年，顺丰控股实现营收3,082亿元"
        fixed = fixer.fix(content)

        self.assertIn("2025财年", fixed)
        self.assertNotIn("2024财年", fixed)

    def test_text_fixer_no_change(self):
        """无需修正时不修改"""
        fixer = YearTextFixer(target_year=2025)
        content = "2025财年，顺丰控股实现营收3,082亿元"
        fixed = fixer.fix(content)

        self.assertEqual(fixed, content)

    def test_full_pipeline(self):
        """完整流程: 注入→检测→修正"""
        anchor = YearAnchor(fiscal_year=2025)

        content = "2024财年，顺丰控股实现营收3,082亿元"
        result = anchor.process(content)

        self.assertTrue(result.has_errors)
        self.assertTrue(len(result.errors) > 0)
        self.assertIn("2025财年", result.fixed_content)
        self.assertIn("FY2025", result.prompt)

    def test_detect_detailed(self):
        """详细检测"""
        detector = YearErrorDetector(fiscal_year=2025)
        content = "2024财年，顺丰控股实现营收3,082亿元，净利润111亿元"
        errors = detector.detect_detailed(content)

        self.assertTrue(len(errors) > 0)
        self.assertTrue(hasattr(errors[0], 'pattern'))
        self.assertTrue(hasattr(errors[0], 'message'))
        self.assertTrue(hasattr(errors[0], 'location'))

    def test_fix_all_patterns(self):
        """修正所有模式"""
        fixer = YearTextFixer(target_year=2025)
        # 包含当前年份标志性数据
        content = "2024财年，FY2024，营收3,082亿元"
        fixed = fixer.fix_all_patterns(content)

        self.assertIn("2025财年", fixed)
        self.assertIn("FY2025", fixed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
