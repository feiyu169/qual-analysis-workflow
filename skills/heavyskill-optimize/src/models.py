"""HeavySkill 优化方案 V3 - 数据模型"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime


class Severity(str, Enum):
    """问题严重程度枚举"""
    P0 = "P0"      # 致命问题
    P1 = "P1"      # 重大问题
    P2 = "P2"      # 一般问题
    P3 = "P3"      # 建议优化
    
    @classmethod
    def from_str(cls, s: str) -> 'Severity':
        """安全转换，支持多种输入格式"""
        mapping = {
            # 英文格式
            "CRITICAL": cls.P0, "P0": cls.P0, "FATAL": cls.P0, "BLOCKER": cls.P0,
            "MAJOR": cls.P1, "P1": cls.P1, "HIGH": cls.P1, "IMPORTANT": cls.P1,
            "MINOR": cls.P2, "P2": cls.P2, "MEDIUM": cls.P2, "NORMAL": cls.P2,
            "INFO": cls.P3, "P3": cls.P3, "LOW": cls.P3, "SUGGESTION": cls.P3,
            # 中文格式
            "致命": cls.P0, "阻断": cls.P0, "严重": cls.P0,
            "重大": cls.P1, "重要": cls.P1, "高": cls.P1,
            "一般": cls.P2, "中": cls.P2, "中等": cls.P2,
            "建议": cls.P3, "低": cls.P3, "优化": cls.P3,
        }
        # 尝试精确匹配
        result = mapping.get(s.upper())
        if result:
            return result
        # 尝试模糊匹配
        for key, value in mapping.items():
            if key in s.upper() or s.upper() in key:
                return value
        # 默认返回 P2
        return cls.P2


class Verdict(str, Enum):
    """审查结论枚举"""
    PASS = "PASS"                    # 通过
    CONDITIONAL_PASS = "CONDITIONAL"  # 附意见通过
    REJECT = "REJECT"                # 不通过
    PENDING_REVIEW = "PENDING"        # 待人工审核


@dataclass
class Issue:
    """问题数据类"""
    id: str
    title: str
    severity: Severity
    domain: str  # 安全/架构/性能/功能/其他
    description: str
    suggestion: str
    confidence: float = 1.0  # 置信度 0-1
    source: str = ""  # 来源（轨迹ID/检查清单ID）
    location: str = ""  # 问题位置
    evidence: str = ""  # 证据


@dataclass
class RuleResult:
    """规则执行结果"""
    rule_name: str
    triggered: bool
    verdict: Verdict
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """验证结果"""
    verdict: Verdict
    rules_applied: List[RuleResult]
    issues: List[Issue]
    confidence: float  # 结论置信度
    shadow_mode: bool = False
    shadow_log: Optional[Dict] = None
    fallback: bool = False
    human_review_required: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
