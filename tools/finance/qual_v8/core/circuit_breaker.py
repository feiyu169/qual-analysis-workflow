"""
熔断器模块

实现熔断、半开、恢复机制
"""

import logging
import random
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"  # 正常状态
    OPEN = "open"  # 熔断状态
    HALF_OPEN = "half-open"  # 半开状态


class ErrorType(Enum):
    """错误类型"""
    TRANSIENT = "transient"  # 临时性错误
    PERMANENT = "permanent"  # 永久性错误
    BUSINESS = "business"  # 业务错误


class CircuitBreaker:
    """熔断器"""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        reset_timeout: int = 60,
        half_open_max_attempts: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_max_attempts = half_open_max_attempts

        self.failure_count = 0
        self.last_failure_time: datetime | None = None
        self.state = CircuitState.CLOSED
        self.half_open_attempts = 0

    def record_failure(self, error_type: ErrorType):
        """记录失败"""
        if error_type == ErrorType.PERMANENT:
            self.failure_count += 1
        elif error_type == ErrorType.TRANSIENT:
            self.failure_count += 0.5  # 临时性错误权重较低

        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"熔断器 {self.name} 打开：连续{self.failure_count}次失败")

    def record_success(self):
        """记录成功"""
        self.failure_count = 0
        self.half_open_attempts = 0
        self.state = CircuitState.CLOSED

    def can_execute(self) -> bool:
        """检查是否可以执行"""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # 检查冷却期是否已过
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed > self.reset_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_attempts = 0
                    logger.info(f"熔断器 {self.name} 半开：尝试恢复")
                    return True
            return False

        # half-open状态
        if self.half_open_attempts < self.half_open_max_attempts:
            self.half_open_attempts += 1
            return True
        return False

    def reset(self):
        """人工重置熔断器"""
        self.failure_count = 0
        self.half_open_attempts = 0
        self.state = CircuitState.CLOSED
        logger.info(f"熔断器 {self.name} 已人工重置")

    def get_state(self) -> CircuitState:
        """获取熔断器状态"""
        return self.state


def calculate_backoff(attempt: int, base_delay: int = 1, max_delay: int = 60) -> int:
    """计算指数退避延迟"""
    delay = min(base_delay * (2 ** attempt), max_delay)
    jitter = random.uniform(0, delay * 0.1)  # 添加抖动
    return int(delay + jitter)
