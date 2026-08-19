"""
变更管理器 - 管理需求变更和回退
基于 Hermes Agent 编程 Workflow 方案 V2.0
"""

from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
import structlog

from .gate_manager import GateManager
from .state_machine import GateStatus

logger = structlog.get_logger()


@dataclass
class ChangeRequest:
    """变更请求"""
    id: str
    description: str
    reason: str
    affected_areas: List[str]
    priority: str  # low, medium, high, critical
    requested_by: str
    requested_at: str


@dataclass
class ChangeEvaluation:
    """变更评估"""
    change_request: ChangeRequest
    affected_gates: List[str]
    impact: str  # low, medium, high
    rollback_gate: str
    estimated_effort: str


@dataclass
class ChangeRecord:
    """变更记录"""
    change_request: ChangeRequest
    evaluation: ChangeEvaluation
    executed_at: str
    executed_by: str
    result: str


class ChangeManager:
    """变更管理器"""
    
    def __init__(self, gate_manager: GateManager):
        self.gate_manager = gate_manager
        self.change_history: List[ChangeRecord] = []
    
    def evaluate_change(self, change_request: ChangeRequest) -> ChangeEvaluation:
        """评估变更影响"""
        # 识别影响的 Gate
        affected_gates = self._identify_affected_gates(change_request)
        
        # 评估影响范围
        impact = self._assess_impact(affected_gates)
        
        # 确定回退 Gate
        rollback_gate = self._determine_rollback_gate(affected_gates)
        
        # 估算工作量
        estimated_effort = self._estimate_effort(affected_gates, impact)
        
        evaluation = ChangeEvaluation(
            change_request=change_request,
            affected_gates=affected_gates,
            impact=impact,
            rollback_gate=rollback_gate,
            estimated_effort=estimated_effort
        )
        
        logger.info(
            "change_evaluated",
            change_id=change_request.id,
            affected_gates=affected_gates,
            impact=impact,
            rollback_gate=rollback_gate
        )
        
        return evaluation
    
    def execute_rollback(self, change_request: ChangeRequest) -> ChangeRecord:
        """执行回退"""
        # 评估变更
        evaluation = self.evaluate_change(change_request)
        
        # 回退到指定 Gate
        rollback_gate = evaluation.rollback_gate
        self._rollback_to(rollback_gate)
        
        # 记录变更历史
        record = ChangeRecord(
            change_request=change_request,
            evaluation=evaluation,
            executed_at=datetime.now().isoformat(),
            executed_by=change_request.requested_by,
            result="rollback_executed"
        )
        
        self.change_history.append(record)
        
        logger.info(
            "change_executed",
            change_id=change_request.id,
            rollback_gate=rollback_gate
        )
        
        # 重新走 Gate 流程
        self._re_execute_from(rollback_gate)
        
        return record
    
    def _identify_affected_gates(self, change_request: ChangeRequest) -> List[str]:
        """识别影响的 Gate"""
        affected_gates = []
        
        # 根据变更影响区域识别 Gate
        for area in change_request.affected_areas:
            if area == "requirements":
                affected_gates.extend(["gate_0_1", "gate_0_2", "gate_0_3"])
            elif area == "design":
                affected_gates.extend(["gate_1_1", "gate_1_2", "gate_1_3"])
            elif area == "implementation":
                affected_gates.extend(["gate_2_1", "gate_2_2"])
            elif area == "testing":
                affected_gates.extend(["gate_3_1", "gate_3_2", "gate_3_3"])
            elif area == "deployment":
                affected_gates.extend(["gate_4_1", "gate_4_2", "gate_4_3"])
        
        # 去重
        return list(set(affected_gates))
    
    def _assess_impact(self, affected_gates: List[str]) -> str:
        """评估影响范围"""
        if len(affected_gates) > 6:
            return "high"
        elif len(affected_gates) > 3:
            return "medium"
        else:
            return "low"
    
    def _determine_rollback_gate(self, affected_gates: List[str]) -> str:
        """确定回退 Gate"""
        # 找到最早的受影响 Gate
        gate_order = [
            "gate_0_1", "gate_0_2", "gate_0_3",
            "gate_1_1", "gate_1_2", "gate_1_3",
            "gate_2_1", "gate_2_2",
            "gate_3_1", "gate_3_2", "gate_3_3",
            "gate_4_1", "gate_4_2", "gate_4_3",
            "gate_5_1", "gate_5_2"
        ]
        
        for gate in gate_order:
            if gate in affected_gates:
                return gate
        
        return affected_gates[0] if affected_gates else "gate_0_1"
    
    def _estimate_effort(self, affected_gates: List[str], impact: str) -> str:
        """估算工作量"""
        base_effort = len(affected_gates) * 2  # 每个 Gate 2 小时
        
        if impact == "high":
            base_effort *= 2
        elif impact == "medium":
            base_effort *= 1.5
        
        return f"{int(base_effort)} 小时"
    
    def _rollback_to(self, gate_id: str):
        """回退到指定 Gate"""
        # 重置所有后续 Gate
        gate_order = [
            "gate_0_1", "gate_0_2", "gate_0_3",
            "gate_1_1", "gate_1_2", "gate_1_3",
            "gate_2_1", "gate_2_2",
            "gate_3_1", "gate_3_2", "gate_3_3",
            "gate_4_1", "gate_4_2", "gate_4_3",
            "gate_5_1", "gate_5_2"
        ]
        
        target_index = gate_order.index(gate_id) if gate_id in gate_order else 0
        
        for i in range(target_index, len(gate_order)):
            gate = gate_order[i]
            try:
                self.gate_manager.reset_gate(gate)
            except:
                pass
        
        logger.info("rollback_completed", gate_id=gate_id)
    
    def _re_execute_from(self, gate_id: str):
        """从指定 Gate 重新执行"""
        # 这里应该触发重新执行流程
        # 简化实现
        logger.info("re_execution_triggered", gate_id=gate_id)
    
    def get_change_history(self) -> List[Dict]:
        """获取变更历史"""
        return [
            {
                "change_id": record.change_request.id,
                "description": record.change_request.description,
                "affected_gates": record.evaluation.affected_gates,
                "impact": record.evaluation.impact,
                "rollback_gate": record.evaluation.rollback_gate,
                "executed_at": record.executed_at,
                "executed_by": record.executed_by,
                "result": record.result
            }
            for record in self.change_history
        ]
