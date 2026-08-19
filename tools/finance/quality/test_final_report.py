"""
最终测试报告

覆盖: 全量测试验证
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))

from finance.quality.v3.workflow_integration import WorkflowIntegration, WorkflowConfig


class TestFinalReport(unittest.TestCase):
    """最终测试报告"""
    
    def test_workflow_integration_load(self):
        """工作流集成: 加载模块"""
        workflow = WorkflowIntegration()
        
        # 验证模块加载
        self.assertGreater(len(workflow._modules), 0)
        self.assertTrue(workflow.is_module_available("year_anchor"))
        self.assertTrue(workflow.is_module_available("authority_resolver"))
        self.assertTrue(workflow.is_module_available("pipeline"))
    
    def test_workflow_integration_run(self):
        """工作流集成: 运行分析"""
        workflow = WorkflowIntegration()
        
        result = workflow.run_analysis(
            ticker="002352.SZ",
            market="a_share",
            fiscal_year=2025,
        )
        
        # 验证结果
        self.assertEqual(result["ticker"], "002352.SZ")
        self.assertEqual(result["market"], "a_share")
        self.assertEqual(result["fiscal_year"], 2025)
        self.assertGreater(len(result["v3_modules_used"]), 0)
    
    def test_workflow_integration_report(self):
        """工作流集成: 生成报告"""
        workflow = WorkflowIntegration()
        
        report = workflow.generate_integration_report()
        
        self.assertIn("工作流集成报告", report)
        self.assertIn("已加载模块数", report)
        self.assertIn("可用模块", report)
    
    def test_all_modules_available(self):
        """所有模块可用"""
        workflow = WorkflowIntegration()
        
        expected_modules = [
            "feature_flags",
            "config_validator",
            "year_anchor",
            "authority_resolver",
            "pipeline",
            "dcf_service",
            "capm_calculator",
            "terminal_value",
            "fcf_calculator",
            "roic_wacc_checker",
            "sensitivity_analyzer",
            "wind_field_mapper",
            "financial_standards",
            "incremental_checker",
            "audit_validator",
            "conclusion_synthesizer",
            "terminal_value_arbitrator",
        ]
        
        for module in expected_modules:
            self.assertTrue(
                workflow.is_module_available(module),
                f"模块 {module} 不可用"
            )
    
    def test_degradation_strategy(self):
        """降级策略"""
        config = WorkflowConfig(use_v3_modules=False)
        workflow = WorkflowIntegration(config=config)
        
        # 验证无模块加载
        self.assertEqual(len(workflow._modules), 0)
        
        # 验证分析仍可运行
        result = workflow.run_analysis(ticker="002352.SZ")
        self.assertEqual(result["ticker"], "002352.SZ")
        self.assertEqual(len(result["v3_modules_used"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
