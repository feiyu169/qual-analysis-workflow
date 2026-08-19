"""
Qual流程v8.4 - 测试模块
"""

import unittest
import time
from typing import Dict, Any

from ..core.state_machine import StateMachine, GateState, WorkflowState
from ..core.audit_logger import AuditLogger
from ..core.circuit_breaker import CircuitBreaker, ErrorType as CBErrorType
from ..core.error_classifier import ErrorClassifier, ErrorType as ECErrorType
from ..core.supervisor import FlowComplianceChecker
from ..gates.gate0 import Gate0DataSourceValidation


class TestStateMachine(unittest.TestCase):
    """测试状态机"""
    
    def test_initialize_gates(self):
        """测试初始化Gate"""
        sm = StateMachine()
        sm.initialize_gates([0, 1, 2])
        
        self.assertEqual(sm.get_gate_state(0), GateState.PENDING)
        self.assertEqual(sm.get_gate_state(1), GateState.PENDING)
        self.assertEqual(sm.get_gate_state(2), GateState.PENDING)
    
    def test_transition_gate(self):
        """测试Gate状态转换"""
        sm = StateMachine()
        sm.initialize_gates([0])
        
        # PENDING -> RUNNING
        self.assertTrue(sm.transition_gate(0, GateState.RUNNING))
        self.assertEqual(sm.get_gate_state(0), GateState.RUNNING)
        
        # RUNNING -> PASSED
        self.assertTrue(sm.transition_gate(0, GateState.PASSED))
        self.assertEqual(sm.get_gate_state(0), GateState.PASSED)
    
    def test_invalid_transition(self):
        """测试无效状态转换"""
        sm = StateMachine()
        sm.initialize_gates([0])
        
        # PENDING -> PASSED (无效，必须经过RUNNING)
        self.assertFalse(sm.transition_gate(0, GateState.PASSED))
    
    def test_workflow_state(self):
        """测试工作流状态"""
        sm = StateMachine()
        
        # INITIALIZED -> RUNNING
        self.assertTrue(sm.transition_workflow(WorkflowState.RUNNING))
        self.assertEqual(sm.get_workflow_state(), WorkflowState.RUNNING)
        
        # RUNNING -> COMPLETED
        self.assertTrue(sm.transition_workflow(WorkflowState.COMPLETED))
        self.assertEqual(sm.get_workflow_state(), WorkflowState.COMPLETED)
    
    def test_can_execute_gate(self):
        """测试Gate执行条件检查"""
        sm = StateMachine()
        sm.initialize_gates([0, 1])
        sm.transition_gate(0, GateState.RUNNING)
        sm.transition_gate(0, GateState.PASSED)
        
        # Gate 1 的前置条件 Gate 0 已通过
        self.assertTrue(sm.can_execute_gate(1, [0]))
        
        # Gate 0 不能重新执行（已PASSED）
        self.assertFalse(sm.can_execute_gate(0, []))


class TestAuditLogger(unittest.TestCase):
    """测试审计日志"""
    
    def test_log_entry(self):
        """测试记录日志"""
        logger = AuditLogger()
        
        entry = logger.log(
            run_id="test_run",
            gate_num=0,
            action="test_action",
            details={"key": "value"},
        )
        
        self.assertEqual(entry.run_id, "test_run")
        self.assertEqual(entry.gate_num, 0)
        self.assertEqual(entry.action, "test_action")
    
    def test_chain_verification(self):
        """测试链验证"""
        logger = AuditLogger()
        
        # 记录多条日志
        logger.log("run1", 0, "action1", {})
        logger.log("run1", 1, "action2", {})
        logger.log("run1", 2, "action3", {})
        
        # 验证链完整性
        self.assertTrue(logger.verify_chain())
    
    def test_chain_tampering(self):
        """测试链篡改检测"""
        logger = AuditLogger()
        
        # 记录日志
        logger.log("run1", 0, "action1", {})
        logger.log("run1", 1, "action2", {})
        
        # 篡改日志
        logger.entries[0].details = {"tampered": True}
        
        # 验证链完整性（应该失败）
        self.assertFalse(logger.verify_chain())


class TestCircuitBreaker(unittest.TestCase):
    """测试熔断器"""
    
    def test_initial_state(self):
        """测试初始状态"""
        cb = CircuitBreaker("test")
        self.assertEqual(cb.get_state(), CircuitState.CLOSED)
        self.assertTrue(cb.can_execute())
    
    def test_failure_threshold(self):
        """测试失败阈值"""
        cb = CircuitBreaker("test", failure_threshold=3)
        
        # 记录失败
        cb.record_failure(CBErrorType.PERMANENT)
        cb.record_failure(CBErrorType.PERMANENT)
        self.assertTrue(cb.can_execute())
        
        cb.record_failure(CBErrorType.PERMANENT)
        self.assertFalse(cb.can_execute())
    
    def test_recovery(self):
        """测试恢复"""
        cb = CircuitBreaker("test", failure_threshold=2, reset_timeout=60)
        
        # 触发熔断
        cb.record_failure(CBErrorType.PERMANENT)
        cb.record_failure(CBErrorType.PERMANENT)
        self.assertFalse(cb.can_execute())
        
        # 人工重置
        cb.reset()
        self.assertTrue(cb.can_execute())
        
        # 记录成功
        cb.record_success()
        self.assertTrue(cb.can_execute())


class TestErrorClassifier(unittest.TestCase):
    """测试错误分类器"""
    
    def test_transient_error(self):
        """测试临时性错误分类"""
        classifier = ErrorClassifier()
        result = classifier.classify("NETWORK_TIMEOUT")
        
        self.assertEqual(result.error_type.value, "transient")
        self.assertTrue(result.retry)
        self.assertEqual(result.max_retries, 3)
    
    def test_permanent_error(self):
        """测试永久性错误分类"""
        classifier = ErrorClassifier()
        result = classifier.classify("HTTP_401")
        
        self.assertEqual(result.error_type.value, "permanent")
        self.assertFalse(result.retry)
        self.assertTrue(result.escalate)
    
    def test_business_error(self):
        """测试业务错误分类"""
        classifier = ErrorClassifier()
        result = classifier.classify("VALIDATION_FAILED")
        
        self.assertEqual(result.error_type.value, "business")
        self.assertTrue(result.retry)
        self.assertEqual(result.max_retries, 1)
    
    def test_unknown_error(self):
        """测试未知错误分类"""
        classifier = ErrorClassifier()
        result = classifier.classify("UNKNOWN_ERROR_CODE")
        
        self.assertEqual(result.error_type.value, "transient")
        self.assertTrue(result.retry)


class TestGate0(unittest.TestCase):
    """测试Gate 0"""
    
    def test_execute(self):
        """测试执行"""
        gate = Gate0DataSourceValidation()
        
        context = {
            "filing_path": "/path/to/filing",
            "wind_data": {
                "revenue": 100.0,
                "net_income": 10.0,
            },
        }
        
        result = gate.execute(context)
        self.assertIsNotNone(result)
        self.assertEqual(result.gate_num, 0)


# 需要从circuit_breaker导入CircuitState
from ..core.circuit_breaker import CircuitState


class TestFlowComplianceChecker(unittest.TestCase):
    """测试第三方监督"""
    
    def test_check_gate(self):
        """测试Gate合规性检查"""
        flow_def = {
            "gate_0": {
                "name": "数据源验证",
                "preconditions": [],
                "execution_steps": [
                    {"name": "财报获取", "order": 1, "required": True},
                ],
                "pass_criteria": [
                    {"name": "覆盖率", "type": "quantitative", "metric": "coverage", "threshold": 0.95},
                ],
            },
        }
        
        checker = FlowComplianceChecker(flow_def)
        
        # 测试通过场景
        execution_log = {
            "steps": {
                "财报获取": {"executed": True, "order": 1, "result": {"success": True}},
            },
            "metrics": {
                "coverage": 0.98,
            },
        }
        
        result = checker.check_gate(0, execution_log)
        self.assertTrue(result.passed)
        
        # 测试失败场景
        execution_log_fail = {
            "steps": {
                "财报获取": {"executed": False},
            },
            "metrics": {
                "coverage": 0.80,
            },
        }
        
        result_fail = checker.check_gate(0, execution_log_fail)
        self.assertFalse(result_fail.passed)
        self.assertTrue(len(result_fail.failed_checks) > 0)


if __name__ == "__main__":
    unittest.main()
