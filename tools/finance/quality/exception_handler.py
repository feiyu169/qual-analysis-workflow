"""
异常处理器（分级处理+继承体系）

功能：
1. 异常分级（FATAL/WARNING/RECOVERABLE）
2. 自定义异常继承体系
3. 异常处理配置
4. 异常分类决策树
"""

import logging
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ExceptionLevel(Enum):
    """异常级别"""
    FATAL = "fatal"           # 致命：阻断流程
    WARNING = "warning"       # 警告：记录+继续
    RECOVERABLE = "recoverable"  # 可恢复：重试


@dataclass
class ExceptionConfig:
    """异常配置"""
    level: ExceptionLevel
    max_retries: int = 0
    alert: bool = False
    fallback: Callable | None = None
    description: str = ""


# ====================================================================
# 自定义异常基类
# ====================================================================

class QualException(Exception):
    """Qual流程异常基类"""

    def __init__(self, message: str, level: ExceptionLevel = ExceptionLevel.FATAL,
                 context: dict | None = None):
        super().__init__(message)
        self.level = level
        self.context = context or {}
        self.traceback_str = traceback.format_exc()

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "type": self.__class__.__name__,
            "message": str(self),
            "level": self.level.value,
            "context": self.context,
            "traceback": self.traceback_str,
        }


class FatalException(QualException):
    """致命异常"""

    def __init__(self, message: str, context: dict | None = None):
        super().__init__(message, ExceptionLevel.FATAL, context)


class WarningException(QualException):
    """警告异常"""

    def __init__(self, message: str, context: dict | None = None):
        super().__init__(message, ExceptionLevel.WARNING, context)


class RecoverableException(QualException):
    """可恢复异常"""

    def __init__(self, message: str, context: dict | None = None):
        super().__init__(message, ExceptionLevel.RECOVERABLE, context)


# ====================================================================
# 业务异常
# ====================================================================

class ModuleLoadException(FatalException):
    """模块加载异常"""


class ValidationException(FatalException):
    """验证异常"""


class ParameterException(FatalException):
    """参数异常"""


class ValuationException(FatalException):
    """估值异常"""


class ReviewException(FatalException):
    """审查异常"""


class GateCheckException(FatalException):
    """Gate检查异常"""


class DataInconsistencyException(WarningException):
    """数据不一致异常"""


class LLMTimeoutException(RecoverableException):
    """LLM超时异常"""


class NetworkException(RecoverableException):
    """网络异常"""


# ====================================================================
# 异常处理器
# ====================================================================

class ExceptionHandler:
    """异常处理器"""

    # 异常配置
    EXCEPTION_CONFIG: dict[str, ExceptionConfig] = {
        # 致命异常：阻断流程
        "ModuleLoadException": ExceptionConfig(
            level=ExceptionLevel.FATAL,
            description="模块加载失败"
        ),
        "ValidationException": ExceptionConfig(
            level=ExceptionLevel.FATAL,
            description="验证失败"
        ),
        "ParameterException": ExceptionConfig(
            level=ExceptionLevel.FATAL,
            description="参数错误"
        ),
        "ValuationException": ExceptionConfig(
            level=ExceptionLevel.FATAL,
            description="估值计算失败"
        ),
        "ReviewException": ExceptionConfig(
            level=ExceptionLevel.FATAL,
            description="审查失败"
        ),
        "GateCheckException": ExceptionConfig(
            level=ExceptionLevel.FATAL,
            description="Gate检查失败"
        ),

        # 警告异常：记录+继续
        "DataInconsistencyException": ExceptionConfig(
            level=ExceptionLevel.WARNING,
            alert=True,
            description="数据不一致"
        ),

        # 可恢复异常：重试
        "LLMTimeoutException": ExceptionConfig(
            level=ExceptionLevel.RECOVERABLE,
            max_retries=3,
            description="LLM超时"
        ),
        "NetworkException": ExceptionConfig(
            level=ExceptionLevel.RECOVERABLE,
            max_retries=3,
            description="网络错误"
        ),
    }

    # 异常分类决策树
    EXCEPTION_CLASSIFICATION = {
        "ImportError": ExceptionLevel.FATAL,
        "ValueError": ExceptionLevel.FATAL,
        "KeyError": ExceptionLevel.FATAL,
        "TypeError": ExceptionLevel.FATAL,
        "AttributeError": ExceptionLevel.FATAL,
        "TimeoutError": ExceptionLevel.RECOVERABLE,
        "ConnectionError": ExceptionLevel.RECOVERABLE,
        "RuntimeError": ExceptionLevel.FATAL,
        "PermissionError": ExceptionLevel.FATAL,
    }

    # 异常历史记录
    _exception_history: list[dict] = []

    @classmethod
    def handle(cls, exception: Exception, context: dict | None = None) -> any | None:
        """
        处理异常

        Args:
            exception: 异常对象
            context: 上下文信息

        Returns:
            None for FATAL (raises exception)
            None for WARNING (logs and continues)
            Result of fallback for RECOVERABLE
        """
        # 记录异常历史
        exception_record = {
            "type": type(exception).__name__,
            "message": str(exception),
            "context": context,
        }
        cls._exception_history.append(exception_record)

        # 首先检查是否为自定义异常
        if isinstance(exception, QualException):
            return cls._handle_qual_exception(exception, context)

        # 使用分类决策树
        exception_type = type(exception).__name__
        level = cls.EXCEPTION_CLASSIFICATION.get(exception_type, ExceptionLevel.FATAL)

        # 获取配置
        config = cls.EXCEPTION_CONFIG.get(exception_type)
        if config:
            level = config.level

        # 处理异常
        if level == ExceptionLevel.FATAL:
            logger.error(f"致命异常: {exception_type} - {exception}")
            raise FatalException(
                f"流程阻断: {exception_type} - {exception}",
                context=context
            ) from exception

        elif level == ExceptionLevel.WARNING:
            logger.warning(f"警告异常: {exception_type} - {exception}")
            if config and config.alert:
                cls._send_alert(exception_type, exception, context)
            return None

        elif level == ExceptionLevel.RECOVERABLE:
            logger.info(f"可恢复异常: {exception_type} - {exception}，尝试重试")
            max_retries = config.max_retries if config else 3

            for attempt in range(max_retries):
                try:
                    if config and config.fallback:
                        return config.fallback(context)
                    return None
                except Exception as retry_error:
                    logger.warning(f"重试{attempt + 1}失败: {retry_error}")

            # 重试失败，升级为致命异常
            logger.error(f"可恢复异常重试失败，升级为致命异常: {exception_type}")
            raise FatalException(
                f"流程阻断: {exception_type}（重试失败）",
                context=context
            ) from exception

        return None

    @classmethod
    def _handle_qual_exception(cls, exception: QualException,
                               context: dict | None = None) -> any | None:
        """处理自定义异常"""
        if exception.level == ExceptionLevel.FATAL:
            logger.error(f"致命异常: {exception}")
            raise exception

        elif exception.level == ExceptionLevel.WARNING:
            logger.warning(f"警告异常: {exception}")
            return None

        elif exception.level == ExceptionLevel.RECOVERABLE:
            logger.info(f"可恢复异常: {exception}")
            return None

        return None

    @classmethod
    def _send_alert(cls, exception_type: str, exception: Exception,
                    context: dict | None = None):
        """发送告警"""
        # 实现告警逻辑（邮件、钉钉等）
        logger.warning(f"告警: {exception_type} - {exception}")

    @classmethod
    def get_exception_history(cls) -> list[dict]:
        """获取异常历史"""
        return cls._exception_history.copy()

    @classmethod
    def clear_exception_history(cls):
        """清除异常历史"""
        cls._exception_history.clear()

    @classmethod
    def get_exception_stats(cls) -> dict:
        """获取异常统计"""
        stats = {
            "total": len(cls._exception_history),
            "by_type": {},
        }

        for record in cls._exception_history:
            exc_type = record["type"]
            stats["by_type"][exc_type] = stats["by_type"].get(exc_type, 0) + 1

        return stats
