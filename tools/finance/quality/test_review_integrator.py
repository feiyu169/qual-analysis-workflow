"""
ReviewIntegrator测试

覆盖: 6个用例
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.review_integrator import ReviewConfig, ReviewIntegrator, ReviewIssue, ReviewResult


class TestReviewIntegrator(unittest.TestCase):
    """ReviewIntegrator测试"""

    def test_default_config(self):
        """默认配置"""
        config = ReviewConfig()

        self.assertTrue(config.enabled)
        self.assertEqual(config.max_rounds, 5)
        self.assertEqual(config.threshold, "P1")
        self.assertTrue(config.auto_fix_p0)
        self.assertTrue(config.auto_fix_p1)
        self.assertTrue(config.auto_fix_p2)
        self.assertEqual(config.review_subdir, "reviews")

    def test_review_passed_p0(self):
        """P0阈值检查"""
        integrator = ReviewIntegrator(ReviewConfig(threshold="P0"))

        # 无致命问题 → 通过
        result = ReviewResult(review_path="")
        self.assertTrue(integrator._is_review_passed(result))

        # 有致命问题 → 不通过
        result.fatal_issues.append(ReviewIssue(
            level="fatal",
            category="data",
            description="错误",
            location="",
            fix_suggestion="",
        ))
        self.assertFalse(integrator._is_review_passed(result))

    def test_review_passed_p1(self):
        """P1阈值检查"""
        integrator = ReviewIntegrator(ReviewConfig(threshold="P1"))

        # 无致命和重要问题 → 通过
        result = ReviewResult(review_path="")
        self.assertTrue(integrator._is_review_passed(result))

        # 有重要问题 → 不通过
        result.important_issues.append(ReviewIssue(
            level="important",
            category="data",
            description="错误",
            location="",
            fix_suggestion="",
        ))
        self.assertFalse(integrator._is_review_passed(result))

    def test_review_passed_p2(self):
        """P2阈值检查"""
        integrator = ReviewIntegrator(ReviewConfig(threshold="P2"))

        # 无任何问题 → 通过
        result = ReviewResult(review_path="")
        self.assertTrue(integrator._is_review_passed(result))

        # 有建议问题 → 不通过
        result.suggestion_issues.append(ReviewIssue(
            level="suggestion",
            category="data",
            description="优化",
            location="",
            fix_suggestion="",
        ))
        self.assertFalse(integrator._is_review_passed(result))

    def test_quality_score(self):
        """质量评分计算"""
        integrator = ReviewIntegrator()

        # 无问题 → 100分
        result = ReviewResult(review_path="")
        self.assertEqual(integrator._calculate_quality_score(result), 100.0)

        # 1个致命问题 → 80分
        result.fatal_issues.append(ReviewIssue(
            level="fatal",
            category="data",
            description="错误",
            location="",
            fix_suggestion="",
        ))
        self.assertEqual(integrator._calculate_quality_score(result), 80.0)

        # 1个重要问题 → 75分
        result.important_issues.append(ReviewIssue(
            level="important",
            category="data",
            description="错误",
            location="",
            fix_suggestion="",
        ))
        self.assertEqual(integrator._calculate_quality_score(result), 75.0)

    def test_get_issues_to_fix(self):
        """获取需要修正的问题"""
        config = ReviewConfig(auto_fix_p0=True, auto_fix_p1=True, auto_fix_p2=True)
        integrator = ReviewIntegrator(config)

        result = ReviewResult(review_path="")
        result.fatal_issues.append(ReviewIssue(level="fatal", category="data", description="P0", location="", fix_suggestion=""))
        result.important_issues.append(ReviewIssue(level="important", category="data", description="P1", location="", fix_suggestion=""))
        result.suggestion_issues.append(ReviewIssue(level="suggestion", category="data", description="P2", location="", fix_suggestion=""))

        issues = integrator._get_issues_to_fix(result)
        self.assertEqual(len(issues), 3)

    def test_parse_review_result(self):
        """解析审查结果"""
        integrator = ReviewIntegrator()

        content = """
## 致命问题

【致命-1】可比公司选错行业

【致命-2】经营现金流数据错误

## 重要问题

【重要-1】净利润口径混用

【重要-2】WACC未统一

【重要-3】PM判断分裂

## 建议

【建议-1】补充资本开支口径说明
"""

        result = integrator._parse_review_result(content)

        self.assertEqual(len(result.fatal_issues), 2)
        self.assertEqual(len(result.important_issues), 3)
        self.assertEqual(len(result.suggestion_issues), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
