"""JobQueuePort：Redis List（RPUSH / BLPOP）。"""

from __future__ import annotations

from typing import Optional

import redis

from domain.ports import JobQueuePort

QUEUE_KEY = "nexora:jobs:queue"


class RedisJobQueue(JobQueuePort):
    def __init__(self, redis_url: str) -> None:
        self._r = redis.Redis.from_url(redis_url, decode_responses=True)

    def enqueue(self, job_id: str) -> None:
        self._r.rpush(QUEUE_KEY, job_id)

    def dequeue(self, *, timeout_sec: int = 5) -> Optional[str]:
        # hiredis 在空队列阻塞到期时可能抛 TimeoutError，视为无任务
        try:
            item = self._r.blpop(QUEUE_KEY, timeout=timeout_sec)
        except Exception as exc:  # noqa: BLE001
            name = type(exc).__name__
            if "Timeout" in name or "timeout" in str(exc).lower():
                return None
            raise
        if not item:
            return None
        return item[1]


class MemoryJobQueue(JobQueuePort):
    """无 Redis 时的进程内队列（仅单进程 API+Worker 同机调试）。"""

    def __init__(self) -> None:
        from collections import deque
        from threading import Condition

        self._q: deque[str] = deque()
        self._cv = Condition()

    def enqueue(self, job_id: str) -> None:
        with self._cv:
            self._q.append(job_id)
            self._cv.notify()

    def dequeue(self, *, timeout_sec: int = 5) -> Optional[str]:
        with self._cv:
            if not self._q:
                self._cv.wait(timeout=timeout_sec)
            if not self._q:
                return None
            return self._q.popleft()
