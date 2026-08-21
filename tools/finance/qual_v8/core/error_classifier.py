"""
错误分类器模块

实现错误分类和处理策略
"""

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """错误类型"""
    TRANSIENT = "transient"  # 临时性错误
    PERMANENT = "permanent"  # 永久性错误
    BUSINESS = "business"  # 业务错误


@dataclass
class ErrorClassification:
    """错误分类结果"""
    error_type: ErrorType
    retry: bool
    max_retries: int
    escalate: bool
    backoff: bool
    description: str


# 错误码映射
ERROR_CODE_MAPPING = {
    # 网络错误（临时性）
    "NETWORK_TIMEOUT": {"type": "transient", "retry": True, "max_retries": 3, "backoff": True},
    "NETWORK_CONNECTION_ERROR": {"type": "transient", "retry": True, "max_retries": 3, "backoff": True},
    "HTTP_429": {"type": "transient", "retry": True, "max_retries": 3, "backoff": True},
    "HTTP_502": {"type": "transient", "retry": True, "max_retries": 3, "backoff": True},
    "HTTP_503": {"type": "transient", "retry": True, "max_retries": 3, "backoff": True},
    "HTTP_504": {"type": "transient", "retry": True, "max_retries": 3, "backoff": True},

    # 认证错误（永久性）
    "HTTP_401": {"type": "permanent", "retry": False, "escalate": True},
    "HTTP_403": {"type": "permanent", "retry": False, "escalate": True},
    "AUTH_FAILED": {"type": "permanent", "retry": False, "escalate": True},
    "TOKEN_EXPIRED": {"type": "permanent", "retry": False, "escalate": True},

    # 数据错误（永久性）
    "HTTP_404": {"type": "permanent", "retry": False, "escalate": True},
    "DATA_NOT_FOUND": {"type": "permanent", "retry": False, "escalate": True},
    "DATA_FORMAT_ERROR": {"type": "permanent", "retry": False, "escalate": True},
    "DATA_PARSE_ERROR": {"type": "permanent", "retry": False, "escalate": True},

    # 业务错误
    "COVERAGE_BELOW_THRESHOLD": {"type": "business", "retry": True, "max_retries": 1},
    "PARAMETER_OUT_OF_RANGE": {"type": "business", "retry": False, "escalate": True},
    "LOGIC_CONTRADICTION": {"type": "business", "retry": False, "escalate": True},
    "VALIDATION_FAILED": {"type": "business", "retry": True, "max_retries": 1},

    # 系统错误（临时性）
    "DATABASE_CONNECTION_ERROR": {"type": "transient", "retry": True, "max_retries": 3},
    "DATABASE_TIMEOUT": {"type": "transient", "retry": True, "max_retries": 3},
    "MEMORY_ERROR": {"type": "transient", "retry": True, "max_retries": 1},
    "LLM_TIMEOUT": {"type": "transient", "retry": True, "max_retries": 2},
    "LLM_RATE_LIMIT": {"type": "transient", "retry": True, "max_retries": 3, "backoff": True},
}


class ErrorClassifier:
    """错误分类器"""

    def __init__(self):
        self.error_mapping = ERROR_CODE_MAPPING

    def classify(self, error_code: str, error_message: str = "") -> ErrorClassification:
        """分类错误"""
        if error_code in self.error_mapping:
            config = self.error_mapping[error_code]
            return ErrorClassification(
                error_type=ErrorType(config["type"]),
                retry=config.get("retry", False),
                max_retries=config.get("max_retries", 0),
                escalate=config.get("escalate", False),
                backoff=config.get("backoff", False),
                description=f"{error_code}: {error_message}",
            )

        # 默认分类为临时性错误
        return ErrorClassification(
            error_type=ErrorType.TRANSIENT,
            retry=True,
            max_retries=3,
            escalate=False,
            backoff=True,
            description=f"未知错误: {error_code} - {error_message}",
        )

    def classify_from_exception(self, exception: Exception) -> ErrorClassification:
        """从异常分类错误"""
        error_type = type(exception).__name__
        error_message = str(exception)

        # 根据异常类型分类
        if isinstance(exception, (ConnectionError, TimeoutError)):
            return self.classify("NETWORK_TIMEOUT", error_message)
        elif isinstance(exception, PermissionError):
            return self.classify("HTTP_403", error_message)
        elif isinstance(exception, FileNotFoundError):
            return self.classify("DATA_NOT_FOUND", error_message)
        elif isinstance(exception, ValueError):
            return self.classify("VALIDATION_FAILED", error_message)
        else:
            return self.classify("UNKNOWN_ERROR", error_message)
