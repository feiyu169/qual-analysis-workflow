"""
状态机模块

实现Gate状态和工作流状态的管理
"""

import logging
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class GateState(Enum):
    """Gate状态"""
    PENDING = "pending"  # 待执行
    RUNNING = "running"  # 执行中
    PASSED = "passed"  # 通过
    FAILED = "failed"  # 失败
    SKIPPED = "skipped"  # 跳过
    WAITING_HUMAN = "waiting_human"  # 等待人工
    ROLLBACK = "rollback"  # 回滚中


class WorkflowState(Enum):
    """工作流状态"""
    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# 合法的状态转换
VALID_GATE_TRANSITIONS = {
    GateState.PENDING: [GateState.RUNNING, GateState.SKIPPED],
    GateState.RUNNING: [GateState.PASSED, GateState.FAILED, GateState.WAITING_HUMAN],
    GateState.PASSED: [],  # 终态
    GateState.FAILED: [GateState.RUNNING, GateState.ROLLBACK],  # 可重试或回滚
    GateState.SKIPPED: [],  # 终态
    GateState.WAITING_HUMAN: [GateState.RUNNING, GateState.FAILED],
    GateState.ROLLBACK: [GateState.PENDING],
}

VALID_WORKFLOW_TRANSITIONS = {
    WorkflowState.INITIALIZED: [WorkflowState.RUNNING, WorkflowState.CANCELLED],
    WorkflowState.RUNNING: [WorkflowState.PAUSED, WorkflowState.COMPLETED, WorkflowState.FAILED],
    WorkflowState.PAUSED: [WorkflowState.RUNNING, WorkflowState.CANCELLED],
    WorkflowState.COMPLETED: [],  # 终态
    WorkflowState.FAILED: [WorkflowState.RUNNING],  # 可重试
    WorkflowState.CANCELLED: [],  # 终态
}


class StateMachine:
    """状态机"""

    def __init__(self):
        self.gate_states: dict[int, GateState] = {}
        self.workflow_state: WorkflowState = WorkflowState.INITIALIZED
        self.state_history: list[dict] = []

    def initialize_gates(self, gate_nums: list[int]):
        """初始化Gate状态"""
        for gate_num in gate_nums:
            self.gate_states[gate_num] = GateState.PENDING
        self._record_state_change("workflow", "initialized", WorkflowState.INITIALIZED.value)

    def transition_gate(self, gate_num: int, new_state: GateState) -> bool:
        """转换Gate状态"""
        if gate_num not in self.gate_states:
            logger.error(f"Gate {gate_num} 不存在")
            return False

        current_state = self.gate_states[gate_num]

        # 检查转换是否合法
        if new_state not in VALID_GATE_TRANSITIONS.get(current_state, []):
            logger.error(f"Gate {gate_num} 状态转换不合法: {current_state.value} -> {new_state.value}")
            return False

        # 执行转换
        self.gate_states[gate_num] = new_state
        self._record_state_change(f"gate_{gate_num}", current_state.value, new_state.value)

        logger.info(f"Gate {gate_num} 状态转换: {current_state.value} -> {new_state.value}")
        return True

    def transition_workflow(self, new_state: WorkflowState) -> bool:
        """转换工作流状态"""
        current_state = self.workflow_state

        # 检查转换是否合法
        if new_state not in VALID_WORKFLOW_TRANSITIONS.get(current_state, []):
            logger.error(f"工作流状态转换不合法: {current_state.value} -> {new_state.value}")
            return False

        # 执行转换
        self.workflow_state = new_state
        self._record_state_change("workflow", current_state.value, new_state.value)

        logger.info(f"工作流状态转换: {current_state.value} -> {new_state.value}")
        return True

    def get_gate_state(self, gate_num: int) -> GateState | None:
        """获取Gate状态"""
        return self.gate_states.get(gate_num)

    def get_workflow_state(self) -> WorkflowState:
        """获取工作流状态"""
        return self.workflow_state

    def is_gate_passed(self, gate_num: int) -> bool:
        """检查Gate是否通过"""
        return self.gate_states.get(gate_num) == GateState.PASSED

    def can_execute_gate(self, gate_num: int, prerequisites: list[int]) -> bool:
        """检查Gate是否可以执行"""
        # 检查前置条件
        for prereq in prerequisites:
            if not self.is_gate_passed(prereq):
                return False

        # 检查Gate状态
        return self.gate_states.get(gate_num) == GateState.PENDING

    def _record_state_change(self, entity: str, old_state: str, new_state: str):
        """记录状态变化"""
        self.state_history.append({
            "entity": entity,
            "old_state": old_state,
            "new_state": new_state,
            "timestamp": datetime.now().isoformat(),
        })

    def get_state_history(self) -> list[dict]:
        """获取状态历史"""
        return self.state_history.copy()
