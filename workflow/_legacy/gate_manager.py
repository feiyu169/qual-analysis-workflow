"""
Gate Manager - Gate-Driven Workflow 核心实现
确保流程严格执行，不可绕过
"""

import asyncio
import yaml
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, asdict
import structlog

try:
    from .state_machine import GateStateMachine, GateStatus, GateState
except ImportError:
    from state_machine import GateStateMachine, GateStatus, GateState

logger = structlog.get_logger()


@dataclass
class GateCriteria:
    """Gate 条件定义"""
    type: str
    description: str
    verification: Optional[str] = None
    command: Optional[str] = None
    expected: Optional[Any] = None


@dataclass
class GateConfig:
    """Gate 配置"""
    name: str
    phase: int
    entry_criteria: List[GateCriteria]
    exit_criteria: List[GateCriteria]
    depends_on: List[str] = None  # 前置 Gate ID 列表
    timeout: int = 3600  # 默认1小时
    max_retries: int = 3


class GateEntryError(Exception):
    """准入条件不满足"""
    pass


class GateExitError(Exception):
    """准出条件不满足"""
    pass


class GateMaxRetriesError(Exception):
    """超过最大重试次数"""
    pass


class GateTimeoutError(Exception):
    """Gate 超时"""
    pass


class GateManager:
    """Gate 执行引擎 - 状态机实现"""
    
    def __init__(self, config_path: str = None, db_path: str = None):
        self.gates: Dict[str, GateConfig] = {}
        self.handlers: Dict[str, Callable] = {}
        self.state_machine = GateStateMachine(db_path)
        self.verification_engine = None
        self._lock = asyncio.Lock()  # 并发控制锁
        
        if config_path:
            self._load_config(config_path)
    
    def _load_config(self, config_path: str):
        """加载 Gate 配置"""
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        for gate_id, gate_config in config.get('gates', {}).items():
            entry_criteria = [
                GateCriteria(**c) for c in gate_config.get('entry_criteria', [])
            ]
            exit_criteria = [
                GateCriteria(**c) for c in gate_config.get('exit_criteria', [])
            ]
            
            self.gates[gate_id] = GateConfig(
                name=gate_config['name'],
                phase=gate_config['phase'],
                entry_criteria=entry_criteria,
                exit_criteria=exit_criteria,
                depends_on=gate_config.get('depends_on', []),
                timeout=gate_config.get('timeout', 3600),
                max_retries=gate_config.get('max_retries', 3)
            )
            
            # 添加到状态机
            self.state_machine.add_gate(gate_id)
        
        logger.info("config_loaded", gate_count=len(self.gates))
    
    def set_verification_engine(self, engine):
        """设置验证引擎"""
        self.verification_engine = engine
    
    def register_handler(self, gate_id: str, handler: Callable):
        """注册 Gate 处理器"""
        self.handlers[gate_id] = handler
        logger.info("handler_registered", gate_id=gate_id)
    
    def check_entry_criteria(self, gate_id: str) -> List[bool]:
        """检查准入条件 - 不可绕过"""
        gate_config = self.gates.get(gate_id)
        if not gate_config:
            raise ValueError(f"Gate {gate_id} not found")
        
        results = []
        for criteria in gate_config.entry_criteria:
            result = self._verify_criteria(criteria, result=None, gate_id=gate_id)
            results.append(result)
            
            if not result:
                logger.warning(
                    "entry_criteria_failed",
                    gate_id=gate_id,
                    criteria=criteria.description
                )
                raise GateEntryError(
                    f"准入条件不满足: {criteria.description}"
                )
        
        logger.info("entry_criteria_passed", gate_id=gate_id)
        return results
    
    def verify_exit_criteria(self, gate_id: str, result: Any) -> List[bool]:
        """验证准出条件 - 不可绕过"""
        gate_config = self.gates.get(gate_id)
        if not gate_config:
            raise ValueError(f"Gate {gate_id} not found")
        
        results = []
        for criteria in gate_config.exit_criteria:
            criteria_result = self._verify_criteria(criteria, result, gate_id=gate_id)
            results.append(criteria_result)
            
            if not criteria_result:
                logger.warning(
                    "exit_criteria_failed",
                    gate_id=gate_id,
                    criteria=criteria.description
                )
                raise GateExitError(
                    f"准出条件不满足: {criteria.description}"
                )
        
        logger.info("exit_criteria_passed", gate_id=gate_id)
        return results
    
    def _get_predecessor_gate(self, gate_id: str, criteria_type: str) -> Optional[str]:
        """从配置中获取前驱 Gate ID
        
        优先级：
        1. 从 GateConfig.depends_on 获取（推荐）
        2. 从硬编码映射获取（向后兼容）
        """
        # 优先从 depends_on 获取
        gate_config = self.gates.get(gate_id)
        if gate_config and gate_config.depends_on:
            # depends_on 列表中最后一个即为直接前驱
            return gate_config.depends_on[-1]
        
        # 向后兼容：硬编码映射
        PREDECESSOR_MAP = {
            # Phase 0
            "user_request": None,  # 无前驱
            "document_generated": "gate_0_1",
            "security_requirements": "gate_0_2",
            "requirements_confirmed": "gate_0_3",
            # Phase 1
            "architecture_document": "gate_1_1",
            "api_definition": "gate_1_2",
            "detailed_design": "gate_1_3",
            "design_approved": "gate_1_3",
            # Phase 2
            "code_completed": "gate_1_3",
            "review_passed": "gate_2_1",
            "code_reviewed": "gate_2_1",
            # Phase 3
            "integration_test_passed": "gate_2_2",
            "security_test_passed": "gate_2_2",
            "acceptance_passed": "gate_3_1",
            "deployment_ready": "gate_3_3",
            # Phase 4
            "deployment_success": "gate_4_1",
            "health_check": "gate_4_2",
            "monitoring_configured": "gate_4_2",
            "monitoring_ready": "gate_4_3",
            # Phase 5
            "monitoring_normal": "gate_4_3",
            "feedback_collected": "gate_5_1",
        }
        return PREDECESSOR_MAP.get(criteria_type)
    
    def _verify_criteria(self, criteria: GateCriteria, result: Any = None, gate_id: str = None) -> bool:
        """验证条件 - 统一验证逻辑
        
        入口条件（result is None）：检查前驱 Gate 状态
        出口条件（result is not None）：优先调用验证引擎，否则按类型处理
        """
        # 类型分类
        command_types = ["unit_test_passed", "tdd_evidence", "static_analysis", 
                         "sast_scan", "dependency_scan", "integration_test_passed",
                         "dast_scan", "user_acceptance"]
        document_types = ["document_generated", "review_passed", "requirements_confirmed",
                          "architecture_document", "threat_model", "api_definition",
                          "detailed_design", "code_completed", "security_requirements"]
        deploy_types = ["deployment_checklist", "iac_security_audit", "key_rotation",
                        "health_check", "monitoring_configured", "feedback_collected",
                        "monitoring_normal", "deployment_success", "deployment_ready",
                        "acceptance_passed", "security_test_passed", "monitoring_ready"]
        review_types = ["automated_review", "manual_review", "review_checklist"]
        
        # 入口条件：检查前驱 Gate 状态
        if result is None:
            if criteria.type == "user_request":
                return True
            
            if criteria.type in document_types or criteria.type in deploy_types or criteria.type in review_types:
                predecessor = self._get_predecessor_gate(gate_id, criteria.type)
                if predecessor:
                    try:
                        status = self.state_machine.get_status(predecessor)
                        return status == GateStatus.PASSED
                    except ValueError:
                        logger.warning("predecessor_not_registered", 
                                       predecessor=predecessor, gate_id=gate_id)
                        return False
                logger.warning("no_predecessor_mapping", 
                               criteria_type=criteria.type, gate_id=gate_id)
                return False
            
            # 其他类型入口条件
            return True
        
        # 出口条件：优先调用验证引擎
        if criteria.verification:
            if not self.verification_engine:
                raise ValueError(
                    f"验证引擎未设置，无法执行 {criteria.verification} 级别验证"
                )
            level = criteria.verification
            verification_result = self.verification_engine.verify(
                level=level,
                command=criteria.command,
                expected=criteria.expected
            )
            return verification_result.passed
        
        # 无 verification 配置时，按类型处理
        if criteria.type in command_types:
            if not self.verification_engine:
                raise ValueError("验证引擎未设置，无法执行验证")
            level = criteria.verification or "L1"
            verification_result = self.verification_engine.verify(
                level=level,
                command=criteria.command,
                expected=criteria.expected
            )
            return verification_result.passed
        
        elif criteria.type in document_types or criteria.type in deploy_types or criteria.type in review_types:
            if isinstance(result, dict):
                if "completed" in result:
                    return result["completed"]
                if "passed" in result:
                    return result["passed"]
                return False
            return bool(result)
        
        elif criteria.type == "data_desensitization":
            if isinstance(result, dict):
                return result.get("desensitized", False)
            return False
        
        else:
            logger.warning("unknown_criteria_type", type=criteria.type, description=criteria.description)
            raise ValueError(f"未知的验证条件类型: {criteria.type}")
    
    async def execute_gate(self, gate_id: str, task_func: Callable = None) -> Any:
        """执行 Gate - 不可绕过（线程安全）"""
        async with self._lock:
            return await self._execute_gate_impl(gate_id, task_func)
    
    async def _execute_gate_impl(self, gate_id: str, task_func: Callable = None) -> Any:
        """Gate 执行实现"""
        gate_config = self.gates.get(gate_id)
        if not gate_config:
            raise ValueError(f"Gate {gate_id} not found")
        
        # 检查前置 Gate 依赖（硬性约束）
        for dep in gate_config.depends_on or []:
            # 验证依赖 Gate 存在
            if dep not in self.gates:
                raise ValueError(f"依赖的 Gate {dep} 不存在于配置中")
            try:
                dep_status = self.state_machine.get_status(dep)
            except ValueError:
                raise GateEntryError(f"依赖的 Gate {dep} 未注册到状态机")
            if dep_status != GateStatus.PASSED:
                raise GateEntryError(
                    f"前置 Gate {dep} 未完成，当前状态: {dep_status.value}"
                )
        
        # 检查当前状态
        current_status = self.state_machine.get_status(gate_id)
        if current_status == GateStatus.IN_PROGRESS:
            # 检查是否超时，超时则允许重试
            state = self.state_machine.get_state(gate_id)
            if state.entry_time:
                from datetime import timedelta
                entry_time = datetime.fromisoformat(state.entry_time)
                # 确保 entry_time 是 aware 对象
                if entry_time.tzinfo is None:
                    entry_time = entry_time.replace(tzinfo=timezone.utc)
                timeout = timedelta(seconds=gate_config.timeout)
                if datetime.now(timezone.utc) - entry_time > timeout:
                    logger.warning("gate_timeout_detected", gate_id=gate_id)
                    self.state_machine.transition(gate_id, GateStatus.TIMEOUT)
                    # 超时后重新获取状态
                    current_status = GateStatus.TIMEOUT
                else:
                    raise ValueError(
                        f"Gate {gate_id} is in IN_PROGRESS state and not yet timed out"
                    )
            else:
                raise ValueError(
                    f"Gate {gate_id} is in IN_PROGRESS state with no entry time"
                )
        
        if current_status not in [GateStatus.PENDING, GateStatus.FAILED, GateStatus.TIMEOUT]:
            raise ValueError(
                f"Gate {gate_id} is not in a valid state for execution, current: {current_status.value}"
            )
        
        # 检查准入条件
        self.check_entry_criteria(gate_id)
        
        # 转移到进行中状态
        self.state_machine.transition(gate_id, GateStatus.IN_PROGRESS)
        
        try:
            # 执行任务
            if task_func:
                if asyncio.iscoroutinefunction(task_func):
                    result = await task_func()
                else:
                    result = task_func()
            else:
                handler = self.handlers.get(gate_id)
                if handler:
                    if asyncio.iscoroutinefunction(handler):
                        result = await handler()
                    else:
                        result = handler()
                else:
                    raise ValueError(
                        f"Gate {gate_id} 没有注册处理器且未提供 task_func"
                    )
            
            # 验证准出条件
            self.verify_exit_criteria(gate_id, result)
            
            # 转移到通过状态
            self.state_machine.transition(gate_id, GateStatus.PASSED)
            
            logger.info("gate_executed", gate_id=gate_id, status="passed")
            return result
            
        except Exception as e:
            # 记录失败
            error_msg = str(e)
            self.state_machine.transition(gate_id, GateStatus.FAILED, error=error_msg)
            
            # 处理失败
            return self.handle_failure(gate_id, e)
    
    def handle_failure(self, gate_id: str, error: Exception) -> Dict:
        """失败处理 - 只检查重试次数，不重复转移
        
        前置条件：execute_gate 已完成 IN_PROGRESS → FAILED 转移
        """
        # 获取最新状态（不重复转移）
        state = self.state_machine.get_state(gate_id)
        gate_config = self.gates.get(gate_id)
        
        logger.warning(
            "gate_failed",
            gate_id=gate_id,
            error=str(error),
            failure_count=state.failure_count
        )
        
        # 检查重试次数
        if state.failure_count >= gate_config.max_retries:
            # 升级处理
            self.escalate_to_owner(gate_id)
            raise GateMaxRetriesError(
                f"Gate {gate_id} 连续失败 {state.failure_count} 次，已升级"
            )
        
        # 允许重试
        return {
            "retry": True,
            "failure_count": state.failure_count,
            "error": str(error)
        }
    
    def escalate_to_owner(self, gate_id: str):
        """升级到负责人"""
        current_status = self.state_machine.get_status(gate_id)
        
        if current_status == GateStatus.FAILED:
            # 从 FAILED 直接升级到 ESCALATED
            self.state_machine.transition(gate_id, GateStatus.ESCALATED)
        elif current_status != GateStatus.ESCALATED:
            # 其他状态先转到 FAILED 再升级
            self.state_machine.transition(gate_id, GateStatus.FAILED)
            self.state_machine.transition(gate_id, GateStatus.ESCALATED)
        
        logger.error("gate_escalated", gate_id=gate_id)
        # TODO: 这里应该发送通知给负责人
    
    async def check_timeout(self, gate_id: str):
        """检查超时"""
        state = self.state_machine.get_state(gate_id)
        gate_config = self.gates.get(gate_id)
        
        if state.status != GateStatus.IN_PROGRESS:
            return
        
        if not state.entry_time:
            return
        
        entry_time = datetime.fromisoformat(state.entry_time)
        # 确保 entry_time 是 aware 对象
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=timezone.utc)
        timeout = timedelta(seconds=gate_config.timeout)
        
        if datetime.now(timezone.utc) - entry_time > timeout:
            self.state_machine.transition(gate_id, GateStatus.TIMEOUT)
            logger.error("gate_timeout", gate_id=gate_id)
            raise GateTimeoutError(f"Gate {gate_id} 超时")
    
    async def execute_from(self, gate_id: str) -> Any:
        """从指定 Gate 开始执行"""
        # 检查前置 Gate 是否完成
        gate_config = self.gates.get(gate_id)
        if not gate_config:
            raise ValueError(f"Gate {gate_id} not found")
        
        # 执行当前 Gate
        return await self.execute_gate(gate_id)
    
    def get_gate_status(self, gate_id: str) -> GateStatus:
        """获取 Gate 状态"""
        return self.state_machine.get_status(gate_id)
    
    def get_all_statuses(self) -> Dict[str, GateStatus]:
        """获取所有 Gate 状态"""
        return {
            gate_id: self.state_machine.get_status(gate_id)
            for gate_id in self.gates.keys()
        }
    
    def reset_gate(self, gate_id: str, force: bool = False):
        """重置 Gate"""
        self.state_machine.reset_gate(gate_id, force=force)
        logger.info("gate_reset", gate_id=gate_id, force=force)
    
    def get_history(self) -> List[Dict]:
        """获取执行历史"""
        states = self.state_machine.get_all_states()
        return [
            {
                "gate_id": state.gate_id,
                "status": state.status.value,
                "entry_time": state.entry_time,
                "exit_time": state.exit_time,
                "failure_count": state.failure_count,
                "last_error": state.last_error
            }
            for state in states.values()
        ]
