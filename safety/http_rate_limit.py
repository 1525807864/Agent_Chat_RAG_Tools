"""HTTP 层限流：Redis 滑动窗口；测式/本地可退回进程内内存。"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Protocol

from config.settings import get_settings


class HttpRateLimiter(Protocol):
    async def allow(self, key: str, limit: int, window_sec: int) -> bool: ...

    async def ping(self) -> None: ...

    async def close(self) -> None: ...


class MemoryHttpRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str, limit: int, window_sec: int) -> bool:
        async with self._lock:
            now = time.monotonic()
            cutoff = now - window_sec
            bucket = [t for t in self._hits.get(key, []) if t > cutoff]
            if len(bucket) >= limit:
                self._hits[key] = bucket
                return False
            bucket.append(now)
            self._hits[key] = bucket
            return True

    async def ping(self) -> None:
        return None

    async def close(self) -> None:
        async with self._lock:
            self._hits.clear()


class RedisHttpRateLimiter:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis

        self._redis = redis.from_url(url, decode_responses=True)

    async def allow(self, key: str, limit: int, window_sec: int) -> bool:
        now = time.time()
        member = f"{now}:{uuid.uuid4().hex}"
        redis_key = f"rl:{key}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(redis_key, 0, now - window_sec)
            pipe.zadd(redis_key, {member: now})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, window_sec + 1)
            results = await pipe.execute()
        count = int(results[2])
        return count <= limit

    async def ping(self) -> None:
        await self._redis.ping()

    async def close(self) -> None:
        await self._redis.aclose()


_limiter: HttpRateLimiter | None = None


async def init_http_rate_limiter() -> HttpRateLimiter:
    global _limiter
    if _limiter is not None:
        return _limiter
    settings = get_settings()
    if settings.rate_limit_backend == "redis":
        limiter: HttpRateLimiter = RedisHttpRateLimiter(settings.redis_url)
        await limiter.ping()
        _limiter = limiter
    else:
        _limiter = MemoryHttpRateLimiter()
    return _limiter


async def shutdown_http_rate_limiter() -> None:
    global _limiter
    if _limiter is not None:
        await _limiter.close()
        _limiter = None


async def allow_request(key: str, limit: int, window_sec: int = 60) -> bool:
    limiter = _limiter
    if limiter is None:
        limiter = await init_http_rate_limiter()
    return await limiter.allow(key, limit, window_sec)
