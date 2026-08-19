"""
Qual流程整合 - WorkflowContext

非侵入式挂载: 在workflow.py中注入审计日志、状态机、监督器
默认只记录不阻断，不影响现有功能
"""

import os
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class QualConfig:
    """Qual流程配置（特性开关）"""
    # 模式: shadow（仅记录）、soft（告警不阻断）、enforce（阻断）
    mode: str = "shadow"
    
    # 是否启用各组件
    enable_state_machine: bool = True
    enable_audit_logger: bool = True
    enable_supervisor: bool = True
    enable_circuit_breaker: bool = True
    enable_monitoring: bool = True
    
    # Gate开关（可单独控制每个Gate是否启用）
    gate_enabled: Dict[int, bool] = field(default_factory=lambda: {
        0: True, 1: True, 2: True, 3: True, 4: True,
        5: True, 6: True, 7: True, 8: True,
    })
    
    # 关键Gate（enforce模式下阻断）
    critical_gates: list = field(default_factory=lambda: [0, 2, 4, 8])


class ComplianceBlockedException(Exception):
    """合规性阻断异常"""
    
    def __init__(self, message: str, compliance_result=None):
        super().__init__(message)
        self.compliance_result = compliance_result


class WorkflowContext:
    """
    工作流上下文（非侵入式挂载）
    
    在workflow.py中注入，提供:
    - 审计日志（哈希链防篡改）
    - 状态机（Gate状态+工作流状态）
    - 第三方监督（规则驱动检查）
    - 熔断器
    - 监控告警
    
    默认行为: 只记录不阻断（shadow模式）
    """
    
    def __init__(self, config: Optional[QualConfig] = None):
        self.config = config or QualConfig()
        self.run_id = None
        self._initialized = False
        
        # 延迟初始化的组件
        self._state_machine = None
        self._audit_logger = None
        self._supervisor = None
        self._circuit_breakers = {}
        self._alert_manager = None
        self._metrics_collector = None
        
        # Step/Gate映射
        self._step_gate_map = {
            "Step 1": 1,
            "Step 1.5": 0,
            "Step 1.6": 1,
            "Step 2": 2,
            "Step 2.5": 2,
            "Step 3": 3,
            "Step 4": 4,
            "Step 4.5": 5,
            "Step 4.5b": 5,
            "Step 4.6": 5,
            "Step 4.7": 4,
            "Step 5": 6,
            "Step 6": 7,
            "Step 7": 7,
        }
    
    def initialize(self, run_id: str):
        """初始化上下文（在workflow开始时调用）"""
        if self._initialized:
            return
        
        self.run_id = run_id
        
        # 初始化状态机
        if self.config.enable_state_machine:
            from .core.state_machine import StateMachine, GateState
            self._state_machine = StateMachine()
            self._state_machine.initialize_gates(list(range(9)))
            logger.info(f"[Qual] 状态机已初始化")
        
        # 初始化审计日志
        if self.config.enable_audit_logger:
            from .core.audit_logger import AuditLogger
            db_path = os.path.expanduser("~/.hermes/data/qual_audit.db")
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            self._audit_logger = AuditLogger(db_path)
            self._audit_logger.log(run_id, None, "workflow_started", {})
            logger.info(f"[Qual] 审计日志已初始化")
        
        # 初始化第三方监督
        if self.config.enable_supervisor:
            from .core.supervisor import FlowComplianceChecker
            self._supervisor = FlowComplianceChecker(self._get_flow_definition())
            logger.info(f"[Qual] 第三方监督已初始化")
        
        # 初始化熔断器
        if self.config.enable_circuit_breaker:
            from .core.circuit_breaker import CircuitBreaker
            for gate_num in range(9):
                self._circuit_breakers[gate_num] = CircuitBreaker(
                    name=f"gate_{gate_num}",
                    failure_threshold=3,
                    reset_timeout=60,
                )
            logger.info(f"[Qual] 熔断器已初始化")
        
        self._initialized = True
    
    def _get_gate_num(self, step_name: str) -> int:
        """根据Step名称获取Gate编号"""
        for prefix, gate_num in self._step_gate_map.items():
            if step_name.startswith(prefix):
                return gate_num
        return -1
    
    def on_step_start(self, step_name: str, step_num: Optional[int] = None):
        """Step开始时的钩子（非侵入式）"""
        if not self._initialized:
            return
        
        # 自动识别Gate编号
        if step_num is None:
            step_num = self._get_gate_num(step_name)
        
        # 记录审计日志
        if self._audit_logger:
            self._audit_logger.log(
                self.run_id, step_num, f"step_started:{step_name}",
                {"step_name": step_name}
            )
        
        # 更新状态机
        if self._state_machine and step_num is not None and step_num >= 0:
            from .core.state_machine import GateState
            self._state_machine.transition_gate(step_num, GateState.RUNNING)
            logger.debug(f"[Qual] Gate {step_num} 状态更新为 RUNNING")
    
    def on_step_end(self, step_name: str, step_num: Optional[int] = None, 
                    passed: bool = True, details: Optional[Dict] = None):
        """Step结束时的钩子（非侵入式）"""
        if not self._initialized:
            return
        
        # 自动识别Gate编号
        if step_num is None:
            step_num = self._get_gate_num(step_name)
        
        # 记录审计日志
        if self._audit_logger:
            self._audit_logger.log(
                self.run_id, step_num, f"step_completed:{step_name}",
                {"step_name": step_name, "passed": passed, "details": details or {}}
            )
        
        # 更新状态机
        if self._state_machine and step_num is not None and step_num >= 0:
            from .core.state_machine import GateState
            new_state = GateState.PASSED if passed else GateState.FAILED
            self._state_machine.transition_gate(step_num, new_state)
            logger.info(f"[Qual] Gate {step_num} 状态更新为 {new_state.value}")
        
        # 第三方监督
        if self._supervisor and step_num is not None and step_num >= 0:
            execution_log = self._build_execution_log(step_name, step_num, passed, details)
            compliance_result = self._supervisor.check_gate(step_num, execution_log)
            
            if not compliance_result.passed:
                logger.warning(f"[Qual] Step {step_name} 合规性检查未通过:")
                for check in compliance_result.failed_checks:
                    logger.warning(f"  - {check.name}: {check.message}")
                
                # 在enforce模式下，关键Gate阻断
                if self.config.mode == "enforce" and step_num in self.config.critical_gates:
                    raise ComplianceBlockedException(
                        f"Step {step_name} 合规性检查未通过，阻断流程",
                        compliance_result=compliance_result,
                    )
    
    def on_error(self, step_name: str, error: Exception, step_num: Optional[int] = None):
        """错误发生时的钩子（非侵入式）"""
        if not self._initialized:
            return
        
        # 自动识别Gate编号
        if step_num is None:
            step_num = self._get_gate_num(step_name)
        
        # 记录审计日志
        if self._audit_logger:
            self._audit_logger.log(
                self.run_id, step_num, f"step_error:{step_name}",
                {"step_name": step_name, "error": str(error), "error_type": type(error).__name__}
            )
        
        # 更新状态机
        if self._state_machine and step_num is not None and step_num >= 0:
            from .core.state_machine import GateState
            self._state_machine.transition_gate(step_num, GateState.FAILED)
            logger.info(f"[Qual] Gate {step_num} 状态更新为 FAILED")
        
        # 错误分类
        from .core.error_classifier import ErrorClassifier
        classifier = ErrorClassifier()
        classification = classifier.classify_from_exception(error)
        logger.info(f"[Qual] 错误分类: {classification.error_type.value}, 可重试: {classification.retry}")
        
        # 熔断器记录
        if self._circuit_breakers and step_num is not None and step_num in self._circuit_breakers:
            from .core.circuit_breaker import ErrorType
            self._circuit_breakers[step_num].record_failure(classification.error_type)
    
    def get_state_summary(self) -> Dict[str, Any]:
        """获取状态摘要"""
        if not self._initialized:
            return {"initialized": False}
        
        summary = {
            "initialized": True,
            "run_id": self.run_id,
            "mode": self.config.mode,
        }
        
        if self._state_machine:
            summary["gate_states"] = {
                num: state.value 
                for num, state in self._state_machine.gate_states.items()
            }
            summary["workflow_state"] = self._state_machine.get_workflow_state().value
        
        return summary
    
    def finalize(self):
        """完成工作流（在workflow结束时调用）"""
        if not self._initialized:
            return
        
        # 记录审计日志
        if self._audit_logger:
            self._audit_logger.log(
                self.run_id, None, "workflow_completed",
                self.get_state_summary()
            )
        
        # 验证审计日志链
        if self._audit_logger:
            chain_valid = self._audit_logger.verify_chain(self.run_id)
            logger.info(f"[Qual] 审计日志链验证: {'通过' if chain_valid else '失败'}")
        
        logger.info(f"[Qual] 工作流完成: {self.get_state_summary()}")
    
    def _build_execution_log(self, step_name: str, step_num: int, 
                             passed: bool, details: Optional[Dict]) -> Dict[str, Any]:
        """构建执行日志（用于第三方监督）"""
        return {
            f"gate_{step_num}": {
                "passed": passed,
                "details": details or {},
            },
            "steps": {
                step_name: {
                    "executed": True,
                    "passed": passed,
                },
            },
        }
    
    def _get_flow_definition(self) -> Dict[str, Any]:
        """获取流程定义（用于第三方监督）"""
        return {
            "gate_0": {
                "name": "数据源验证",
                "preconditions": [],
                "execution_steps": [
                    {"name": "财报获取", "order": 1, "required": True},
                    {"name": "Wind数据获取", "order": 2, "required": True},
                ],
                "pass_criteria": [
                    {"name": "财报文件存在", "type": "condition", "condition": "filing_exists"},
                    {"name": "Wind字段覆盖率", "type": "quantitative", "metric": "wind_coverage", "threshold": 0.95},
                ],
            },
            "gate_1": {
                "name": "类型推断 + 数据提取",
                "preconditions": [{"name": "Gate 0通过", "type": "gate_passed", "gate_num": 0}],
                "execution_steps": [
                    {"name": "推断市场类型", "order": 1, "required": True},
                    {"name": "提取结构化事实", "order": 2, "required": True},
                ],
                "pass_criteria": [
                    {"name": "市场类型正确", "type": "condition", "condition": "market_type_valid"},
                ],
            },
            "gate_2": {
                "name": "数据收集 + 参数提取",
                "preconditions": [{"name": "Gate 1通过", "type": "gate_passed", "gate_num": 1}],
                "execution_steps": [
                    {"name": "收集Wind数据", "order": 1, "required": True},
                    {"name": "提取DCF参数", "order": 2, "required": True},
                ],
                "pass_criteria": [
                    {"name": "FCF非零", "type": "condition", "condition": "fcf_nonzero"},
                    {"name": "WACC范围", "type": "condition", "condition": "wacc_in_range"},
                ],
            },
            "gate_3": {
                "name": "逐章写作",
                "preconditions": [{"name": "Gate 2通过", "type": "gate_passed", "gate_num": 2}],
                "execution_steps": [
                    {"name": "生成大纲", "order": 1, "required": True},
                    {"name": "分章生成", "order": 2, "required": True},
                    {"name": "交叉验证", "order": 3, "required": True},
                ],
                "pass_criteria": [
                    {"name": "章节完整性", "type": "condition", "condition": "chapters_complete"},
                    {"name": "无占位符", "type": "condition", "condition": "no_placeholders"},
                ],
            },
            "gate_4": {
                "name": "审计修复 + 深度审查",
                "preconditions": [{"name": "Gate 3通过", "type": "gate_passed", "gate_num": 3}],
                "execution_steps": [
                    {"name": "形式审查", "order": 1, "required": True},
                    {"name": "实质审查", "order": 2, "required": True},
                    {"name": "修复循环", "order": 3, "required": True},
                ],
                "pass_criteria": [
                    {"name": "格式错误数", "type": "quantitative", "metric": "format_errors", "threshold": 0},
                    {"name": "逻辑矛盾数", "type": "quantitative", "metric": "logic_contradictions", "threshold": 2},
                ],
            },
            "gate_5": {
                "name": "质量增强 + 组件集成",
                "preconditions": [{"name": "Gate 4通过", "type": "gate_passed", "gate_num": 4}],
                "execution_steps": [
                    {"name": "估值计算", "order": 1, "required": True},
                    {"name": "组件集成", "order": 2, "required": True},
                ],
                "pass_criteria": [
                    {"name": "估值计算正确", "type": "condition", "condition": "valuation_correct"},
                    {"name": "组件集成成功", "type": "condition", "condition": "components_integrated"},
                ],
            },
            "gate_6": {
                "name": "综合结论 + 决策章",
                "preconditions": [{"name": "Gate 5通过", "type": "gate_passed", "gate_num": 5}],
                "execution_steps": [
                    {"name": "生成决策章", "order": 1, "required": True},
                    {"name": "生成概览章", "order": 2, "required": True},
                ],
                "pass_criteria": [
                    {"name": "决策章存在", "type": "condition", "condition": "decision_chapter_exists"},
                    {"name": "投资评级有效", "type": "condition", "condition": "rating_valid"},
                ],
            },
            "gate_7": {
                "name": "问题转化 + 记忆存储",
                "preconditions": [{"name": "Gate 6通过", "type": "gate_passed", "gate_num": 6}],
                "execution_steps": [
                    {"name": "问题转化", "order": 1, "required": True},
                    {"name": "记忆存储", "order": 2, "required": True},
                ],
                "pass_criteria": [
                    {"name": "问题转化成功", "type": "condition", "condition": "transformation_success"},
                ],
            },
            "gate_8": {
                "name": "最终验证",
                "preconditions": [{"name": "Gate 7通过", "type": "gate_passed", "gate_num": 7}],
                "execution_steps": [
                    {"name": "最终质量评估", "order": 1, "required": True},
                    {"name": "人工确认", "order": 2, "required": True},
                ],
                "pass_criteria": [
                    {"name": "所有Gate通过", "type": "condition", "condition": "all_gates_passed"},
                    {"name": "人工确认", "type": "condition", "condition": "human_confirmed"},
                ],
            },
        }


# 全局上下文实例（单例）
_workflow_context: Optional[WorkflowContext] = None


def get_workflow_context(config: Optional[QualConfig] = None) -> WorkflowContext:
    """获取工作流上下文（单例）"""
    global _workflow_context
    if _workflow_context is None:
        _workflow_context = WorkflowContext(config)
    return _workflow_context


def reset_workflow_context():
    """重置工作流上下文（用于测试）"""
    global _workflow_context
    _workflow_context = None
