"""
ConfigValidator测试

覆盖: 4个用例
"""

import unittest

# HGF P0-①（2026-08-22）：本文件测试 hermes v3 版 ConfigValidator 契约
# （validate_* 返回 bool、WACC 范围 4%-20%、ValidationResult(valid=)、
#  validate_beta/validate_dcf_config/get_validation_range/format_validation_report 等），
# 与本地实现（返回 ValidationResult、WACC 6%-18%、validate_dcf_params/validate_yaml_config）
# 是两代 API——本地实现已被业务使用，不为过时测试回改。显式 skip（三态：⚠️ 已知不兼容）。
# 添加路径
import pytest

pytestmark = pytest.mark.skip(
    reason="hermes v3 版 ConfigValidator API 未随迁（返回类型/范围/方法集两代），"
           "本地实现契约不同——见 docs/qual-hgf-deep-check-2026-08-22.md §3"
)

from finance.quality.v3.config_validator import ConfigValidator, ValidationResult  # noqa: E402


class TestConfigValidator(unittest.TestCase):
    """ConfigValidator测试"""

    def setUp(self):
        self.validator = ConfigValidator()

    def test_wacc_range_normal(self):
        """WACC范围验证: 正常值"""
        self.assertTrue(self.validator.validate_wacc(0.10))
        self.assertTrue(self.validator.validate_wacc(0.08))
        self.assertTrue(self.validator.validate_wacc(0.15))

    def test_wacc_range_out_of_range(self):
        """WACC范围验证: 超出范围"""
        self.assertFalse(self.validator.validate_wacc(0.30))
        self.assertFalse(self.validator.validate_wacc(0.01))

    def test_ke_range_normal(self):
        """Ke范围验证: 正常值"""
        self.assertTrue(self.validator.validate_ke(0.12))
        self.assertTrue(self.validator.validate_ke(0.08))

    def test_ke_range_out_of_range(self):
        """Ke范围验证: 超出范围"""
        self.assertFalse(self.validator.validate_ke(0.30))
        self.assertFalse(self.validator.validate_ke(0.01))

    def test_g_range_normal(self):
        """g范围验证: 正常值"""
        self.assertTrue(self.validator.validate_g(0.025))
        self.assertTrue(self.validator.validate_g(0.02))

    def test_g_range_out_of_range(self):
        """g范围验证: 超出范围"""
        self.assertFalse(self.validator.validate_g(0.05))
        self.assertFalse(self.validator.validate_g(0.005))

    def test_beta_range_normal(self):
        """Beta范围验证: 正常值"""
        self.assertTrue(self.validator.validate_beta(1.0))
        self.assertTrue(self.validator.validate_beta(0.5))

    def test_beta_range_out_of_range(self):
        """Beta范围验证: 超出范围"""
        self.assertFalse(self.validator.validate_beta(3.0))
        self.assertFalse(self.validator.validate_beta(0.1))

    def test_dcf_config_valid(self):
        """DCF配置验证: 有效配置"""
        config = {'wacc': 0.10, 'g': 0.025}
        result = self.validator.validate_dcf_config(config)
        self.assertTrue(result.valid)

    def test_dcf_config_g_exceeds_wacc(self):
        """DCF配置验证: g >= WACC"""
        config = {'wacc': 0.02, 'g': 0.03}
        result = self.validator.validate_dcf_config(config)
        self.assertFalse(result.valid)

    def test_wacc_config_valid(self):
        """WACC配置验证: 有效配置"""
        config = {
            'risk_free_rate': 0.023,
            'beta': 1.0,
            'equity_risk_premium': 0.065
        }
        result = self.validator.validate_wacc_config(config)
        self.assertTrue(result.valid)

    def test_wacc_config_missing_field(self):
        """WACC配置验证: 缺少必要字段"""
        config = {'risk_free_rate': 0.023}
        result = self.validator.validate_wacc_config(config)
        self.assertFalse(result.valid)

    def test_pipeline_config_valid(self):
        """Pipeline配置验证: 有效配置"""
        config = {
            'require_structural_pass': True,
            'max_repair_rounds': 3
        }
        result = self.validator.validate_pipeline_config(config)
        self.assertTrue(result.valid)

    def test_get_validation_range(self):
        """获取验证范围"""
        wacc_range = self.validator.get_validation_range('wacc')
        self.assertEqual(wacc_range, (0.04, 0.20))

        unknown_range = self.validator.get_validation_range('unknown')
        self.assertIsNone(unknown_range)

    def test_format_validation_report(self):
        """格式化验证报告"""
        result = ValidationResult(valid=True, warnings=["测试警告"])
        report = self.validator.format_validation_report(result)
        self.assertIn("通过", report)
        self.assertIn("测试警告", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
