"""
状态机实现 - Gate-Driven Workflow
确保 Gate 状态转移不可绕过
"""

import sqlite3
import json
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


class GateStatus(Enum):
    """Gate 状态枚举"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ESCALATED = "escalated"


@dataclass
class GateState:
    """Gate 状态数据"""
    gate_id: str
    status: GateStatus
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None
    failure_count: int = 0
    timeout_count: int = 0  # 超时计数
    last_error: Optional[str] = None
    metadata: Optional[Dict] = None


class GateStateMachine:
    """Gate 状态机 - 不可绕过"""
    
    # 合法的状态转移
    VALID_TRANSITIONS = {
        GateStatus.PENDING: [GateStatus.IN_PROGRESS],
        GateStatus.IN_PROGRESS: [GateStatus.PASSED, GateStatus.FAILED, GateStatus.TIMEOUT],
        GateStatus.FAILED: [GateStatus.IN_PROGRESS, GateStatus.ESCALATED],
        GateStatus.TIMEOUT: [GateStatus.IN_PROGRESS, GateStatus.ESCALATED],
        GateStatus.PASSED: [],  # 终态，不可转移
        GateStatus.ESCALATED: [GateStatus.IN_PROGRESS],  # 升级后可重试
    }
    
    def __init__(self, db_path: str = None):
        self.states: Dict[str, GateState] = {}
        self.db_path = db_path
        self._lock = threading.Lock()
        if db_path:
            self._init_db()
            self._load_states()
    
    def _init_db(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS gate_states (
                    gate_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    entry_time TEXT,
                    exit_time TEXT,
                    failure_count INTEGER DEFAULT 0,
                    timeout_count INTEGER DEFAULT 0,
                    last_error TEXT,
                    metadata TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 数据库迁移：添加 timeout_count 列（如果不存在）
            cursor.execute("PRAGMA table_info(gate_states)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'timeout_count' not in columns:
                cursor.execute('ALTER TABLE gate_states ADD COLUMN timeout_count INTEGER DEFAULT 0')
                logger.info("migration_added_column", column="timeout_count")
            
            conn.commit()
        logger.info("database_initialized", db_path=self.db_path)
    
    def _load_states(self):
        """从数据库加载状态"""
        if not self.db_path:
            return
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT gate_id, status, entry_time, exit_time, failure_count, timeout_count, last_error, metadata, updated_at FROM gate_states')
            rows = cursor.fetchall()
        
        for row in rows:
            gate_id, status, entry_time, exit_time, failure_count, timeout_count, last_error, metadata, _ = row
            # 安全解析 metadata JSON
            parsed_metadata = None
            if metadata:
                try:
                    parsed_metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    logger.warning("metadata_parse_error", gate_id=gate_id, metadata=metadata)
            self.states[gate_id] = GateState(
                gate_id=gate_id,
                status=GateStatus(status),
                entry_time=entry_time,
                exit_time=exit_time,
                failure_count=failure_count,
                timeout_count=timeout_count,
                last_error=last_error,
                metadata=parsed_metadata
            )
        
        logger.info("states_loaded", count=len(self.states))
    
    def _save_state(self, gate_id: str):
        """保存状态到数据库"""
        if not self.db_path:
            return
        
        state = self.states.get(gate_id)
        if not state:
            return
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO gate_states 
                (gate_id, status, entry_time, exit_time, failure_count, timeout_count, last_error, metadata, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                state.gate_id,
                state.status.value,
                state.entry_time,
                state.exit_time,
                state.failure_count,
                state.timeout_count,
                state.last_error,
                json.dumps(state.metadata) if state.metadata else None,
                datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()
        logger.info("state_saved", gate_id=gate_id, status=state.status.value)
    
    def add_gate(self, gate_id: str):
        """添加 Gate"""
        with self._lock:
            if gate_id in self.states:
                logger.warning("gate_already_exists", gate_id=gate_id)
                return
            
            self.states[gate_id] = GateState(
                gate_id=gate_id,
                status=GateStatus.PENDING
            )
            self._save_state(gate_id)
            logger.info("gate_added", gate_id=gate_id)
    
    def get_status(self, gate_id: str) -> GateStatus:
        """获取 Gate 状态"""
        state = self.states.get(gate_id)
        if not state:
            raise ValueError(f"Gate {gate_id} not found")
        return state.status
    
    def can_transition(self, gate_id: str, target_status: GateStatus) -> bool:
        """检查是否可以转移"""
        with self._lock:
            return self._can_transition_locked(gate_id, self.get_status(gate_id), target_status)
    
    def _can_transition_locked(self, gate_id: str, current_status: GateStatus, target_status: GateStatus) -> bool:
        """检查是否可以转移（内部方法，需持锁）"""
        valid_targets = self.VALID_TRANSITIONS.get(current_status, [])
        return target_status in valid_targets
    
    def transition(self, gate_id: str, target_status: GateStatus, error: str = None):
        """状态转移 - 不可绕过（线程安全）"""
        with self._lock:
            current_status = self.get_status(gate_id)
            
            # 检查转移合法性
            if not self._can_transition_locked(gate_id, current_status, target_status):
                raise ValueError(
                    f"Invalid transition: {current_status.value} -> {target_status.value} "
                    f"for gate {gate_id}"
                )
            
            # 准备新状态（不直接修改内存）
            state = self.states[gate_id]
            now = datetime.now(timezone.utc).isoformat()
            
            # 计算新值
            new_entry_time = state.entry_time
            new_exit_time = state.exit_time
            new_failure_count = state.failure_count
            new_timeout_count = state.timeout_count
            
            if target_status == GateStatus.IN_PROGRESS:
                new_entry_time = now
            elif target_status in [GateStatus.PASSED, GateStatus.FAILED, GateStatus.TIMEOUT]:
                new_exit_time = now
            
            if target_status == GateStatus.FAILED:
                new_failure_count += 1
            
            if target_status == GateStatus.TIMEOUT:
                new_timeout_count = state.timeout_count + 1
            else:
                new_timeout_count = state.timeout_count
            
            # 先保存到数据库（write-ahead）
            if self.db_path:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO gate_states 
                        (gate_id, status, entry_time, exit_time, failure_count, timeout_count, last_error, metadata, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        gate_id,
                        target_status.value,
                        new_entry_time,
                        new_exit_time,
                        new_failure_count,
                        new_timeout_count,
                        error or state.last_error,
                        json.dumps(state.metadata) if state.metadata else None,
                        now
                    ))
                    conn.commit()
            
            # DB成功后再更新内存
            state.status = target_status
            state.entry_time = new_entry_time
            state.exit_time = new_exit_time
            state.failure_count = new_failure_count
            state.timeout_count = new_timeout_count
            if error:
                state.last_error = error
            
            logger.info(
                "state_transition",
                gate_id=gate_id,
                from_status=current_status.value,
                to_status=target_status.value,
                error=error
            )
    
    def get_state(self, gate_id: str) -> GateState:
        """获取完整状态"""
        state = self.states.get(gate_id)
        if not state:
            raise ValueError(f"Gate {gate_id} not found")
        return state
    
    def get_all_states(self) -> Dict[str, GateState]:
        """获取所有状态"""
        return self.states.copy()
    
    def reset_gate(self, gate_id: str, force: bool = False):
        """重置 Gate 状态（线程安全）
        
        Args:
            gate_id: Gate ID
            force: 是否强制重置终态（需要显式声明）
        """
        with self._lock:
            current_status = self.get_status(gate_id)
            if current_status == GateStatus.PASSED and not force:
                raise ValueError(
                    f"Gate {gate_id} 已通过，不可重置。使用 force=True 强制重置。"
                )
            self.states[gate_id] = GateState(
                gate_id=gate_id,
                status=GateStatus.PENDING
            )
            self._save_state(gate_id)
            logger.info("gate_reset", gate_id=gate_id, force=force)
    
    def is_terminal(self, gate_id: str) -> bool:
        """检查是否为终态"""
        status = self.get_status(gate_id)
        # PASSED 是不可逆终态；ESCALATED 不是终态（可人工干预后重试）
        return status == GateStatus.PASSED
