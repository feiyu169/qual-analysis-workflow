"""
WindFieldMapper测试

覆盖: 5个用例
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.wind_field_mapper import WindFieldMapper


class TestWindFieldMapper(unittest.TestCase):
    """WindFieldMapper测试"""

    def test_a_share_mapping(self):
        """A股字段映射"""
        mapper = WindFieldMapper()
        field_name = mapper.get_field_name("operating_cashflow", "a_share")

        self.assertIsNotNone(field_name)
        self.assertIn("S_FA_", field_name)

    def test_hk_share_mapping(self):
        """港股字段映射"""
        mapper = WindFieldMapper()
        field_name = mapper.get_field_name("operating_cashflow", "hk_share")

        self.assertIsNotNone(field_name)
        self.assertIn("NET_CASH_", field_name)

    def test_us_share_mapping(self):
        """美股字段映射"""
        mapper = WindFieldMapper()
        field_name = mapper.get_field_name("operating_cashflow", "us_share")

        self.assertIsNotNone(field_name)
        self.assertIn("_TTM", field_name)

    def test_detect_market(self):
        """检测市场"""
        mapper = WindFieldMapper()

        self.assertEqual(mapper.detect_market("002352.SZ"), "a_share")
        self.assertEqual(mapper.detect_market("0700.HK"), "hk_share")
        self.assertEqual(mapper.detect_market("AAPL.OQ"), "us_share")

    def test_validate_field_names(self):
        """验证字段名"""
        mapper = WindFieldMapper()

        data = {
            "S_FA_OCFL_TTM_510200000": 100,  # 有效A股字段
            "INVALID_FIELD": 200,  # 无效字段
        }

        valid, invalid = mapper.validate_field_names(data, "a_share")

        self.assertIn("S_FA_OCFL_TTM_510200000", valid)
        self.assertIn("INVALID_FIELD", invalid)

    def test_map_financial_data(self):
        """映射财务数据"""
        mapper = WindFieldMapper()

        data = {
            "operating_cashflow": 100,
            "capex": 50,
        }

        mapped = mapper.map_financial_data(data, "a_share")

        self.assertIn("S_FA_OCFL_TTM_510200000", mapped)
        self.assertEqual(mapped["S_FA_OCFL_TTM_510200000"], 100)

    def test_get_common_mistakes(self):
        """获取常见错误"""
        mapper = WindFieldMapper()

        mistakes = mapper.get_common_mistakes("a_share")
        self.assertTrue(len(mistakes) > 0)

    def test_generate_mapping_report(self):
        """生成映射报告"""
        mapper = WindFieldMapper()

        report = mapper.generate_mapping_report("a_share")
        self.assertIn("a_share", report)
        self.assertIn("Wind字段", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
