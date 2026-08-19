"""
Mock策略测试

覆盖: 三层Mock策略
- L1精确: 固定返回值
- L2行为: 调用序列
- L3异常: 注入失败
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/.hermes/tools"))


class TestMockStrategy(unittest.TestCase):
    """Mock策略测试"""
    
    def test_l1_precise_mock_wind(self):
        """L1精确Mock: Wind API"""
        
        class WindMockL1:
            """精确返回固定数据"""
            
            SHUNFENG_DATA = {
                "income": {"年营业总收入": [2584, 2844, 3082]},
                "balance": {"近3年每年资产总计": [2215, 2138, 2165]},
                "cashflow": {"过去3年每年经营活动产生的现金流量净额": [265.7, 321.9, 275.6]},
            }
            
            def get_data(self, windcode, data_type):
                return self.SHUNFENG_DATA.get(data_type, {})
        
        mock = WindMockL1()
        
        income_data = mock.get_data("002352.SZ", "income")
        self.assertEqual(income_data["年营业总收入"], [2584, 2844, 3082])
        
        balance_data = mock.get_data("002352.SZ", "balance")
        self.assertEqual(balance_data["近3年每年资产总计"], [2215, 2138, 2165])
    
    def test_l2_behavior_mock_llm(self):
        """L2行为Mock: LLM"""
        
        class LLMMockL2:
            """按调用序列返回"""
            
            RESPONSES = [
                "第1章内容: 顺丰控股是物流公司",
                "第2章内容: 商业模式分析",
                '{"passed": true, "score": 85}',
            ]
            
            def __init__(self):
                self.call_count = 0
            
            def __call__(self, prompt):
                response = self.RESPONSES[self.call_count % len(self.RESPONSES)]
                self.call_count += 1
                return response
        
        mock = LLMMockL2()
        
        self.assertEqual(mock("prompt1"), "第1章内容: 顺丰控股是物流公司")
        self.assertEqual(mock("prompt2"), "第2章内容: 商业模式分析")
        self.assertEqual(mock("prompt3"), '{"passed": true, "score": 85}')
        
        self.assertEqual(mock("prompt4"), "第1章内容: 顺丰控股是物流公司")
    
    def test_l3_error_mock_timeout(self):
        """L3异常Mock: 超时"""
        
        class ErrorMockL3:
            """注入各种失败"""
            
            def timeout(self):
                raise TimeoutError("LLM调用超时")
            
            def network_error(self):
                raise ConnectionError("网络连接失败")
            
            def invalid_json(self):
                return "这不是JSON"
        
        mock = ErrorMockL3()
        
        with self.assertRaises(TimeoutError):
            mock.timeout()
        
        with self.assertRaises(ConnectionError):
            mock.network_error()
        
        result = mock.invalid_json()
        self.assertEqual(result, "这不是JSON")
    
    def test_l1_mock_calculator(self):
        """L1 Mock: 计算器"""
        
        class MockCalculator:
            """Mock计算器"""
            
            def calculate(self, inputs):
                return {"result": 42, "method": "mock"}
        
        mock = MockCalculator()
        result = mock.calculate({"data": 100})
        
        self.assertEqual(result["result"], 42)
        self.assertEqual(result["method"], "mock")
    
    def test_l2_mock_pipeline(self):
        """L2 Mock: Pipeline"""
        
        class MockCheckFunction:
            """Mock检查函数"""
            
            def __init__(self):
                self.call_count = 0
            
            def __call__(self, ch_id, content):
                self.call_count += 1
                if "问题" in content:
                    return ["发现问题"]
                return []
        
        mock = MockCheckFunction()
        
        # 测试正常内容
        issues = mock("ch01", "正常内容")
        self.assertEqual(issues, [])
        
        # 测试有问题的内容
        issues = mock("ch02", "有问题的内容")
        self.assertEqual(issues, ["发现问题"])
        
        # 验证调用次数
        self.assertEqual(mock.call_count, 2)
    
    def test_mock_granularity_levels(self):
        """Mock粒度级别"""
        
        # L1精确: 固定返回值
        class PreciseMock:
            def get_value(self):
                return 42
        
        precise = PreciseMock()
        self.assertEqual(precise.get_value(), 42)
        
        # L2行为: 调用序列
        class SequenceMock:
            def __init__(self):
                self.values = [1, 2, 3]
                self.index = 0
            
            def get_value(self):
                value = self.values[self.index % len(self.values)]
                self.index += 1
                return value
        
        sequence = SequenceMock()
        self.assertEqual(sequence.get_value(), 1)
        self.assertEqual(sequence.get_value(), 2)
        self.assertEqual(sequence.get_value(), 3)
        self.assertEqual(sequence.get_value(), 1)
        
        # L3异常: 注入失败
        class ErrorMock:
            def get_value(self):
                raise RuntimeError("模拟错误")
        
        error = ErrorMock()
        with self.assertRaises(RuntimeError):
            error.get_value()


if __name__ == "__main__":
    unittest.main(verbosity=2)
