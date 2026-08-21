"""
IncrementalChecker测试

覆盖: 5个用例
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.incremental_checker import IncrementalChecker


class TestIncrementalChecker(unittest.TestCase):
    """IncrementalChecker测试"""

    def test_detect_changes(self):
        """检测变更章节"""
        checker = IncrementalChecker()

        before = {
            "ch01": "内容A",
            "ch02": "内容B",
        }

        after = {
            "ch01": "内容A修改",  # 变更
            "ch02": "内容B",  # 未变
            "ch03": "新增内容",  # 新增
        }

        changed = checker.detect_changes(before, after)

        self.assertIn("ch01", changed)
        self.assertIn("ch03", changed)
        self.assertNotIn("ch02", changed)

    def test_check_incremental(self):
        """增量检查"""
        checker = IncrementalChecker()

        before = {"ch01": "内容A"}
        after = {"ch01": "内容A修改"}

        def mock_check(ch_id, content):
            if "修改" in content:
                return ["新问题"]
            return []

        result = checker.check_incremental(before, after, mock_check)

        self.assertIn("ch01", result.changed_chapters)
        self.assertIn("ch01", result.checked_chapters)
        self.assertTrue(any("[新增]" in i for i in result.new_issues))

    def test_check_incremental_resolved(self):
        """增量检查: 问题已解决"""
        checker = IncrementalChecker()

        before = {"ch01": "有问题的内容"}
        after = {"ch01": "已修正的内容"}

        def mock_check(ch_id, content):
            if "有问题" in content:
                return ["问题1"]
            return []

        result = checker.check_incremental(before, after, mock_check)

        self.assertTrue(any("[已解决]" in i for i in result.resolved_issues))

    def test_check_full(self):
        """全量检查"""
        checker = IncrementalChecker()

        chapters = {
            "ch01": "内容1",
            "ch02": "内容2",
        }

        def mock_check(ch_id, content):
            return [f"{ch_id}问题"]

        result = checker.check_full(chapters, mock_check)

        self.assertEqual(len(result.checked_chapters), 2)
        self.assertTrue(len(result.new_issues) > 0)

    def test_get_affected_chapters(self):
        """获取受影响的章节"""
        checker = IncrementalChecker()

        chapter_dependencies = {
            "ch01": [],
            "ch02": ["ch01"],  # ch02依赖ch01
            "ch03": ["ch01"],  # ch03依赖ch01
        }

        affected = checker.get_affected_chapters(
            changed_chapters={"ch01"},
            chapter_dependencies=chapter_dependencies,
        )

        self.assertIn("ch01", affected)
        self.assertIn("ch02", affected)
        self.assertIn("ch03", affected)

    def test_no_changes(self):
        """无变更场景"""
        checker = IncrementalChecker()

        before = {"ch01": "内容A"}
        after = {"ch01": "内容A"}

        def mock_check(ch_id, content):
            return []

        result = checker.check_incremental(before, after, mock_check)

        self.assertEqual(len(result.changed_chapters), 0)
        self.assertEqual(len(result.checked_chapters), 0)

    def test_generate_report(self):
        """生成报告"""
        checker = IncrementalChecker()

        before = {"ch01": "内容A"}
        after = {"ch01": "内容A修改"}

        def mock_check(ch_id, content):
            return []

        result = checker.check_incremental(before, after, mock_check)
        report = checker.generate_report(result)

        self.assertIn("增量检查报告", report)
        self.assertIn("检查章节数", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
