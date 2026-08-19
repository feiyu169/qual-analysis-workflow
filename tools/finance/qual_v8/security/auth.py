"""
安全合规模块

实现密钥管理、数据脱敏、RBAC权限控制
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import hashlib
import hmac
import os
import logging

logger = logging.getLogger(__name__)


class Permission(Enum):
    """权限"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    CANCEL = "cancel"
    RETRY = "retry"
    ROLLBACK = "rollback"
    OVERRIDE = "override"
    RESPOND = "respond"
    ESCALATE = "escalate"
    REASSIGN = "reassign"
    EXPORT = "export"
    VERIFY = "verify"
    MONITOR = "monitor"
    ALERT = "alert"
    BACKUP = "backup"
    RESTORE = "restore"


# RBAC权限矩阵
PERMISSION_MATRIX = {
    "admin": {
        "workflow": [Permission.CREATE, Permission.READ, Permission.UPDATE, Permission.DELETE, Permission.CANCEL, Permission.RETRY, Permission.ROLLBACK],
        "gate": [Permission.READ, Permission.RETRY, Permission.SKIP, Permission.ROLLBACK, Permission.OVERRIDE],
        "human_intervention": [Permission.READ, Permission.RESPOND, Permission.ESCALATE, Permission.REASSIGN],
        "audit_log": [Permission.READ, Permission.EXPORT, Permission.VERIFY],
        "config": [Permission.READ, Permission.UPDATE],
        "user": [Permission.CREATE, Permission.READ, Permission.UPDATE, Permission.DELETE],
        "system": [Permission.MONITOR, Permission.ALERT, Permission.BACKUP, Permission.RESTORE],
    },
    "analyst": {
        "workflow": [Permission.CREATE, Permission.READ],
        "gate": [Permission.READ],
        "human_intervention": [Permission.READ, Permission.RESPOND],
        "audit_log": [Permission.READ],
        "config": [Permission.READ],
        "user": [],
        "system": [],
    },
    "reviewer": {
        "workflow": [Permission.READ],
        "gate": [Permission.READ],
        "human_intervention": [Permission.READ, Permission.RESPOND, Permission.ESCALATE],
        "audit_log": [Permission.READ],
        "config": [Permission.READ],
        "user": [],
        "system": [],
    },
    "viewer": {
        "workflow": [Permission.READ],
        "gate": [Permission.READ],
        "human_intervention": [Permission.READ],
        "audit_log": [Permission.READ],
        "config": [],
        "user": [],
        "system": [],
    },
}


class RBACManager:
    """RBAC权限管理器"""
    
    def __init__(self):
        self.permission_matrix = PERMISSION_MATRIX
    
    def check_permission(self, role: str, resource: str, permission: Permission) -> bool:
        """检查权限"""
        if role not in self.permission_matrix:
            return False
        
        role_permissions = self.permission_matrix[role]
        if resource not in role_permissions:
            return False
        
        return permission in role_permissions[resource]


class DataMasker:
    """数据脱敏器"""
    
    MASKING_RULES = {
        "api_key": {"type": "full", "replacement": "***"},
        "password": {"type": "full", "replacement": "***"},
        "secret_key": {"type": "full", "replacement": "***"},
        "email": {"type": "partial", "keep_chars": 3},
        "phone": {"type": "partial", "keep_chars": 4},
        "id_card": {"type": "partial", "keep_chars": 4},
        "bank_card": {"type": "partial", "keep_chars": 4},
    }
    
    def mask(self, data: Dict[str, Any], field_type: str) -> Dict[str, Any]:
        """对数据进行脱敏"""
        masked_data = data.copy()
        
        if field_type in self.MASKING_RULES:
            rule = self.MASKING_RULES[field_type]
            
            for key, value in masked_data.items():
                if isinstance(value, str):
                    if rule["type"] == "full":
                        masked_data[key] = rule["replacement"]
                    elif rule["type"] == "partial":
                        keep_chars = rule.get("keep_chars", 3)
                        if len(value) > keep_chars:
                            masked_data[key] = value[:keep_chars] + "***"
        
        return masked_data


class KeyManager:
    """密钥管理器"""
    
    def __init__(self):
        self._cache: Dict[str, str] = {}
    
    def get_key(self, key_id: str) -> Optional[str]:
        """获取密钥"""
        if key_id in self._cache:
            return self._cache[key_id]
        
        # 从环境变量获取
        key = os.environ.get(key_id)
        if key:
            self._cache[key_id] = key
        
        return key
    
    def sign_data(self, data: str, key_id: str) -> str:
        """签名数据"""
        key = self.get_key(key_id)
        if not key:
            raise ValueError(f"密钥 {key_id} 不存在")
        
        return hmac.new(
            key.encode(),
            data.encode(),
            hashlib.sha256,
        ).hexdigest()
    
    def verify_signature(self, data: str, signature: str, key_id: str) -> bool:
        """验证签名"""
        expected_signature = self.sign_data(data, key_id)
        return hmac.compare_digest(signature, expected_signature)
