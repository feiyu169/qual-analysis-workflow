#!/usr/bin/env python3
# NOTE: Copied from investment/ package (2026-06-30)
# Source: ~/.hermes/tools/investment/stage_manager.py
# Update: 当 investment/ 更新时，需同步更新此文件
"""外部工作流状态管理器 — V5.0 乐观锁修复版

特性:
- SQLite 持久化 + PRAGMA busy_timeout
- threading.Lock 类锁保护写操作
- 乐观锁（version 列）检测并发冲突
- 冲突时重新加载+合并+重试（非 INSERT OR REPLACE 覆盖）
- 新 session 自动 INSERT
- 熔断器集成（on_circuit_break: block/skip/retry）
- 自定义 JSON 序列化器（numpy/pandas/datetime）
"""

import json
import sqlite3
import threading
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _json_serializer(obj: Any) -> Any:
    """自定义 JSON 序列化器"""
    try:
        import numpy as np
    except ImportError:
        np = None
    try:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            return {"_type": "DataFrame", "data": obj.to_dict()}
        if isinstance(obj, pd.Series):
            return {"_type": "Series", "data": obj.to_dict()}
    except ImportError:
        pass
    if np is not None:
        if isinstance(obj, np.ndarray):
            return {"_type": "ndarray", "data": obj.tolist()}
        if isinstance(obj, (np.integer, np.floating)):
            return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


@dataclass
class StageDefinition:
    """阶段定义"""
    name: str
    required_outputs: List[str]
    blocking_checks: List[str] = field(default_factory=list)
    on_circuit_break: str = "block"  # block | skip | retry


STAGES: Dict[int, StageDefinition] = {
    0: StageDefinition(
        name="路由", required_outputs=["skill_loaded", "ticker"],
        on_circuit_break="skip"),
    1: StageDefinition(
        name="数据采集", required_outputs=["wind_data", "search_results"],
        blocking_checks=["wind_data_non_empty"], on_circuit_break="block"),
    2: StageDefinition(
        name="数据验证", required_outputs=["validation_result"],
        blocking_checks=["validation_passed_or_warned"], on_circuit_break="retry"),
    3: StageDefinition(
        name="财务建模", required_outputs=["dcf_result", "valuation_cross_check"],
        blocking_checks=["valuation_deviation_checked"], on_circuit_break="block"),
    4: StageDefinition(
        name="深度分析",
        required_outputs=["business_analysis", "financial_analysis", "risk_analysis"],
        blocking_checks=["analysis_content_sufficient"], on_circuit_break="retry"),
    5: StageDefinition(
        name="报告生成", required_outputs=["report_content"],
        blocking_checks=["report_lint_passed"], on_circuit_break="skip"),
    6: StageDefinition(
        name="存档", required_outputs=["gbrain_written", "flomo_written"],
        on_circuit_break="retry"),
}


class StageManager:
    """外部工作流状态管理器 — SQLite + 乐观锁 + 线程安全"""

    DB_PATH = Path.home() / ".hermes" / "data" / "investment_stages.db"
    _lock = threading.Lock()

    def __init__(self, session_id: str, db_path: Optional[Path] = None):
        self.session_id = session_id
        self.current_stage = 0
        self.completed_stages: List[int] = []
        self.stage_outputs: Dict[str, Any] = {}
        self.stage_timestamps: Dict[int, str] = {}
        self.blocking_results: Dict[str, bool] = {}
        self._version = 0
        if db_path:
            self.DB_PATH = db_path
        self._init_db()

    def _init_db(self):
        """初始化 SQLite 数据库"""
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stage_state (
                session_id TEXT PRIMARY KEY,
                current_stage INTEGER DEFAULT 0,
                completed_stages TEXT DEFAULT '[]',
                stage_outputs TEXT DEFAULT '{}',
                stage_timestamps TEXT DEFAULT '{}',
                blocking_results TEXT DEFAULT '{}',
                version INTEGER DEFAULT 0,
                updated_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """获取带 busy_timeout 的连接"""
        conn = sqlite3.connect(str(self.DB_PATH), timeout=10)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def check_stage_completion(self, stage: int) -> Dict[str, Any]:
        """检查阶段是否完成"""
        if stage not in STAGES:
            return {"stage": stage, "completed": False, "error": f"未知阶段: {stage}"}

        definition = STAGES[stage]
        missing = [o for o in definition.required_outputs if o not in self.stage_outputs]
        blocking_failed = [
            c for c in definition.blocking_checks
            if c in self.blocking_results and not self.blocking_results[c]
        ]

        return {
            "stage": stage,
            "name": definition.name,
            "completed": len(missing) == 0 and len(blocking_failed) == 0,
            "missing_outputs": missing,
            "blocking_failed": blocking_failed,
        }

    def record_output(self, key: str, value: Any):
        """记录阶段输出"""
        try:
            json.dumps(value, default=_json_serializer)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Output value for '{key}' must be JSON-serializable: {e}")
        self.stage_outputs[key] = value
        self._save_state()

    def record_blocking_result(self, check: str, passed: bool):
        """记录阻断检查结果"""
        self.blocking_results[check] = passed
        self._save_state()

    def advance_to_next_stage(self, circuit_breaker=None) -> Dict[str, Any]:
        """尝试进入下一阶段（集成熔断器）"""
        # 熔断器检查
        if circuit_breaker is not None:
            definition = STAGES.get(self.current_stage)
            if definition:
                cb_action = definition.on_circuit_break
                if cb_action == "block" and not circuit_breaker.can_execute():
                    return {
                        "success": False,
                        "reason": "circuit_breaker_open",
                        "action": "block",
                        "message": f"熔断器已打开，阶段 {self.current_stage} ({definition.name}) 被阻断",
                    }
                elif cb_action == "skip" and not circuit_breaker.can_execute():
                    self.completed_stages.append(self.current_stage)
                    self.stage_timestamps[self.current_stage] = datetime.now().isoformat()
                    self.current_stage += 1
                    self._save_state()
                    return {
                        "success": True, "new_stage": self.current_stage,
                        "action": "skip",
                        "message": f"熔断器已打开，跳过阶段 {self.current_stage - 1}",
                    }
                elif cb_action == "retry" and not circuit_breaker.can_execute():
                    logger.warning(f"熔断器已打开，阶段 {self.current_stage} 将重试")

        result = self.check_stage_completion(self.current_stage)
        if result["completed"]:
            self.completed_stages.append(self.current_stage)
            self.stage_timestamps[self.current_stage] = datetime.now().isoformat()
            self.current_stage += 1
            self._save_state()
            return {"success": True, "new_stage": self.current_stage}
        else:
            return {"success": False, "reason": result}

    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            "session_id": self.session_id,
            "current_stage": self.current_stage,
            "completed_stages": self.completed_stages,
            "stage_outputs": self.stage_outputs,
            "stage_timestamps": self.stage_timestamps,
            "blocking_results": self.blocking_results,
            "version": self._version,
        }

    def _save_state(self):
        """持久化状态（乐观锁 + 新 session INSERT）"""
        with StageManager._lock:
            for attempt in range(3):
                conn = self._get_connection()
                try:
                    now = datetime.now().isoformat()
                    old_version = self._version
                    new_version = old_version + 1

                    cursor = conn.execute("""
                        UPDATE stage_state SET
                            current_stage = ?,
                            completed_stages = ?,
                            stage_outputs = ?,
                            stage_timestamps = ?,
                            blocking_results = ?,
                            version = ?,
                            updated_at = ?
                        WHERE session_id = ? AND version = ?
                    """, (
                        self.current_stage,
                        json.dumps(self.completed_stages),
                        json.dumps(self.stage_outputs, default=_json_serializer),
                        json.dumps(self.stage_timestamps),
                        json.dumps(self.blocking_results),
                        new_version,
                        now,
                        self.session_id,
                        old_version,
                    ))

                    if cursor.rowcount == 0:
                        conn.close()
                        # P0-1 FIX: 保存本地变更 BEFORE 加载 DB 状态
                        local_outputs = self.stage_outputs.copy()
                        local_blocking = self.blocking_results.copy()
                        local_stage = self.current_stage
                        local_completed = self.completed_stages.copy()
                        local_timestamps = self.stage_timestamps.copy()

                        # 尝试加载：如果 session 不存在，执行 INSERT
                        if not self.load_state():
                            logger.info(f"Session {self.session_id} 不存在，创建新记录")
                            conn2 = self._get_connection()
                            try:
                                conn2.execute("""
                                    INSERT INTO stage_state
                                    (session_id, current_stage, completed_stages,
                                     stage_outputs, stage_timestamps, blocking_results,
                                     version, updated_at)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    self.session_id,
                                    self.current_stage,
                                    json.dumps(self.completed_stages),
                                    json.dumps(self.stage_outputs, default=_json_serializer),
                                    json.dumps(self.stage_timestamps),
                                    json.dumps(self.blocking_results),
                                    1,
                                    now,
                                ))
                                conn2.commit()
                                self._version = 1
                                return
                            finally:
                                conn2.close()

                        # session 存在但版本冲突 → 合并重试
                        logger.warning(f"乐观锁冲突 (attempt {attempt+1}/3)，重新加载并合并")

                        # 合并本地变更到 DB 状态（local_* 已在 load_state 前保存）
                        self.stage_outputs.update(local_outputs)
                        self.blocking_results.update(local_blocking)
                        self.current_stage = max(self.current_stage, local_stage)
                        self.completed_stages = list(set(self.completed_stages) | set(local_completed))
                        for k, v in local_timestamps.items():
                            if k not in self.stage_timestamps or v > self.stage_timestamps[k]:
                                self.stage_timestamps[k] = v

                        continue

                    conn.commit()
                    self._version = new_version
                    return

                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e) and attempt < 2:
                        logger.warning(f"SQLite locked, retrying ({attempt+1}/3)")
                        import time
                        time.sleep(0.1 * (attempt + 1))
                        continue
                    raise
                finally:
                    conn.close()

    def load_state(self) -> bool:
        """加载状态"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT current_stage, completed_stages, stage_outputs, "
                "stage_timestamps, blocking_results, version "
                "FROM stage_state WHERE session_id = ?",
                (self.session_id,)
            )
            row = cursor.fetchone()

            if row:
                self.current_stage = row[0]
                try:
                    self.completed_stages = json.loads(row[1])
                    self.stage_outputs = json.loads(row[2])
                    self.stage_timestamps = json.loads(row[3])
                    self.blocking_results = json.loads(row[4])
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse state for session {self.session_id}: {e}")
                    self.completed_stages = []
                    self.stage_outputs = {}
                    self.stage_timestamps = {}
                    self.blocking_results = {}
                    return False
                self._version = row[5] if row[5] is not None else 0
                return True
            return False
        finally:
            conn.close()

    @classmethod
    def cleanup_old_sessions(cls, days: int = 30):
        """清理过期 session"""
        conn = sqlite3.connect(str(cls.DB_PATH), timeout=10)
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            cursor = conn.execute(
                "DELETE FROM stage_state WHERE updated_at < ?",
                (cutoff,)
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
