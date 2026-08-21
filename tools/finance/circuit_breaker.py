#!/usr/bin/env python3
# NOTE: Copied from investment/ package (2026-06-30)
# Source: ~/.hermes/tools/investment/circuit_breaker.py
# Update: 当 investment/ 更新时，需同步更新此文件
"""熔断器 — 线程安全版

V5.0 特性:
- 每实例 threading.Lock
- can_execute() 无副作用（状态转换在锁内完成）
- half_open 计数在锁内递增，防止并发超限
- 双重检查锁的全局注册表
"""

import logging
import threading
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"      # 正常状态，允许请求
    OPEN = "open"          # 熔断状态，拒绝请求
    HALF_OPEN = "half_open"  # 半开状态，允许少量请求


class CircuitBreaker:
    """熔断器（线程安全）"""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: datetime | None = None
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def can_execute(self) -> bool:
        """检查是否允许执行（无副作用，状态转换在锁内完成）"""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                if self._last_failure_time:
                    elapsed = datetime.now() - self._last_failure_time
                    if elapsed > timedelta(seconds=self.recovery_timeout):
                        self._state = CircuitState.HALF_OPEN
                        self._half_open_calls = 0
                        logger.info(f"CircuitBreaker {self.name}: OPEN -> HALF_OPEN")
                        # 进入半开状态后，立即递增计数并允许
                        self._half_open_calls += 1
                        return True
                return False

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    # 在锁内递增计数，防止并发超限
                    self._half_open_calls += 1
                    return True
                return False

            return False

    def record_success(self):
        """记录成功"""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                # 半开状态下的成功：如果累积足够成功，关闭熔断器
                if self._half_open_calls >= self.half_open_max_calls:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    logger.info(f"CircuitBreaker {self.name}: HALF_OPEN -> CLOSED")
            else:
                self._failure_count = 0

    def record_failure(self):
        """记录失败"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now()

            if self._state == CircuitState.HALF_OPEN:
                # 半开状态下的失败：立即打开
                self._state = CircuitState.OPEN
                self._half_open_calls = 0
                logger.warning(f"CircuitBreaker {self.name}: HALF_OPEN -> OPEN")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"CircuitBreaker {self.name}: CLOSED -> OPEN "
                    f"(failures={self._failure_count})"
                )

    def get_status(self) -> dict[str, Any]:
        """获取状态"""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "last_failure_time": (
                    self._last_failure_time.isoformat()
                    if self._last_failure_time else None
                ),
                "half_open_calls": self._half_open_calls,
                "half_open_max_calls": self.half_open_max_calls,
            }

    def reset(self):
        """重置熔断器"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0
            self._last_failure_time = None


# 全局熔断器注册表（线程安全）
_breaker_lock = threading.Lock()
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    """获取或创建熔断器（双重检查锁）"""
    if name not in _circuit_breakers:
        with _breaker_lock:
            if name not in _circuit_breakers:
                _circuit_breakers[name] = CircuitBreaker(name, **kwargs)
    return _circuit_breakers[name]


def with_circuit_breaker(name: str):
    """熔断器装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            cb = get_circuit_breaker(name)
            if not cb.can_execute():
                return {
                    "error": True,
                    "circuit_breaker": name,
                    "state": cb.state.value,
                    "message": f"熔断器 {name} 已打开，拒绝请求",
                }
            try:
                result = func(*args, **kwargs)
                cb.record_success()
                return result
            except Exception:
                cb.record_failure()
                raise
        return wrapper
    return decorator
