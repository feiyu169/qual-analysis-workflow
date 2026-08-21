"""
Qual流程v8 - 模块入口

架构代次：ARCH_GEN = "v8"（从 v2 单体演进到 Gate 引擎；v3-v7 是单体内部功能迭代，无独立代码）
状态（2026-08-18）：已可运行化——9 个 Gate 灌入 v2-v7 真实组件 + DataAnchor 数据锚点 + Gate8 红队审查。
                推荐作为唯一对外入口（编排+门禁）；workflow.run_analysis 为 legacy 兼容回退。
"""

# 架构代次（三刻度之一：包版本见 finance.__version__，组件代次见 quality.COMPONENT_GEN）
ARCH_GEN = "v8"

# 版本信息（实现细节版本）
__version__ = "8.4.0"

# 核心组件（供workflow.py使用）
from .core.audit_logger import AuditLogger
from .core.circuit_breaker import CircuitBreaker, ErrorType, calculate_backoff
from .core.error_classifier import ErrorClassifier
from .core.state_machine import GateState, StateMachine, WorkflowState
from .core.supervisor import FlowComplianceChecker

# 模式管理
from .mode_manager import ModeManager, QualMode, get_initial_mode

# Step/Gate映射
from .step_gate_mapping import get_gate_for_step, get_gate_name, get_steps_for_gate

# 工作流上下文（非侵入式挂载）
from .workflow_context import QualConfig, WorkflowContext, get_workflow_context

__all__ = [
    # 架构代次
    "ARCH_GEN",
    # 核心组件
    "StateMachine",
    "GateState",
    "WorkflowState",
    "AuditLogger",
    "CircuitBreaker",
    "ErrorType",
    "calculate_backoff",
    "ErrorClassifier",
    "FlowComplianceChecker",

    # 工作流上下文
    "WorkflowContext",
    "QualConfig",
    "get_workflow_context",

    # 模式管理
    "ModeManager",
    "QualMode",
    "get_initial_mode",

    # Step/Gate映射
    "get_gate_for_step",
    "get_steps_for_gate",
    "get_gate_name",
]
