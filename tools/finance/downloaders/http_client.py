"""HTTP客户端封装。

提供：
- 连接池复用
- 指数退避重试
- 速率限制
- 统一错误处理
- 可注入sleep函数（测试用）
- 条件GET（304 Not Modified）

与Dayu对齐：
- httpx.Client
- 重试机制（指数退避）
- 限流控制（_throttle_before_request）
- sleep注入（sleep_func）
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Optional

import httpx

from .models import DownloaderError

logger = logging.getLogger(__name__)

# ============ 默认配置 ============

DEFAULT_USER_AGENT: str = "Hermes-Agent/1.0 (investment-analysis)"
DEFAULT_REQUEST_TIMEOUT: float = 30.0
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_SLEEP_SECONDS: float = 0.3
RETRY_BACKOFF_BASE: float = 0.8

# ============ HTTP客户端类 ============

class HttpClient:
    """封装HTTP请求，提供重试、限流、错误处理。
    
    对应Dayu的httpx.Client封装。
    
    Attributes:
        _client: httpx.Client实例
        _max_retries: 最大重试次数
        _sleep_seconds: 请求间隔
        _last_request_at: 上次请求时间（monotonic clock）
        _sleep_func: 可注入的sleep函数（测试用）
    """
    
    def __init__(
        self,
        *,
        client: Optional[httpx.Client] = None,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
        sleep_func: Optional[Callable[[float], None]] = None,
    ) -> None:
        """初始化HTTP客户端。
        
        Args:
            client: 可注入的httpx.Client（测试用）
            user_agent: User-Agent
            timeout: 请求超时（秒）
            max_retries: 最大重试次数
            sleep_seconds: 请求间隔（秒）
            sleep_func: 可注入的sleep函数（测试用，可传lambda _: None跳过等待）
            
        Raises:
            ValueError: max_retries <= 0 或 sleep_seconds < 0
        """
        if max_retries <= 0:
            raise ValueError("max_retries 必须大于 0")
        if sleep_seconds < 0:
            raise ValueError("sleep_seconds 不能为负数")
        
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent},
        )
        self._max_retries = max_retries
        self._sleep_seconds = sleep_seconds
        self._last_request_at: Optional[float] = None
        self._sleep_func: Callable[[float], None] = (
            sleep_func if sleep_func is not None else time.sleep
        )
    
    def close(self) -> None:
        """关闭底层HTTP客户端。"""
        if self._owns_client:
            self._client.close()
    
    def get_json(
        self,
        url: str,
        *,
        params: Optional[dict[str, str]] = None,
    ) -> Any:
        """GET请求并解析JSON响应。
        
        对应Dayu的_http_get_json。
        
        Args:
            url: 请求URL
            params: 查询参数
            
        Returns:
            解析后的JSON对象
            
        Raises:
            DownloaderError: 重试后仍失败
        """
        last_exc: Optional[Exception] = None
        
        for attempt in range(self._max_retries):
            try:
                self._throttle()
                try:
                    response = self._client.get(url, params=params)
                    response.raise_for_status()
                    return response.json()
                finally:
                    self._mark_request_finished()
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last_exc = exc
                logger.warning(f"请求失败 (attempt {attempt + 1}): {url} -> {exc}")
                self._backoff(attempt)
        
        raise DownloaderError(f"GET JSON失败: url={url} error={last_exc}")
    
    def get_bytes(
        self,
        url: str,
        *,
        follow_redirects: bool = True,
    ) -> bytes:
        """GET请求并返回字节内容。
        
        对应Dayu的_http_download_bytes。
        
        Args:
            url: 请求URL
            follow_redirects: 是否跟随重定向
            
        Returns:
            响应字节
            
        Raises:
            DownloaderError: 重试后仍失败
        """
        last_exc: Optional[Exception] = None
        
        for attempt in range(self._max_retries):
            try:
                self._throttle()
                try:
                    response = self._client.get(url, follow_redirects=follow_redirects)
                    response.raise_for_status()
                    return response.content
                finally:
                    self._mark_request_finished()
            except httpx.HTTPError as exc:
                last_exc = exc
                logger.warning(f"下载失败 (attempt {attempt + 1}): {url} -> {exc}")
                self._backoff(attempt)
        
        raise DownloaderError(f"下载失败: url={url} error={last_exc}")
    
    def get_bytes_conditional(
        self,
        url: str,
        *,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        follow_redirects: bool = True,
    ) -> tuple[int, Optional[bytes]]:
        """条件GET请求，支持304 Not Modified。
        
        对应Dayu的条件下载逻辑。
        
        Args:
            url: 请求URL
            etag: If-None-Match头
            last_modified: If-Modified-Since头
            follow_redirects: 是否跟随重定向
            
        Returns:
            (status_code, content)
            - 200: (200, bytes)
            - 304: (304, None)
            
        Raises:
            DownloaderError: 重试后仍失败（非304/200）
        """
        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        
        last_exc: Optional[Exception] = None
        
        for attempt in range(self._max_retries):
            try:
                self._throttle()
                try:
                    response = self._client.get(
                        url,
                        headers=headers,
                        follow_redirects=follow_redirects,
                    )
                    
                    # 304 Not Modified
                    if response.status_code == 304:
                        return 304, None
                    
                    response.raise_for_status()
                    return response.status_code, response.content
                finally:
                    self._mark_request_finished()
            except httpx.HTTPError as exc:
                last_exc = exc
                logger.warning(f"条件下载失败 (attempt {attempt + 1}): {url} -> {exc}")
                self._backoff(attempt)
        
        raise DownloaderError(f"条件下载失败: url={url} error={last_exc}")
    
    def head(
        self,
        url: str,
        *,
        follow_redirects: bool = True,
    ) -> dict[str, Optional[str]]:
        """HEAD请求获取元数据。
        
        对应Dayu的_http_head_meta。
        
        Args:
            url: 请求URL
            follow_redirects: 是否跟随重定向
            
        Returns:
            包含content_length, etag, last_modified的字典
        """
        try:
            self._throttle()
            try:
                response = self._client.head(url, follow_redirects=follow_redirects)
                response.raise_for_status()
            finally:
                self._mark_request_finished()
        except httpx.HTTPError as exc:
            logger.warning(f"HEAD失败: url={url} error={exc}")
            return {
                "content_length": None,
                "etag": None,
                "last_modified": None,
            }
        
        raw_length = response.headers.get("Content-Length")
        try:
            content_length = str(int(raw_length)) if raw_length is not None else None
        except (TypeError, ValueError):
            content_length = None
        
        return {
            "content_length": content_length,
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
        }
    
    def post_form(
        self,
        url: str,
        *,
        data: dict[str, str],
    ) -> Any:
        """POST表单请求并解析JSON响应。
        
        对应Dayu的_http_post_form。
        
        Args:
            url: 请求URL
            data: 表单数据
            
        Returns:
            解析后的JSON对象
            
        Raises:
            DownloaderError: 重试后仍失败
        """
        last_exc: Optional[Exception] = None
        
        for attempt in range(self._max_retries):
            try:
                self._throttle()
                try:
                    response = self._client.post(url, data=data)
                    response.raise_for_status()
                    return response.json()
                finally:
                    self._mark_request_finished()
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last_exc = exc
                logger.warning(f"POST失败 (attempt {attempt + 1}): {url} -> {exc}")
                self._backoff(attempt)
        
        raise DownloaderError(f"POST失败: url={url} error={last_exc}")
    
    def _throttle(self) -> None:
        """请求限流，确保请求间隔。
        
        对应Dayu的_throttle_before_request。
        """
        now = time.monotonic()
        if self._sleep_seconds > 0 and self._last_request_at is not None:
            elapsed = now - self._last_request_at
            remaining = self._sleep_seconds - elapsed
            if remaining > 0:
                self._sleep_func(remaining)
    
    def _mark_request_finished(self) -> None:
        """记录请求完成时间。
        
        对应Dayu的_mark_request_finished。
        """
        self._last_request_at = time.monotonic()
    
    def _backoff(self, attempt: int) -> None:
        """指数退避。
        
        对应Dayu的_retry_backoff。
        
        Args:
            attempt: 当前重试序号（0-based）
        """
        if attempt >= self._max_retries - 1:
            return
        
        delay = RETRY_BACKOFF_BASE * (2 ** attempt)
        logger.debug(f"退避 {delay:.1f}s (attempt {attempt + 1})")
        self._sleep_func(delay)
