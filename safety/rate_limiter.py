"""速率限制器 — Token Bucket 算法实现

知识点:
1. Token Bucket: 桶里有 token, 每次请求消耗 n 个, 按固定速率补充, 桶空则拒绝
2. 滑动窗口 vs Token Bucket:
   - 滑动窗口: "N秒内最多M次", 边界处可能两倍突发
   - Token Bucket: 允许一定突发, 更平滑
3. AsyncRateLimiter: async 场景使用滑动窗口 + asyncio.Lock
"""

import time
import asyncio
from threading import Lock


class TokenBucketRateLimiter:
    """令牌桶速率限制器 (线程安全)"""

    def __init__(self, rate: int, capacity: int | None = None):
        self.rate = float(rate)
        self.capacity = float(capacity or rate)
        self.tokens = self.capacity
        self.last_refill = time.monotonic()
        self.lock = Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

    def acquire(self, tokens: int = 1) -> bool:
        with self.lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def wait_time(self, tokens: int = 1) -> float:
        with self.lock:
            self._refill()
            if self.tokens >= tokens:
                return 0.0
            return (tokens - self.tokens) / self.rate


class AsyncRateLimiter:
    """异步速率限制器 — 滑动窗口实现"""

    def __init__(self, max_requests: int, time_window: float = 60.0):
        self.max_requests = max_requests
        self.time_window = time_window
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self.time_window
            self._timestamps = [t for t in self._timestamps if t > cutoff]

            if len(self._timestamps) < self.max_requests:
                self._timestamps.append(now)
                return True
            return False

    async def wait_and_acquire(self) -> None:
        while not await self.acquire():
            await asyncio.sleep(0.1)

    @property
    def available(self) -> int:
        now = time.monotonic()
        cutoff = now - self.time_window
        valid = [t for t in self._timestamps if t > cutoff]
        return max(0, self.max_requests - len(valid))
