"""
异步 Gate Manager - 生产级实现
"""
import asyncio
import yaml
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, asdict
import structlog

from async_state_machine import AsyncGateStateMachine, GateStatus, GateState

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
    depends_on: List[str] = None
    timeout: int = 3600
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


class AsyncGateManager:
    """异步 Gate 执行引擎
    
    特性：
    - 细粒度锁（Gate 级别）
    - 超时任务取消
    - 异步状态机
    - 自动超时监控
    """
    
    def __init__(self, config_path: str = None, db_path: str = None):
        self.gates: Dict[str, GateConfig] = {}
        self.handlers: Dict[str, Callable] = {}
        self.state_machine = AsyncGateStateMachine(db_path)
        self.verification_engine = None
        self._gate_locks: Dict[str, asyncio.Lock] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._timeout_task: Optional[asyncio.Task] = None
        self._config_path = config_path
    
    async def initialize(self):
        """异步初始化"""
        await self.state_machine.initialize()
        if self._config_path:
            await self._load_config(self._config_path)
        
        # 恢复超时 Gate
        await self._recover_timeout_gates()
    
    async def close(self):
        """关闭"""
        await self.stop_timeout_monitor()
        await self.state_machine.close()
    
    def _get_gate_lock(self, gate_id: str) -> asyncio.Lock:
        """获取 Gate 级别的锁"""
        if gate_id not in self._gate_locks:
            self._gate_locks[gate_id] = asyncio.Lock()
        return self._gate_locks[gate_id]
    
    async def _load_config(self, config_path: str):
        """异步加载配置"""
        loop = asyncio.get_event_loop()
        config = await loop.run_in_executor(None, self._load_config_sync, config_path)
        
        for gate_id, gate_config in config.get('gates', {}).items():
            entry_criteria = [GateCriteria(**c) for c in gate_config.get('entry_criteria', [])]
            exit_criteria = [GateCriteria(**c) for c in gate_config.get('exit_criteria', [])]
            
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
            await self.state_machine.add_gate(gate_id)
        
        logger.info("config_loaded", gate_count=len(self.gates))
    
    def _load_config_sync(self, config_path: str) -> dict:
        """同步加载配置（在线程池中执行）"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    async def _recover_timeout_gates(self):
        """恢复超时 Gate"""
        all_states = await self.state_machine.get_all_states()
        for gate_id, state in all_states.items():
            if state.status == GateStatus.IN_PROGRESS:
                gate_config = self.gates.get(gate_id)
                if gate_config and state.entry_time:
                    entry_time = datetime.fromisoformat(state.entry_time)
                    if entry_time.tzinfo is None:
                        entry_time = entry_time.replace(tzinfo=timezone.utc)
                    timeout = timedelta(seconds=gate_config.timeout)
                    if datetime.now(timezone.utc) - entry_time > timeout:
                        await self.state_machine.transition(gate_id, GateStatus.TIMEOUT)
                        logger.info("gate_recovered_timeout", gate_id=gate_id)
    
    def set_verification_engine(self, engine):
        """设置验证引擎"""
        self.verification_engine = engine
    
    def register_handler(self, gate_id: str, handler: Callable):
        """注册 Gate 处理器"""
        self.handlers[gate_id] = handler
        logger.info("handler_registered", gate_id=gate_id)
    
    async def get_gate_status(self, gate_id: str) -> GateStatus:
        """获取 Gate 状态"""
        return await self.state_machine.get_status(gate_id)
    
    async def get_all_statuses(self) -> Dict[str, GateStatus]:
        """获取所有 Gate 状态"""
        result = {}
        for gate_id in self.gates.keys():
            result[gate_id] = await self.state_machine.get_status(gate_id)
        return result
    
    async def get_history(self) -> List[Dict]:
        """获取执行历史"""
        states = await self.state_machine.get_all_states()
        return [
            {
                "gate_id": state.gate_id,
                "status": state.status.value,
                "entry_time": state.entry_time,
                "exit_time": state.exit_time,
                "failure_count": state.failure_count,
                "timeout_count": state.timeout_count,
                "last_error": state.last_error
            }
            for state in states.values()
        ]
    
    async def check_entry_criteria(self, gate_id: str) -> List[bool]:
        """检查准入条件"""
        gate_config = self.gates.get(gate_id)
        if not gate_config:
            raise ValueError(f"Gate {gate_id} not found")
        
        results = []
        for criteria in gate_config.entry_criteria:
            result = await self._verify_criteria(criteria, result=None, gate_id=gate_id)
            results.append(result)
            
            if not result:
                logger.warning("entry_criteria_failed", gate_id=gate_id, criteria=criteria.description)
                raise GateEntryError(f"准入条件不满足: {criteria.description}")
        
        logger.info("entry_criteria_passed", gate_id=gate_id)
        return results
    
    async def verify_exit_criteria(self, gate_id: str, result: Any) -> List[bool]:
        """验证准出条件"""
        gate_config = self.gates.get(gate_id)
        if not gate_config:
            raise ValueError(f"Gate {gate_id} not found")
        
        results = []
        for criteria in gate_config.exit_criteria:
            criteria_result = await self._verify_criteria(criteria, result, gate_id=gate_id)
            results.append(criteria_result)
            
            if not criteria_result:
                logger.warning("exit_criteria_failed", gate_id=gate_id, criteria=criteria.description)
                raise GateExitError(f"准出条件不满足: {criteria.description}")
        
        logger.info("exit_criteria_passed", gate_id=gate_id)
        return results
    
    async def _verify_criteria(self, criteria: GateCriteria, result: Any = None, gate_id: str = None) -> bool:
        """验证条件"""
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
        
        # 入口条件
        if result is None:
            if criteria.type == "user_request":
                return True
            
            if criteria.type in document_types or criteria.type in deploy_types or criteria.type in review_types:
                predecessor = self._get_predecessor_gate(gate_id, criteria.type)
                if predecessor:
                    try:
                        status = await self.state_machine.get_status(predecessor)
                        return status == GateStatus.PASSED
                    except ValueError:
                        logger.warning("predecessor_not_registered", predecessor=predecessor, gate_id=gate_id)
                        return False
                logger.warning("no_predecessor_mapping", criteria_type=criteria.type, gate_id=gate_id)
                return False
            
            return True
        
        # 出口条件：优先调用验证引擎
        if criteria.verification:
            if not self.verification_engine:
                raise ValueError(f"验证引擎未设置，无法执行 {criteria.verification} 级别验证")
            level = criteria.verification
            verification_result = self.verification_engine.verify(
                level=level, command=criteria.command, expected=criteria.expected
            )
            return verification_result.passed
        
        # 无 verification 配置时，按类型处理
        if criteria.type in command_types:
            if not self.verification_engine:
                raise ValueError("验证引擎未设置，无法执行验证")
            level = criteria.verification or "L1"
            verification_result = self.verification_engine.verify(
                level=level, command=criteria.command, expected=criteria.expected
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
    
    def _get_predecessor_gate(self, gate_id: str, criteria_type: str) -> Optional[str]:
        """获取前驱 Gate"""
        gate_config = self.gates.get(gate_id)
        if gate_config and gate_config.depends_on:
            return gate_config.depends_on[-1]
        return None
    
    async def execute_gate(self, gate_id: str, task_func: Callable = None) -> Any:
        """执行 Gate（细粒度锁，支持超时取消）"""
        gate_config = self.gates.get(gate_id)
        if not gate_config:
            raise ValueError(f"Gate {gate_id} not found")
        
        # 检查依赖（无锁）
        for dep in gate_config.depends_on or []:
            if dep not in self.gates:
                raise ValueError(f"依赖的 Gate {dep} 不存在于配置中")
            try:
                dep_status = await self.state_machine.get_status(dep)
            except ValueError:
                raise GateEntryError(f"依赖的 Gate {dep} 未注册到状态机")
            if dep_status != GateStatus.PASSED:
                raise GateEntryError(f"前置 Gate {dep} 未完成，当前状态: {dep_status.value}")
        
        # 获取 Gate 级别锁
        gate_lock = self._get_gate_lock(gate_id)
        async with gate_lock:
            # 检查当前状态
            current_status = await self.state_machine.get_status(gate_id)
            if current_status not in [GateStatus.PENDING, GateStatus.FAILED, GateStatus.TIMEOUT]:
                raise ValueError(f"Gate {gate_id} 不可执行，当前状态: {current_status.value}")
            
            # 检查准入条件
            await self.check_entry_criteria(gate_id)
            
            # 转移到进行中状态
            await self.state_machine.transition(gate_id, GateStatus.IN_PROGRESS)
            
            # 创建任务
            async def _execute():
                if task_func:
                    if asyncio.iscoroutinefunction(task_func):
                        return await task_func()
                    else:
                        return task_func()
                else:
                    handler = self.handlers.get(gate_id)
                    if handler:
                        if asyncio.iscoroutinefunction(handler):
                            return await handler()
                        else:
                            return handler()
                    else:
                        raise ValueError(f"Gate {gate_id} 没有注册处理器")
            
            task = asyncio.create_task(_execute())
            self._running_tasks[gate_id] = task
            
            try:
                # 等待任务完成或超时
                result = await asyncio.wait_for(task, timeout=gate_config.timeout)
                
                # 验证准出条件
                await self.verify_exit_criteria(gate_id, result)
                
                # 转移到通过状态
                await self.state_machine.transition(gate_id, GateStatus.PASSED)
                
                logger.info("gate_executed", gate_id=gate_id, status="passed")
                return result
                
            except asyncio.TimeoutError:
                # 超时：取消任务
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                
                # 处理超时
                await self._handle_timeout(gate_id)
                raise GateTimeoutError(f"Gate {gate_id} 超时")
                
            except Exception as e:
                # 任务失败
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                # 记录失败
                await self.state_machine.transition(gate_id, GateStatus.FAILED, error=str(e))
                
                # 处理失败
                await self._handle_failure(gate_id, e)
                raise
                
            finally:
                self._running_tasks.pop(gate_id, None)
    
    async def _handle_timeout(self, gate_id: str) -> None:
        """处理超时（私有方法，在锁内调用）
        
        流程：先转移 TIMEOUT（计数+1），再检查是否超过限制
        """
        gate_config = self.gates.get(gate_id)
        
        # 先转移到 TIMEOUT（transition 会自动递增 timeout_count）
        await self.state_machine.transition(gate_id, GateStatus.TIMEOUT)
        
        # 再获取最新状态检查超时次数
        state = await self.state_machine.get_state(gate_id)
        
        logger.warning("gate_timeout_detected", 
                       gate_id=gate_id, 
                       timeout_count=state.timeout_count)
        
        # 检查超时次数（转移后检查，确保计数准确）
        if state.timeout_count >= gate_config.max_retries:
            # 升级处理：TIMEOUT → ESCALATED
            await self._escalate_to_owner(gate_id)
            raise GateMaxRetriesError(f"Gate {gate_id} 超时 {state.timeout_count} 次，已升级")
    
    async def _handle_failure(self, gate_id: str, error: Exception) -> Dict:
        """处理失败（私有方法，在锁内调用）"""
        state = await self.state_machine.get_state(gate_id)
        gate_config = self.gates.get(gate_id)
        
        logger.warning("gate_failed", gate_id=gate_id, error=str(error), failure_count=state.failure_count)
        
        if state.failure_count >= gate_config.max_retries:
            await self._escalate_to_owner(gate_id)
            raise GateMaxRetriesError(f"Gate {gate_id} 连续失败 {state.failure_count} 次，已升级")
        
        return {"retry": True, "failure_count": state.failure_count, "error": str(error)}
    
    async def _escalate_to_owner(self, gate_id: str):
        """升级到负责人（私有方法，在锁内调用）"""
        current_status = await self.state_machine.get_status(gate_id)
        
        if current_status == GateStatus.FAILED:
            # FAILED → ESCALATED
            await self.state_machine.transition(gate_id, GateStatus.ESCALATED)
        elif current_status == GateStatus.TIMEOUT:
            # TIMEOUT → ESCALATED（直接升级）
            await self.state_machine.transition(gate_id, GateStatus.ESCALATED)
        elif current_status != GateStatus.ESCALATED:
            # 其他状态 → FAILED → ESCALATED
            await self.state_machine.transition(gate_id, GateStatus.FAILED)
            await self.state_machine.transition(gate_id, GateStatus.ESCALATED)
        
        logger.error("gate_escalated", gate_id=gate_id)
    
    async def reset_gate(self, gate_id: str, force: bool = False):
        """重置 Gate（细粒度锁）"""
        gate_lock = self._get_gate_lock(gate_id)
        async with gate_lock:
            await self.state_machine.reset_gate(gate_id, force=force)
            logger.info("gate_reset", gate_id=gate_id, force=force)
    
    async def start_timeout_monitor(self, interval: int = 60):
        """启动超时监控"""
        async def _monitor():
            while True:
                try:
                    await asyncio.sleep(interval)
                    await self._check_all_timeouts()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("timeout_monitor_error", error=str(e))
        
        self._timeout_task = asyncio.create_task(_monitor())
        logger.info("timeout_monitor_started", interval=interval)
    
    async def stop_timeout_monitor(self):
        """停止超时监控"""
        if self._timeout_task:
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass
            self._timeout_task = None
            logger.info("timeout_monitor_stopped")
    
    async def _check_all_timeouts(self):
        """检查所有 Gate 的超时状态"""
        for gate_id in self.gates.keys():
            try:
                await self.check_timeout(gate_id)
            except Exception as e:
                logger.error("timeout_check_error", gate_id=gate_id, error=str(e))
    
    async def check_timeout(self, gate_id: str):
        """检查超时（细粒度锁）"""
        gate_lock = self._get_gate_lock(gate_id)
        async with gate_lock:
            state = await self.state_machine.get_state(gate_id)
            gate_config = self.gates.get(gate_id)
            
            if state.status != GateStatus.IN_PROGRESS:
                return
            
            if not state.entry_time:
                return
            
            entry_time = datetime.fromisoformat(state.entry_time)
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=timezone.utc)
            timeout = timedelta(seconds=gate_config.timeout)
            
            if datetime.now(timezone.utc) - entry_time > timeout:
                # 取消正在运行的任务
                task = self._running_tasks.get(gate_id)
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                # 处理超时
                await self._handle_timeout(gate_id)
