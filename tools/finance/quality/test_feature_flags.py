"""
FeatureFlags和ConfigValidator测试

测试覆盖:
- FeatureFlags: 8个测试
- ConfigValidator: 4个测试

"""

import sys
import os
import unittest

# 添加finance工具路径
sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.feature_flags import FeatureFlags, FeatureModule, FeatureDisabledError
from finance.quality.v3.config_validator import ConfigValidator, ValidationResult


class TestFeatureFlags(unittest.TestCase):
    """FeatureFlags测试"""
    
    def test_default_all_enabled(self):
        """测试默认配置: 所有模块启用"""
        flags = FeatureFlags.default()
        for module in FeatureModule:
            self.assertTrue(flags.is_enabled(module))
    
    def test_minimal_only_core(self):
        """测试最小配置: 仅核心模块"""
        flags = FeatureFlags.minimal()
        self.assertTrue(flags.is_enabled(FeatureModule.STRUCTURAL_CHECK))
        self.assertFalse(flags.is_enabled(FeatureModule.SEMANTIC_AUDIT))
        self.assertFalse(flags.is_enabled(FeatureModule.DCF))
    
    def test_no_llm(self):
        """测试无LLM配置: 禁用所有需要LLM的模块"""
        flags = FeatureFlags.no_llm()
        self.assertTrue(flags.is_enabled(FeatureModule.STRUCTURAL_CHECK))
        self.assertFalse(flags.is_enabled(FeatureModule.SEMANTIC_AUDIT))
        self.assertFalse(flags.is_enabled(FeatureModule.CAUSAL_INFERENCE))
        self.assertTrue(flags.is_enabled(FeatureModule.DCF))
    
    def test_valuation_only(self):
        """测试估值专项: 仅估值相关模块"""
        flags = FeatureFlags.valuation_only()
        self.assertTrue(flags.is_enabled(FeatureModule.DCF))
        self.assertTrue(flags.is_enabled(FeatureModule.SOTP))
        self.assertTrue(flags.is_enabled(FeatureModule.SENSITIVITY))
        self.assertFalse(flags.is_enabled(FeatureModule.SEMANTIC_AUDIT))
    
    def test_from_profile(self):
        """测试从profile创建"""
        flags = FeatureFlags.from_profile("minimal")
        self.assertTrue(flags.is_enabled(FeatureModule.STRUCTURAL_CHECK))
        self.assertFalse(flags.is_enabled(FeatureModule.SEMANTIC_AUDIT))
    
    def test_require_success(self):
        """测试require成功"""
        flags = FeatureFlags.default()
        flags.require(FeatureModule.STRUCTURAL_CHECK)  # 不应抛出异常
    
    def test_require_failure(self):
        """测试require失败"""
        flags = FeatureFlags.minimal()
        with self.assertRaises(FeatureDisabledError):
            flags.require(FeatureModule.SEMANTIC_AUDIT)
    
    def test_enabled_disabled_modules(self):
        """测试enabled_modules和disabled_modules"""
        flags = FeatureFlags.minimal()
        enabled = flags.enabled_modules()
        disabled = flags.disabled_modules()
        
        self.assertIn("structural_check", enabled)
        self.assertNotIn("semantic_audit", enabled)
        self.assertIn("semantic_audit", disabled)


class TestConfigValidator(unittest.TestCase):
    """ConfigValidator测试"""
    
    def setUp(self):
        self.validator = ConfigValidator()
    
    def test_validate_wacc_valid(self):
        """测试WACC有效值"""
        result = self.validator.validate_wacc(0.10)
        self.assertTrue(result.passed)
        self.assertIn("10.00%", result.message)
    
    def test_validate_wacc_invalid_low(self):
        """测试WACC过低"""
        result = self.validator.validate_wacc(0.03)
        self.assertFalse(result.passed)
        self.assertIn("超出合理范围", result.message)
    
    def test_validate_wacc_invalid_high(self):
        """测试WACC过高"""
        result = self.validator.validate_wacc(0.25)
        self.assertFalse(result.passed)
        self.assertIn("超出合理范围", result.message)
    
    def test_validate_ke_valid(self):
        """测试Ke有效值"""
        result = self.validator.validate_ke(0.12)
        self.assertTrue(result.passed)
        self.assertIn("12.00%", result.message)
    
    def test_validate_g_valid(self):
        """测试g有效值"""
        result = self.validator.validate_g(0.02, wacc=0.10)
        self.assertTrue(result.passed)
        self.assertIn("2.00%", result.message)
    
    def test_validate_g_exceeds_wacc(self):
        """测试g >= WACC"""
        result = self.validator.validate_g(0.12, wacc=0.10)
        self.assertFalse(result.passed)
        self.assertIn("必须小于WACC", result.message)
    
    def test_validate_dcf_params_valid(self):
        """测试DCF参数组合有效"""
        results = self.validator.validate_dcf_params(
            wacc=0.10,
            ke=0.12,
            g=0.02
        )
        self.assertTrue(all(r.passed for r in results))
    
    def test_validate_dcf_params_with_kd(self):
        """测试DCF参数组合含Kd"""
        # 使用一致的参数: WACC = Ke*(1-D) + Kd*(1-T)*D
        # 0.10 = 0.12*(1-0.20) + 0.05*(1-0.25)*0.20 = 0.096 + 0.0075 = 0.1035
        # 调整参数使WACC一致: 使用ke=0.118
        # 0.10 = 0.118*(1-0.20) + 0.05*(1-0.25)*0.20 = 0.0944 + 0.0075 = 0.1019
        # 还是不一致，直接使用精确计算值
        ke = 0.11625  # 使得 0.11625*0.8 + 0.05*0.75*0.2 = 0.093 + 0.0075 = 0.1005 ≈ 0.10
        results = self.validator.validate_dcf_params(
            wacc=0.10,
            ke=ke,
            g=0.02,
            kd=0.05,
            tax_rate=0.25,
            debt_ratio=0.20
        )
        # 检查WACC计算一致性
        consistency_check = [r for r in results if "计算一致性" in r.message]
        self.assertEqual(len(consistency_check), 1)
        self.assertTrue(consistency_check[0].passed)


if __name__ == "__main__":
    unittest.main()
