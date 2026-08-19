"""
quality/budget.py - 预算控制模块

职责分离：
- BudgetController: 软限制，可恢复的资源消耗控制
- CircuitBreaker: 硬阻断，系统保护熔断器
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from .exceptions import BudgetExceededError, CircuitOpenError

@dataclass
@dataclass
class BudgetController:
    """Budget controller - soft limit
    
    Tracks resource consumption and determines if execution can continue
    
    Attributes:
        total_time: Total time budget (seconds)
        total_llm_calls: Total LLM call budget
        total_tokens: Total token budget
        elapsed: Elapsed time
        llm_calls_used: LLM calls used
        tokens_used: Tokens used
        min_time_threshold: Minimum time threshold for can_proceed (seconds)
        min_tokens_threshold: Minimum tokens threshold for can_proceed
    """
    total_time: float = 900.0
    total_llm_calls: int = 20
    total_tokens: int = 100000
    elapsed: float = 0.0
    llm_calls_used: int = 0
    tokens_used: int = 0
    min_time_threshold: float = 30.0  # Minimum time threshold (seconds)
    min_tokens_threshold: int = 1000  # Minimum tokens threshold
    
    def remaining_time(self) -> float:
        """Remaining time"""
        return max(0, self.total_time - self.elapsed)
    
    def remaining_calls(self) -> int:
        """Remaining LLM calls"""
        return max(0, self.total_llm_calls - self.llm_calls_used)
    
    def remaining_tokens(self) -> int:
        """Remaining tokens"""
        return max(0, self.total_tokens - self.tokens_used)
    
    def can_proceed(self) -> bool:
        """Check if can continue"""
        return (self.remaining_time() > self.min_time_threshold
                and self.remaining_calls() > 0
                and self.remaining_tokens() > self.min_tokens_threshold)
    
    def consume(self, time_delta: float, calls: int = 0, tokens: int = 0) -> bool:
        """消耗预算
        
        Args:
            time_delta: 消耗的时间（秒）
            calls: 消耗的LLM调用次数
            tokens: 消耗的token数
            
        Returns:
            bool: 是否消耗成功
        """
        if not self.can_proceed():
            return False
        self.elapsed += time_delta
        self.llm_calls_used += calls
        self.tokens_used += tokens
        return True
    
    def consume_or_raise(self, time_delta: float, calls: int = 0, tokens: int = 0) -> None:
        """消耗预算，不足时抛出异常
        
        Raises:
            BudgetExceededError: 预算耗尽
        """
        if not self.consume(time_delta, calls, tokens):
            raise BudgetExceededError(
                message="推理预算耗尽",
                budget_info={
                    "remaining_time": self.remaining_time(),
                    "remaining_calls": self.remaining_calls(),
                    "remaining_tokens": self.remaining_tokens(),
                }
            )
    
    def get_status(self) -> dict:
        """获取预算状态"""
        return {
            "total_time": self.total_time,
            "total_llm_calls": self.total_llm_calls,
            "total_tokens": self.total_tokens,
            "elapsed": self.elapsed,
            "llm_calls_used": self.llm_calls_used,
            "tokens_used": self.tokens_used,
            "remaining_time": self.remaining_time(),
            "remaining_calls": self.remaining_calls(),
            "remaining_tokens": self.remaining_tokens(),
            "can_proceed": self.can_proceed(),
        }


class CircuitBreaker:
    """Circuit breaker - hard block, system protection
    
    When consecutive failures reach threshold, triggers circuit breaker to block subsequent calls
    
    States:
        CLOSED: Normal state, allows calls
        OPEN: Circuit broken, blocks calls
        HALF_OPEN: Half-open state, allows probe calls
    
    State machine: CLOSED -> OPEN -> HALF_OPEN -> CLOSED
    """
    
    def __init__(
        self, 
        failure_threshold: int = 3, 
        recovery_timeout: float = 60.0,
        half_open_max_probes: int = 3  # HALF_OPEN max probe count
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_probes = half_open_max_probes
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.half_open_probe_count = 0  # HALF_OPEN probe count
    
    def record_failure(self) -> None:
        """Record failure"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.state == "HALF_OPEN":
            self.half_open_probe_count += 1
            if self.half_open_probe_count >= self.half_open_max_probes:
                self.state = "OPEN"  # Probe failed, back to OPEN
        elif self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
    
    def record_success(self) -> None:
        """Record success"""
        self.failure_count = 0
        self.half_open_probe_count = 0
        self.state = "CLOSED"
    
    def is_open(self) -> bool:
        """Check if circuit is open"""
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
                self.half_open_probe_count = 0
                return False
            return True
        elif self.state == "HALF_OPEN":
            # HALF_OPEN state allows probing
            return False
        return False
    
    def check_or_raise(self) -> None:
        """检查熔断状态，熔断时抛出异常
        
        Raises:
            CircuitOpenError: 熔断器已触发
        """
        if self.is_open():
            raise CircuitOpenError(
                message="熔断器已触发",
                failure_count=self.failure_count
            )
    
    def get_status(self) -> dict:
        """Get circuit breaker status"""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "last_failure_time": self.last_failure_time,
            "is_open": self.is_open(),
            "half_open_max_probes": self.half_open_max_probes,
            "half_open_probe_count": self.half_open_probe_count,
        }


@dataclass
class ReasoningBudget:
    """推理预算 - 组合BudgetController和CircuitBreaker
    
    提供统一的预算管理接口
    """
    budget: BudgetController = field(default_factory=BudgetController)
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    
    def can_proceed(self) -> bool:
        """检查是否可以继续"""
        return self.budget.can_proceed() and not self.circuit_breaker.is_open()
    
    def consume(self, time_delta: float, calls: int = 0, tokens: int = 0) -> bool:
        """消耗预算"""
        if not self.can_proceed():
            return False
        return self.budget.consume(time_delta, calls, tokens)
    
    def consume_or_raise(self, time_delta: float, calls: int = 0, tokens: int = 0) -> None:
        """消耗预算，不足时抛出异常"""
        self.circuit_breaker.check_or_raise()
        self.budget.consume_or_raise(time_delta, calls, tokens)
    
    def record_failure(self) -> None:
        """记录失败"""
        self.circuit_breaker.record_failure()
    
    def record_success(self) -> None:
        """记录成功"""
        self.circuit_breaker.record_success()
    
    def get_status(self) -> dict:
        """获取预算状态"""
        return {
            "budget": self.budget.get_status(),
            "circuit_breaker": self.circuit_breaker.get_status(),
            "can_proceed": self.can_proceed(),
        }
