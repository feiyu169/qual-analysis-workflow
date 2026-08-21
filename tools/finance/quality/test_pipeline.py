"""
QualityPipeline测试

覆盖: 7个用例
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.pipeline import ChapterQualityInput, QualityPipeline


class TestQualityPipeline(unittest.TestCase):
    """QualityPipeline测试"""

    def test_normal_path(self):
        """正常路径"""
        pipeline = QualityPipeline()
        content = "结论要点: 顺丰控股是中国领先的物流公司\n详细分析: " + "详细内容" * 50 + "\n证据与出处: 年报数据"
        input_data = ChapterQualityInput(
            chapter_id="ch01",
            content=content,
            contract={"must_answer": ["商业模式"]},
        )

        result = pipeline.run_chapter_quality(input_data)

        self.assertFalse(result.blocked)
        self.assertIsNotNone(result.structural)
        self.assertTrue(result.structural.passed)

    def test_structural_fail_short_content(self):
        """结构化预检失败: 内容过短"""
        pipeline = QualityPipeline()
        input_data = ChapterQualityInput(
            chapter_id="ch01",
            content="太短",
            contract={},
        )

        result = pipeline.run_chapter_quality(input_data)

        self.assertTrue(result.blocked)
        self.assertIn("过短", result.block_reason)

    def test_structural_fail_missing_sections(self):
        """结构化预检失败: 缺少必需小节"""
        pipeline = QualityPipeline()
        content = "这是一段很长的内容" * 50  # 足够长但缺少结构
        input_data = ChapterQualityInput(
            chapter_id="ch01",
            content=content,
            contract={},
        )

        result = pipeline.run_chapter_quality(input_data)

        self.assertTrue(result.blocked)
        self.assertIn("缺少必需小节", result.block_reason)

    def test_audit_with_must_answer(self):
        """语义审计: must_answer检查"""
        pipeline = QualityPipeline()
        # 内容包含"商业模式"关键词，且长度>200
        content = "结论要点: 顺丰控股是物流公司\n详细分析: 商业模式是直营模式，客户包括B端和C端，收入来源多元化，覆盖时效快递、经济快递、快运、冷链、同城即时配送及国际供应链等业务板块，核心竞争力是重资产投入构建的物理网络壁垒，包括亚洲最大的货运机队和遍布全国的转运中心，以及强大的运营管理体系和品牌信任，2025年营收3082亿元\n证据与出处: 年报数据来源于顺丰控股2025年年度报告，Wind金融终端数据，公司公告"
        input_data = ChapterQualityInput(
            chapter_id="ch01",
            content=content,
            contract={"must_answer": ["商业模式"]},
        )

        result = pipeline.run_chapter_quality(input_data)

        self.assertIsNotNone(result.audit)
        self.assertTrue(result.audit.passed)  # "商业模式"在内容中

    def test_audit_with_unanswered(self):
        """语义审计: 未回答的问题"""
        pipeline = QualityPipeline()
        # 内容不包含"客户画像"关键词，且长度>200
        content = "结论要点: 顺丰控股是物流公司\n详细分析: 商业模式是直营模式，收入来源多元化，覆盖时效快递、经济快递、快运、冷链、同城即时配送及国际供应链等业务板块，核心竞争力是重资产投入构建的物理网络壁垒，包括亚洲最大的货运机队和遍布全国的转运中心，以及强大的运营管理体系和品牌信任，2025年营收3082亿元，净利润111亿元\n证据与出处: 年报数据来源于顺丰控股2025年年度报告，Wind金融终端数据，公司公告，券商研报"
        input_data = ChapterQualityInput(
            chapter_id="ch01",
            content=content,
            contract={"must_answer": ["客户画像"]},
        )

        result = pipeline.run_chapter_quality(input_data)

        self.assertIsNotNone(result.audit)
        self.assertFalse(result.audit.passed)  # "客户画像"不在内容中

    def test_degradation_on_audit_failure(self):
        """语义审计失败时降级"""
        pipeline = QualityPipeline()

        # 模拟LLM调用失败的场景
        class FailingCaller:
            def __call__(self, *args, **kwargs):
                raise RuntimeError("LLM调用失败")

        content = "结论要点: 顺丰控股是物流公司\n详细分析: ...\n证据与出处: " + "数据" * 50
        input_data = ChapterQualityInput(
            chapter_id="ch01",
            content=content,
            contract={"must_answer": ["商业模式"]},
            llm_caller=FailingCaller(),
        )

        result = pipeline.run_chapter_quality(input_data)

        self.assertIsNotNone(result)

    def test_batch_processing(self):
        """批量处理"""
        pipeline = QualityPipeline()

        inputs = [
            ChapterQualityInput(
                chapter_id=f"ch{i:02d}",
                content=f"结论要点: 章节{i}内容\n详细分析: " + "内容" * 50 + "\n证据与出处: 数据",
                contract={},
            )
            for i in range(5)
        ]

        results = pipeline.run_batch(inputs)

        self.assertEqual(len(results), 5)
        for result in results:
            self.assertIsNotNone(result.structural)

    def test_summary(self):
        """摘要生成"""
        pipeline = QualityPipeline()

        inputs = [
            ChapterQualityInput(
                chapter_id=f"ch{i:02d}",
                content=f"结论要点: 章节{i}内容\n详细分析: " + "内容" * 50 + "\n证据与出处: 数据",
                contract={},
            )
            for i in range(5)
        ]

        results = pipeline.run_batch(inputs)
        summary = pipeline.get_summary(results)

        self.assertEqual(summary["total"], 5)
        self.assertIn("pass_rate", summary)

    def test_checkpoint_saves(self):
        """断点保存"""
        pipeline = QualityPipeline()
        content = "结论要点: 顺丰控股是物流公司\n详细分析: " + "详细内容" * 50 + "\n证据与出处: 年报数据"
        input_data = ChapterQualityInput(
            chapter_id="ch01",
            content=content,
            contract={},
        )

        result = pipeline.run_chapter_quality(input_data)

        self.assertIsNotNone(result.checkpoint)
        self.assertTrue(result.checkpoint.saved)


if __name__ == "__main__":
    unittest.main(verbosity=2)
