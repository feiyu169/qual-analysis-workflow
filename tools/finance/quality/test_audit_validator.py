"""
AuditValidator测试

覆盖: 5个用例
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.audit_validator import AuditValidator, AuditIssue


class TestAuditValidator(unittest.TestCase):
    """AuditValidator测试"""
    
    def test_check_known_issues_wacc(self):
        """检查已知问题: WACC硬编码"""
        validator = AuditValidator()
        content = "WACC=10%，折现率取10%"
        
        issues = validator.check_known_issues(content)
        
        self.assertTrue(any("WACC硬编码" in i.message for i in issues))
    
    def test_check_known_issues_dcf_null(self):
        """检查已知问题: DCF为null"""
        validator = AuditValidator()
        content = "DCF结果为null，无法计算"
        
        issues = validator.check_known_issues(content)
        
        self.assertTrue(any("DCF" in i.message for i in issues))
    
    def test_check_known_issues_year_mismatch(self):
        """检查已知问题: 年份错标"""
        validator = AuditValidator()
        content = "2024财年，营收3082亿元"
        
        issues = validator.check_known_issues(content)
        
        self.assertTrue(any("年份错标" in i.message for i in issues))
    
    def test_check_known_issues_ai_trace(self):
        """检查已知问题: AI痕迹"""
        validator = AuditValidator()
        content = "作为AI语言模型，我分析如下"
        
        issues = validator.check_known_issues(content)
        
        self.assertTrue(any("AI痕迹" in i.message for i in issues))
    
    def test_check_config_consistency(self):
        """检查配置一致性"""
        validator = AuditValidator()
        
        config = {"wacc": 0.30, "g": 0.025}
        issues = validator.check_config_consistency(config)
        
        self.assertTrue(any("WACC" in i.message for i in issues))
    
    def test_check_config_g_exceeds_wacc(self):
        """检查配置: g >= WACC"""
        validator = AuditValidator()
        
        config = {"wacc": 0.02, "g": 0.03}
        issues = validator.check_config_consistency(config)
        
        self.assertTrue(any("永续增长率" in i.message for i in issues))
    
    def test_check_module_calls(self):
        """检查模块调用"""
        validator = AuditValidator()
        
        module_calls = ["结构化预检", "语义审计", "修复循环"]
        issues = validator.check_module_calls(module_calls)
        
        self.assertTrue(any("WACC计算" in i.message for i in issues))
    
    def test_check_self_audit(self):
        """检查自身审计"""
        validator = AuditValidator()
        
        audit_results = [
            {"score": 85},
            {"score": 86},
            {"score": 84},
        ]
        issues = validator.check_self_audit(audit_results)
        
        # 标准差约1.0 < 2.0，应触发警告
        self.assertTrue(any("标准差" in i.message for i in issues))
    
    def test_check_cross_validation(self):
        """交叉验证"""
        validator = AuditValidator()
        
        issues = validator.check_cross_validation(
            dcf_value=50,
            market_price=10,
            tolerance=0.5,
        )
        
        self.assertTrue(any("差异过大" in i.message for i in issues))
    
    def test_validate_full(self):
        """完整审计验证"""
        validator = AuditValidator()
        
        content = "WACC=10%，DCF估值50元"
        config = {"wacc": 0.10, "g": 0.025}
        
        issues = validator.validate(content, config)
        
        self.assertTrue(len(issues) > 0)
    
    def test_generate_audit_report(self):
        """生成审计报告"""
        validator = AuditValidator()
        
        issues = [
            AuditIssue(pattern="test", severity="ERROR", message="测试问题", suggestion="修复"),
        ]
        
        report = validator.generate_audit_report(issues)
        
        self.assertIn("审计报告", report)
        self.assertIn("测试问题", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
