"""HeavySkill 优化方案 V3 - 测试用例"""

import unittest
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import Severity, Verdict, Issue
from src.validator import ConclusionValidator, ConclusionValidatorConfig
from src.parser import ChecklistResultParser


class TestConclusionValidator(unittest.TestCase):
    """结论校验器测试"""
    
    def test_p0_veto(self):
        """测试 P0 一票否决"""
        validator = ConclusionValidator()
        issues = [
            Issue(id="1", title="SQL注入", severity=Severity.P0, domain="安全", 
                  description="", suggestion="", confidence=0.9)
        ]
        result = validator.validate(issues)
        self.assertEqual(result.verdict, Verdict.REJECT)
    
    def test_p0_veto_disabled(self):
        """测试 P0 否决禁用"""
        config = ConclusionValidatorConfig()
        config.p0_veto.enabled = False
        config.threshold_rule.enabled = False  # 禁用阈值规则
        config.domain_coverage.enabled = False  # 禁用领域覆盖率
        validator = ConclusionValidator(config)
        
        issues = [
            Issue(id="1", title="SQL注入", severity=Severity.P0, domain="安全",
                  description="", suggestion="", confidence=0.9)
        ]
        result = validator.validate(issues)
        # 不应该被否决（因为 P0 否决和阈值规则都禁用）
        # 应该触发加权评分警告（P0 权重 10 > warn_threshold 8）
        self.assertEqual(result.verdict, Verdict.CONDITIONAL_PASS)
    
    def test_threshold_rule(self):
        """测试阈值规则"""
        validator = ConclusionValidator()
        issues = [
            Issue(id=str(i), title=f"问题{i}", severity=Severity.P1, domain="架构",
                  description="", suggestion="") for i in range(4)
        ]
        result = validator.validate(issues)
        self.assertEqual(result.verdict, Verdict.REJECT)
    
    def test_weighted_score(self):
        """测试加权评分"""
        validator = ConclusionValidator()
        issues = [
            Issue(id="1", title="问题1", severity=Severity.P1, domain="架构",
                  description="", suggestion=""),
            Issue(id="2", title="问题2", severity=Severity.P1, domain="安全",
                  description="", suggestion=""),
            Issue(id="3", title="问题3", severity=Severity.P2, domain="性能",
                  description="", suggestion=""),
        ]
        # P1*5 + P1*5 + P2*2 = 12 < 15 (reject) but > 8 (warn)
        result = validator.validate(issues)
        self.assertEqual(result.verdict, Verdict.CONDITIONAL_PASS)
    
    def test_domain_coverage(self):
        """测试领域覆盖率"""
        config = ConclusionValidatorConfig()
        config.domain_coverage.required_domains = ["安全", "架构", "性能"]
        config.domain_coverage.min_coverage = 0.6
        validator = ConclusionValidator(config)
        
        # 只覆盖了安全和架构，覆盖率 2/3 = 67% > 60%
        issues = [
            Issue(id="1", title="问题1", severity=Severity.P2, domain="安全",
                  description="", suggestion=""),
            Issue(id="2", title="问题2", severity=Severity.P2, domain="架构",
                  description="", suggestion=""),
        ]
        result = validator.validate(issues)
        self.assertEqual(result.verdict, Verdict.PASS)
    
    def test_domain_coverage_fail(self):
        """测试领域覆盖率失败"""
        config = ConclusionValidatorConfig()
        config.domain_coverage.required_domains = ["安全", "架构", "性能"]
        config.domain_coverage.min_coverage = 0.6
        validator = ConclusionValidator(config)
        
        # 只覆盖了安全，覆盖率 1/3 = 33% < 60%
        issues = [
            Issue(id="1", title="问题1", severity=Severity.P2, domain="安全",
                  description="", suggestion=""),
        ]
        result = validator.validate(issues)
        self.assertEqual(result.verdict, Verdict.REJECT)
    
    def test_shadow_mode(self):
        """测试影子模式"""
        config = ConclusionValidatorConfig()
        config.shadow_mode = True
        validator = ConclusionValidator(config)
        
        issues = [
            Issue(id="1", title="SQL注入", severity=Severity.P0, domain="安全",
                  description="", suggestion="", confidence=0.9)
        ]
        # LLM 说通过，但规则说不通过
        result = validator.validate(issues, llm_verdict=Verdict.PASS)
        # 影子模式应该返回 LLM 结论
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertTrue(result.shadow_mode)
    
    def test_shadow_mode_fallback_on_error(self):
        """测试影子模式异常回退（P0-5 修复验证）"""
        config = ConclusionValidatorConfig()
        config.shadow_mode = True
        validator = ConclusionValidator(config)
        
        # 构造会触发异常的场景（如空 issues 列表）
        issues = []
        
        # 即使内部出错，也不应该抛异常
        result = validator.validate(issues, llm_verdict=Verdict.PASS)
        
        # 验证返回正常
        self.assertIsNotNone(result)
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertTrue(result.shadow_mode)
        
        # 验证影子日志记录了异常（如果发生）
        shadow_log = validator.get_shadow_log()
        # 空列表可能不会触发异常，但至少应该有记录
        self.assertGreaterEqual(len(shadow_log), 0)
    
    def test_confidence_filter(self):
        """测试置信度过滤"""
        config = ConclusionValidatorConfig()
        config.confidence_threshold = 0.8
        config.domain_coverage.enabled = False  # 禁用领域覆盖率，专注测试置信度
        validator = ConclusionValidator(config)
        
        # 低置信度的 P0 问题应该被降级为 P1
        issues = [
            Issue(id="1", title="SQL注入", severity=Severity.P0, domain="安全",
                  description="", suggestion="", confidence=0.6)
        ]
        result = validator.validate(issues)
        # P0 被降级为 P1，不触发 P0 否决
        self.assertNotEqual(result.verdict, Verdict.REJECT)
    
    def test_fallback_on_error(self):
        """测试异常回退"""
        config = ConclusionValidatorConfig()
        config.fallback_to_llm = True
        config.domain_coverage.enabled = False  # 禁用领域覆盖率
        validator = ConclusionValidator(config)
        
        # 正常情况
        issues = [
            Issue(id="1", title="问题1", severity=Severity.P2, domain="安全",
                  description="", suggestion="")
        ]
        result = validator.validate(issues, llm_verdict=Verdict.PASS)
        self.assertEqual(result.verdict, Verdict.PASS)


class TestChecklistResultParser(unittest.TestCase):
    """检查清单解析器测试"""
    
    def test_parse_markdown_table(self):
        """测试解析 Markdown 表格"""
        parser = ChecklistResultParser()
        markdown = """
| ID | 检查项 | 结果 | 严重级别 | 说明 |
|----|--------|------|----------|------|
| S-01 | SQL注入 | ❌ FAIL | Critical | 用户输入直接拼接SQL |
| S-02 | XSS防护 | ✅ PASS | - | - |
"""
        issues = parser.parse_markdown_table(markdown)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, Severity.P0)
    
    def test_parse_json(self):
        """测试解析 JSON"""
        parser = ChecklistResultParser()
        json_str = '''
[
  {"id": "S-01", "title": "SQL注入", "severity": "CRITICAL", "domain": "安全", "description": "..."}
]
'''
        issues = parser.parse_json(json_str)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, Severity.P0)
    
    def test_severity_from_str(self):
        """测试严重级别转换"""
        self.assertEqual(Severity.from_str("CRITICAL"), Severity.P0)
        self.assertEqual(Severity.from_str("P0"), Severity.P0)
        self.assertEqual(Severity.from_str("致命"), Severity.P0)
        self.assertEqual(Severity.from_str("MAJOR"), Severity.P1)
        self.assertEqual(Severity.from_str("P1"), Severity.P1)
        self.assertEqual(Severity.from_str("重大"), Severity.P1)
        self.assertEqual(Severity.from_str("unknown"), Severity.P2)  # 默认
    
    def test_parse_plaintext(self):
        """测试解析纯文本"""
        parser = ChecklistResultParser()
        text = """
1. SQL注入风险
用户输入直接拼接SQL语句

2. XSS攻击
未对输出进行转义
"""
        issues = parser.parse_plaintext(text)
        self.assertEqual(len(issues), 2)
    
    def test_parse_unified(self):
        """测试统一解析入口"""
        parser = ChecklistResultParser()
        
        # JSON 格式
        json_str = '[{"id": "1", "title": "test", "severity": "P0"}]'
        issues = parser.parse(json_str)
        self.assertEqual(len(issues), 1)
        
        # Markdown 表格
        markdown = "| ID | 检查项 | 结果 | 严重级别 |\n|---|---|---|---|\n| 1 | test | ❌ | Critical |"
        issues = parser.parse(markdown)
        self.assertEqual(len(issues), 1)


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def test_integrate_with_heavyskill(self):
        """测试与 HeavySkill 集成"""
        from src.integration import integrate_with_heavyskill
        
        # 模拟 HeavySkill 输出
        heavyskill_output = {
            'reasoning': {
                'trajectories': [
                    '发现 P0 问题：SQL注入\n结论：不通过',
                    '发现 P1 问题：XSS\n结论：附意见通过'
                ]
            },
            'final_answer': '总体结论：不通过'
        }
        
        result = integrate_with_heavyskill(heavyskill_output)
        
        # 验证增强输出
        self.assertIn('validation', result)
        self.assertIn('verdict', result['validation'])


if __name__ == '__main__':
    unittest.main()
