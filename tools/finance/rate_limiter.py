"""
Rate Limiter - 速率限制器

SEC EDGAR 合规要求:
- SEC: 10 req/sec
- 巨潮/披露易: 5 req/sec

使用滑动窗口算法实现线程安全的速率限制。
"""

import time
import threading
import logging
from collections import deque
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    """速率限制器 - 滑动窗口算法

    Args:
        max_requests: 时间窗口内最大请求数
        time_window: 时间窗口（秒）
        name: 限制器名称（用于日志）
    """

    def __init__(self, max_requests: int = 10, time_window: float = 1.0, name: str = "default"):
        self.max_requests = max_requests
        self.time_window = time_window
        self.name = name
        self.requests: deque[float] = deque()
        self.lock = threading.Lock()
        self._total_wait_time: float = 0.0
        self._total_requests: int = 0

    def acquire(self) -> float:
        """获取请求许可

        如果当前窗口内请求数已达上限，阻塞等待直到有空位。

        Returns:
            实际等待时间（秒）
        """
        with self.lock:
            now = time.time()

            # 清理过期请求
            while self.requests and self.requests[0] < now - self.time_window:
                self.requests.popleft()

            wait_time = 0.0

            # 检查是否超过限制
            if len(self.requests) >= self.max_requests:
                # 计算需要等待的时间
                wait_time = self.requests[0] + self.time_window - now
                if wait_time > 0:
                    logger.debug(f"[{self.name}] 速率限制: 等待 {wait_time:.3f}s")
                    time.sleep(wait_time)
                    self._total_wait_time += wait_time

            # 记录请求
            self.requests.append(time.time())
            self._total_requests += 1

            return wait_time

    @contextmanager
    def throttle(self):
        """上下文管理器方式使用速率限制

        Usage:
            with rate_limiter.throttle():
                make_request()
        """
        self.acquire()
        yield

    @property
    def stats(self) -> dict:
        """获取统计信息"""
        return {
            "name": self.name,
            "max_requests": self.max_requests,
            "time_window": self.time_window,
            "total_requests": self._total_requests,
            "total_wait_time": round(self._total_wait_time, 3),
            "current_window_requests": len(self.requests),
        }

    def reset(self):
        """重置限制器状态"""
        with self.lock:
            self.requests.clear()
            self._total_wait_time = 0.0
            self._total_requests = 0


# ─── 全局速率限制器实例 ───

# SEC EDGAR: 10 requests per second
SEC_RATE_LIMITER = RateLimiter(max_requests=10, time_window=1.0, name="SEC")

# 巨潮资讯: 5 requests per second
CNINFO_RATE_LIMITER = RateLimiter(max_requests=5, time_window=1.0, name="CNInfo")

# 披露易: 5 requests per second
HKEX_RATE_LIMITER = RateLimiter(max_requests=5, time_window=1.0, name="HKEX")


def get_rate_limiter(source: str) -> Optional[RateLimiter]:
    """根据数据源获取对应的速率限制器

    Args:
        source: 数据源标识 (sec/cninfo/hkex)

    Returns:
        对应的速率限制器，未找到返回 None
    """
    limiters = {
        "sec": SEC_RATE_LIMITER,
        "cninfo": CNINFO_RATE_LIMITER,
        "hkex": HKEX_RATE_LIMITER,
    }
    return limiters.get(source.lower())
