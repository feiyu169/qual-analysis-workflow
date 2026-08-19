"""
AuthorityResolver测试

覆盖: 8个用例
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.authority_resolver import (
    AuthorityResolver, AuthorityResult, AuthorityLevel, ConflictMode
)


class TestAuthorityResolver(unittest.TestCase):
    """AuthorityResolver测试"""
    
    def test_l1_pass_l2_pass(self):
        """L1通过, L2通过 → 直接通过"""
        resolver = AuthorityResolver()
        
        l1 = AuthorityResult(level=AuthorityLevel.PRIMARY, passed=True, score=85)
        l2 = AuthorityResult(level=AuthorityLevel.SUPPLEMENTARY, passed=True, score=90)
        
        result = resolver.resolve(l1, l2)
        
        self.assertTrue(result.final_passed)
        self.assertEqual(result.winner, AuthorityLevel.PRIMARY)
    
    def test_l1_pass_l2_fail_voting(self):
        """L1通过, L2失败 → 投票模式"""
        resolver = AuthorityResolver()
        
        l1 = AuthorityResult(level=AuthorityLevel.PRIMARY, passed=True, score=85)
        l2 = AuthorityResult(level=AuthorityLevel.SUPPLEMENTARY, passed=False, score=60)
        
        result = resolver.resolve(l1, l2)
        
        self.assertEqual(result.mode, ConflictMode.VOTING)
        self.assertTrue(result.final_passed)  # L1权重0.7 > L2权重0.3
    
    def test_l1_fail_cascade(self):
        """L1失败 → 级联模式"""
        resolver = AuthorityResolver()
        
        l1 = AuthorityResult(level=AuthorityLevel.PRIMARY, passed=False, issues=["结构化预检失败"])
        l2 = AuthorityResult(level=AuthorityLevel.SUPPLEMENTARY, passed=True, score=90)
        
        result = resolver.resolve(l1, l2)
        
        self.assertEqual(result.mode, ConflictMode.CASCADE)
        self.assertFalse(result.final_passed)
    
    def test_l3_fatal_veto(self):
        """L3发现FATAL → 否决模式"""
        resolver = AuthorityResolver()
        
        l1 = AuthorityResult(level=AuthorityLevel.PRIMARY, passed=True, score=85)
        l3 = AuthorityResult(level=AuthorityLevel.SUPERVISORY, passed=False, issues=["FATAL: DCF值不一致"])
        
        result = resolver.resolve(l1, l2_result=None, l3_result=l3)
        
        self.assertEqual(result.mode, ConflictMode.VETO)
        self.assertFalse(result.final_passed)
    
    def test_l3_error_voting(self):
        """L3发现ERROR → 投票模式"""
        resolver = AuthorityResolver()
        
        l1 = AuthorityResult(level=AuthorityLevel.PRIMARY, passed=True, score=85)
        l3 = AuthorityResult(level=AuthorityLevel.SUPERVISORY, passed=False, issues=["ERROR: PE口径不一致"])
        
        result = resolver.resolve(l1, l2_result=None, l3_result=l3)
        
        # L3 ERROR不触发否决，但会添加到warnings
        self.assertTrue(result.final_passed)
        self.assertTrue(len(result.warnings) > 0)
    
    def test_l3_warn_only(self):
        """L3发现WARN → 仅记录"""
        resolver = AuthorityResolver()
        
        l1 = AuthorityResult(level=AuthorityLevel.PRIMARY, passed=True, score=85)
        l3 = AuthorityResult(level=AuthorityLevel.SUPERVISORY, passed=True, warnings=["评分标准差过小"])
        
        result = resolver.resolve(l1, l2_result=None, l3_result=l3)
        
        self.assertTrue(result.final_passed)
        self.assertIn("评分标准差过小", result.warnings)
    
    def test_fallback_on_exception(self):
        """自身失败回退"""
        resolver = AuthorityResolver()
        
        # 模拟异常
        class BadResult:
            @property
            def passed(self):
                raise RuntimeError("模拟异常")
        
        l1 = AuthorityResult(level=AuthorityLevel.PRIMARY, passed=True, score=85)
        
        result = resolver.resolve_with_fallback(l1, BadResult())
        
        self.assertEqual(result.mode, ConflictMode.CASCADE)
        self.assertTrue(result.final_passed)  # 回退到L1
    
    def test_decision_matrix(self):
        """决策矩阵完整性"""
        resolver = AuthorityResolver()
        matrix = resolver.get_decision_matrix()
        
        self.assertIn("L1_pass_L2_pass", matrix)
        self.assertIn("L1_pass_L2_fail", matrix)
        self.assertIn("L1_fail_L2_any", matrix)
        self.assertIn("L3_FATAL", matrix)
        self.assertIn("L3_ERROR", matrix)
        self.assertIn("L3_WARN", matrix)
    
    def test_voting_weights(self):
        """投票权重验证"""
        resolver = AuthorityResolver()
        
        self.assertEqual(resolver.WEIGHTS[AuthorityLevel.PRIMARY], 0.7)
        self.assertEqual(resolver.WEIGHTS[AuthorityLevel.SUPPLEMENTARY], 0.3)
        self.assertEqual(resolver.WEIGHTS[AuthorityLevel.SUPERVISORY], 0.5)
    
    def test_l1_pass_l2_none(self):
        """L1通过, L2不存在 → 直接通过"""
        resolver = AuthorityResolver()
        
        l1 = AuthorityResult(level=AuthorityLevel.PRIMARY, passed=True, score=85)
        
        result = resolver.resolve(l1)
        
        self.assertTrue(result.final_passed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
