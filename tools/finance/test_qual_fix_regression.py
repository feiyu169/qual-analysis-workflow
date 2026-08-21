"""
Qual 工作流缺陷修复回归测试

覆盖：
1. success 判断降级路径
2. 辩论合并模式
3. 上游兼容性
"""
from finance.quality_enhancer import QualityEnhancementResult, _merge_debate_result


class MockDebateResult:
    """模拟辩论结果"""
    def __init__(self, bull="看多论点", bear="看空质疑", pm="PM综合",
                 conviction=0.8, catalysts=None, triggers=None, degraded=False):
        self.bull_argument = bull
        self.bear_argument = bear
        self.pm_synthesis = pm
        self.conviction_score = conviction
        self.catalysts = catalysts or []
        self.triggers = triggers or []
        self.degraded = degraded


class TestDebateMergeMode:
    """辩论合并模式测试"""

    def test_original_content_preserved(self):
        """原始内容保留"""
        original = "## 结论要点\nDAU 4.1亿\n## 证据与出处\n[来源：财报]"
        debate = MockDebateResult()

        merged = _merge_debate_result(original, debate)

        # 原始内容保留
        assert "## 结论要点" in merged
        assert "DAU 4.1亿" in merged
        assert "[来源：财报]" in merged

    def test_debate_content_in_fold_tags(self):
        """辩论内容在折叠标签中"""
        original = "原始内容"
        debate = MockDebateResult(
            bull="看多论点详细内容",
            bear="看空质疑详细内容",
            pm="PM综合判断"
        )

        merged = _merge_debate_result(original, debate)

        # 折叠标签
        assert "<details><summary>看多论点</summary>" in merged
        assert "看多论点详细内容" in merged
        assert "<details><summary>看空质疑</summary>" in merged
        assert "看空质疑详细内容" in merged
        assert "<details><summary>PM 综合判断</summary>" in merged
        assert "PM综合判断" in merged

    def test_full_content_preserved_no_truncation(self):
        """完整内容保留（无截断）"""
        long_bull = "A" * 1000 + "\n\n" + "B" * 500
        original = "原始内容"
        debate = MockDebateResult(bull=long_bull)

        merged = _merge_debate_result(original, debate)

        # 完整内容保留
        assert "A" * 1000 in merged
        assert "B" * 500 in merged

    def test_catalysts_and_triggers_displayed(self):
        """催化剂和触发条件展示"""
        original = "原始内容"
        debate = MockDebateResult(
            catalysts=["催化剂1", "催化剂2", "催化剂3"],
            triggers=["触发条件1", "触发条件2"]
        )

        merged = _merge_debate_result(original, debate)

        assert "催化剂" in merged
        assert "催化剂1" in merged
        assert "触发条件" in merged
        assert "触发条件1" in merged

    def test_conviction_score_displayed(self):
        """确信度展示"""
        original = "原始内容"
        debate = MockDebateResult(conviction=0.75)

        merged = _merge_debate_result(original, debate)

        assert "确信度" in merged
        assert "75%" in merged

    def test_separation_line_added(self):
        """分隔线添加"""
        original = "原始内容"
        debate = MockDebateResult()

        merged = _merge_debate_result(original, debate)

        assert "---" in merged


class TestQualityDegradation:
    """质量降级测试"""

    def test_quality_enhancement_result_has_warnings(self):
        """QualityEnhancementResult 有 warnings 字段"""
        result = QualityEnhancementResult()
        assert hasattr(result, 'warnings')
        assert isinstance(result.warnings, list)

    def test_quality_enhancement_result_warnings_default_empty(self):
        """warnings 默认为空"""
        result = QualityEnhancementResult()
        assert len(result.warnings) == 0


class TestEdgeCases:
    """边界情况测试"""

    def test_empty_original(self):
        """空原始内容"""
        original = ""
        debate = MockDebateResult()

        merged = _merge_debate_result(original, debate)

        assert "辩论增强" in merged
        assert "看多论点" in merged

    def test_empty_debate_arguments(self):
        """空辩论内容"""
        original = "原始内容"
        debate = MockDebateResult(bull="", bear="", pm="")

        merged = _merge_debate_result(original, debate)

        # 原始内容保留
        assert "原始内容" in merged
        # 辩论标签存在
        assert "辩论增强" in merged

    def test_none_catalysts_and_triggers(self):
        """None 催化剂和触发条件"""
        original = "原始内容"
        debate = MockDebateResult(catalysts=None, triggers=None)

        merged = _merge_debate_result(original, debate)

        # 不应崩溃
        assert "原始内容" in merged
