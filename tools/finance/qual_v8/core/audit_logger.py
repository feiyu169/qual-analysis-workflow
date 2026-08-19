"""
审计日志模块

实现哈希链防篡改的审计日志
"""

import hashlib
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    """审计日志条目"""
    log_id: str
    run_id: str
    gate_num: Optional[int]
    action: str
    timestamp: str
    details: Dict[str, Any]
    user_id: Optional[str]
    previous_hash: str
    current_hash: str


class AuditLogger:
    """审计日志记录器（防篡改）"""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.previous_hash = "0" * 64  # 初始哈希
        self.entries: List[AuditEntry] = []
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        if self.db_path:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    log_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    gate_num INTEGER,
                    action TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    details TEXT,
                    user_id TEXT,
                    previous_hash TEXT NOT NULL,
                    current_hash TEXT NOT NULL
                )
            """)
            
            conn.commit()
            conn.close()
    
    def log(
        self,
        run_id: str,
        gate_num: Optional[int],
        action: str,
        details: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> AuditEntry:
        """记录审计日志"""
        log_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        # 计算当前哈希
        hash_input = json.dumps({
            "log_id": log_id,
            "run_id": run_id,
            "gate_num": gate_num,
            "action": action,
            "timestamp": timestamp,
            "details": details,
            "user_id": user_id,
            "previous_hash": self.previous_hash,
        }, sort_keys=True)
        
        current_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        
        # 创建条目
        entry = AuditEntry(
            log_id=log_id,
            run_id=run_id,
            gate_num=gate_num,
            action=action,
            timestamp=timestamp,
            details=details,
            user_id=user_id,
            previous_hash=self.previous_hash,
            current_hash=current_hash,
        )
        
        # 保存到内存
        self.entries.append(entry)
        
        # 保存到数据库
        if self.db_path:
            self._save_to_db(entry)
        
        # 更新previous_hash
        self.previous_hash = current_hash
        
        logger.debug(f"审计日志: {action} (gate={gate_num})")
        return entry
    
    def _save_to_db(self, entry: AuditEntry):
        """保存到数据库"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO audit_logs (
                log_id, run_id, gate_num, action, timestamp,
                details, user_id, previous_hash, current_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.log_id, entry.run_id, entry.gate_num, entry.action,
            entry.timestamp, json.dumps(entry.details), entry.user_id,
            entry.previous_hash, entry.current_hash,
        ))
        
        conn.commit()
        conn.close()
    
    def verify_chain(self, run_id: Optional[str] = None) -> bool:
        """验证哈希链完整性"""
        entries = self.entries
        if run_id:
            entries = [e for e in entries if e.run_id == run_id]
        
        previous_hash = "0" * 64
        for entry in entries:
            # 验证previous_hash
            if entry.previous_hash != previous_hash:
                logger.error(f"哈希链断裂: log_id={entry.log_id}")
                return False
            
            # 验证current_hash
            hash_input = json.dumps({
                "log_id": entry.log_id,
                "run_id": entry.run_id,
                "gate_num": entry.gate_num,
                "action": entry.action,
                "timestamp": entry.timestamp,
                "details": entry.details,
                "user_id": entry.user_id,
                "previous_hash": previous_hash,
            }, sort_keys=True)
            
            calculated_hash = hashlib.sha256(hash_input.encode()).hexdigest()
            if calculated_hash != entry.current_hash:
                logger.error(f"哈希不匹配: log_id={entry.log_id}")
                return False
            
            previous_hash = entry.current_hash
        
        return True
    
    def get_entries(self, run_id: Optional[str] = None) -> List[AuditEntry]:
        """获取审计日志条目"""
        if run_id:
            return [e for e in self.entries if e.run_id == run_id]
        return self.entries.copy()
