"""重试机制与熔断器

知识点:
1. 指数退避 (Exponential Backoff): 1s → 2s → 4s → 8s...
   + Jitter (随机抖动): 防止惊群效应 (多个客户端同时重试)
2. 熔断器 (Circuit Breaker) 三种状态:
   - CLOSED:   正常调用
   - OPEN:     熔断, 直接返回错误 (快速失败)
   - HALF_OPEN: 放一个请求试探, 成功则 CLOSED, 失败则 OPEN
3. 不是所有错误都适合重试 (400/401 不重试, 429/503 可以重试)
"""

import time
import random
import asyncio
from enum import Enum
from functools import wraps
from typing import Callable, TypeVar


F = TypeVar("F", bound=Callable)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """熔断器打开时抛出的异常"""
    pass


class CircuitBreaker:
    """熔断器"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_requests: int = 1,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_requests = half_open_max_requests

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0
        self.half_open_requests = 0

    def call(self, func: Callable, *args, **kwargs):
        """受熔断器保护的同步调用"""
        self._check_state()
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e

    async def async_call(self, func: Callable, *args, **kwargs):
        """受熔断器保护的异步调用"""
        self._check_state()
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e

    def _check_state(self):
        if self.state == CircuitState.OPEN:
            if time.monotonic() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_requests = 0
            else:
                remaining = self.recovery_timeout - (time.monotonic() - self.last_failure_time)
                raise CircuitBreakerOpenError(f"熔断器打开中, {remaining:.0f}s 后重试")

        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_requests >= self.half_open_max_requests:
                raise CircuitBreakerOpenError("半开状态已达试探上限, 请稍后重试")
            self.half_open_requests += 1

    def _on_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple = (Exception,),
):
    """同步重试装饰器 — 指数退避 + 随机抖动"""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        break
                    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                    if jitter:
                        delay *= 0.5 + random.random()
                    print(f"重试 {attempt + 1}/{max_retries}, {delay:.1f}s 后... ({e})")
                    time.sleep(delay)
            raise last_exception  # type: ignore
        return wrapper  # type: ignore
    return decorator


def async_retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
):
    """异步重试装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries:
                        break
                    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                    if jitter:
                        delay *= 0.5 + random.random()
                    print(f"重试 {attempt + 1}/{max_retries}, {delay:.1f}s 后... ({e})")
                    await asyncio.sleep(delay)
            raise last_exception
        return wrapper
    return decorator
