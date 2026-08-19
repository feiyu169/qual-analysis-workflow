"""
异步 Gate 状态机 - 生产级实现
"""
import asyncio
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional

import aiosqlite
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
    """Gate 状态"""
    gate_id: str
    status: GateStatus
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None
    failure_count: int = 0
    timeout_count: int = 0
    last_error: Optional[str] = None
    metadata: Optional[Dict] = None


class AsyncGateStateMachine:
    """异步 Gate 状态机
    
    特性：
    - 异步数据库操作（aiosqlite）
    - 事务原子性
    - 自动 Schema 迁移
    - 线程安全（asyncio.Lock）
    """
    
    # 合法的状态转移表
    VALID_TRANSITIONS = {
        GateStatus.PENDING: [GateStatus.IN_PROGRESS],
        GateStatus.IN_PROGRESS: [GateStatus.PASSED, GateStatus.FAILED, GateStatus.TIMEOUT],
        GateStatus.FAILED: [GateStatus.IN_PROGRESS, GateStatus.ESCALATED],
        GateStatus.TIMEOUT: [GateStatus.IN_PROGRESS, GateStatus.ESCALATED],
        GateStatus.PASSED: [],  # 终态
        GateStatus.ESCALATED: [GateStatus.IN_PROGRESS],
    }
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path
        self.states: Dict[str, GateState] = {}
        self._lock = asyncio.Lock()
        self._db: Optional[aiosqlite.Connection] = None
    
    async def initialize(self):
        """异步初始化"""
        if self.db_path:
            self._db = await aiosqlite.connect(self.db_path)
            await self._init_db()
            await self._load_states()
            logger.info("database_initialized", db_path=self.db_path)
    
    async def close(self):
        """关闭数据库连接"""
        if self._db:
            await self._db.close()
            self._db = None
    
    async def _init_db(self):
        """异步初始化数据库"""
        async with self._db.cursor() as cursor:
            # 启用 WAL 模式
            await cursor.execute("PRAGMA journal_mode=WAL")
            await cursor.execute("PRAGMA busy_timeout=5000")
            
            # 创建表
            await cursor.execute('''
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
            
            # 迁移：添加 timeout_count 列（如果不存在）
            await cursor.execute("PRAGMA table_info(gate_states)")
            columns = [row[1] async for row in cursor]
            if 'timeout_count' not in columns:
                await cursor.execute('ALTER TABLE gate_states ADD COLUMN timeout_count INTEGER DEFAULT 0')
                logger.info("migration_added_column", column="timeout_count")
            
            await self._db.commit()
    
    async def _load_states(self):
        """从数据库加载状态"""
        async with self._db.cursor() as cursor:
            await cursor.execute(
                'SELECT gate_id, status, entry_time, exit_time, failure_count, timeout_count, last_error, metadata, updated_at FROM gate_states'
            )
            async for row in cursor:
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
    
    async def _save_state(self, gate_id: str):
        """保存状态到数据库（原子事务）"""
        state = self.states[gate_id]
        now = datetime.now(timezone.utc).isoformat()
        
        async with self._db.cursor() as cursor:
            await cursor.execute('''
                INSERT OR REPLACE INTO gate_states 
                (gate_id, status, entry_time, exit_time, failure_count, timeout_count, last_error, metadata, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                gate_id,
                state.status.value,
                state.entry_time,
                state.exit_time,
                state.failure_count,
                state.timeout_count,
                state.last_error,
                json.dumps(state.metadata) if state.metadata else None,
                now
            ))
            await self._db.commit()
        
        logger.info("state_saved", gate_id=gate_id, status=state.status.value)
    
    async def add_gate(self, gate_id: str):
        """添加 Gate"""
        async with self._lock:
            if gate_id in self.states:
                return  # 已存在，幂等
            
            self.states[gate_id] = GateState(
                gate_id=gate_id,
                status=GateStatus.PENDING
            )
            
            if self._db:
                await self._save_state(gate_id)
            
            logger.info("gate_added", gate_id=gate_id)
    
    async def get_status(self, gate_id: str) -> GateStatus:
        """获取 Gate 状态"""
        async with self._lock:
            state = self.states.get(gate_id)
            if not state:
                raise ValueError(f"Gate {gate_id} not found")
            return state.status
    
    async def get_state(self, gate_id: str) -> GateState:
        """获取 Gate 完整状态"""
        async with self._lock:
            state = self.states.get(gate_id)
            if not state:
                raise ValueError(f"Gate {gate_id} not found")
            return state
    
    async def get_all_states(self) -> Dict[str, GateState]:
        """获取所有 Gate 状态"""
        async with self._lock:
            return dict(self.states)
    
    async def transition(self, gate_id: str, target_status: GateStatus, error: str = None):
        """状态转移（原子事务）"""
        async with self._lock:
            state = self.states.get(gate_id)
            if not state:
                raise ValueError(f"Gate {gate_id} not found")
            
            # 检查转移合法性
            current_status = state.status
            if target_status not in self.VALID_TRANSITIONS.get(current_status, []):
                raise ValueError(
                    f"Invalid transition: {current_status.value} -> {target_status.value} "
                    f"for gate {gate_id}"
                )
            
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
                new_timeout_count += 1
            
            # 原子写入数据库
            if self._db:
                try:
                    async with self._db.cursor() as cursor:
                        await cursor.execute('''
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
                        await self._db.commit()
                except Exception as e:
                    # 数据库写入失败，不更新内存
                    logger.error("transition_db_error", gate_id=gate_id, error=str(e))
                    raise
            
            # 更新内存
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
    
    async def reset_gate(self, gate_id: str, force: bool = False):
        """重置 Gate"""
        async with self._lock:
            state = self.states.get(gate_id)
            if not state:
                raise ValueError(f"Gate {gate_id} not found")
            
            # PASSED 状态需要 force
            if state.status == GateStatus.PASSED and not force:
                raise ValueError(
                    f"Gate {gate_id} 已通过，不可重置。使用 force=True 强制重置。"
                )
            
            # 重置状态
            state.status = GateStatus.PENDING
            state.entry_time = None
            state.exit_time = None
            state.failure_count = 0
            state.timeout_count = 0
            state.last_error = None
            
            # 持久化
            if self._db:
                await self._save_state(gate_id)
            
            logger.info("gate_reset", gate_id=gate_id, force=force)
