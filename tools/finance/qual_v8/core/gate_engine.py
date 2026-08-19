"""
Gate引擎模块

实现Gate的执行、检查和管理
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    """Gate执行结果"""
    gate_num: int
    passed: bool
    score: float
    details: Dict[str, Any]
    errors: List[str]
    warnings: List[str]
    execution_time: float  # 秒
    timestamp: str


@dataclass
class GateSpec:
    """Gate规格"""
    gate_num: int
    name: str
    description: str
    prerequisites: List[int]  # 前置Gate
    timeout: int  # 超时时间（秒）
    max_retries: int  # 最大重试次数
    pass_criteria: Dict[str, Any]  # 通过标准


class GateBase(ABC):
    """Gate基类"""
    
    def __init__(self, spec: GateSpec):
        self.spec = spec
        self.result: Optional[GateResult] = None
        self.retry_count: int = 0
    
    @abstractmethod
    def execute(self, context: Dict[str, Any]) -> GateResult:
        """执行Gate"""
        pass
    
    @abstractmethod
    def check_criteria(self, context: Dict[str, Any]) -> bool:
        """检查通过标准"""
        pass
    
    def can_retry(self) -> bool:
        """检查是否可以重试"""
        return self.retry_count < self.spec.max_retries
    
    def increment_retry(self):
        """增加重试次数"""
        self.retry_count += 1


class GateEngine:
    """Gate引擎"""
    
    def __init__(self):
        self.gates: Dict[int, GateBase] = {}
        self.results: Dict[int, GateResult] = {}
    
    def register_gate(self, gate: GateBase):
        """注册Gate"""
        self.gates[gate.spec.gate_num] = gate
    
    def execute_gate(self, gate_num: int, context: Dict[str, Any]) -> GateResult:
        """执行Gate"""
        if gate_num not in self.gates:
            raise ValueError(f"Gate {gate_num} 未注册")
        
        gate = self.gates[gate_num]
        
        # 检查前置条件
        for prereq in gate.spec.prerequisites:
            if prereq not in self.results or not self.results[prereq].passed:
                return GateResult(
                    gate_num=gate_num,
                    passed=False,
                    score=0.0,
                    details={"error": f"前置Gate {prereq} 未通过"},
                    errors=[f"前置Gate {prereq} 未通过"],
                    warnings=[],
                    execution_time=0.0,
                    timestamp=datetime.now().isoformat(),
                )
        
        # 执行Gate
        start_time = datetime.now()
        result = gate.execute(context)
        end_time = datetime.now()
        
        result.execution_time = (end_time - start_time).total_seconds()
        result.timestamp = datetime.now().isoformat()
        
        # 保存结果
        self.results[gate_num] = result
        
        return result
    
    def get_result(self, gate_num: int) -> Optional[GateResult]:
        """获取Gate结果"""
        return self.results.get(gate_num)
    
    def all_gates_passed(self) -> bool:
        """检查所有Gate是否通过"""
        return all(result.passed for result in self.results.values())
    
    def get_failed_gates(self) -> List[int]:
        """获取失败的Gate"""
        return [gate_num for gate_num, result in self.results.items() if not result.passed]
