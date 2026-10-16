"""组装 JobService。"""

from __future__ import annotations

from application.jobs.service import JobService
from config.settings import get_settings
from infrastructure.db.schema import mysql_reachable
from infrastructure.jobs.memory_job_store import MemoryJobStore
from infrastructure.jobs.mysql_job_store import MysqlJobStore
from infrastructure.jobs.redis_queue import MemoryJobQueue, RedisJobQueue
from utils.logger import get_logger

_log = get_logger("nexora.jobs.factory")
_svc: JobService | None = None
_mem_store: MemoryJobStore | None = None
_mem_queue: MemoryJobQueue | None = None


def get_job_service() -> JobService:
    """优先 MySQL + Redis；不可用时回退内存（仅单进程联调）。"""
    global _svc, _mem_store, _mem_queue
    if _svc is None:
        settings = get_settings()
        if mysql_reachable():
            store: MysqlJobStore | MemoryJobStore = MysqlJobStore()
            try:
                queue: RedisJobQueue | MemoryJobQueue = RedisJobQueue(
                    settings.redis_url
                )
            except Exception:  # noqa: BLE001
                _log.warning("Redis 队列初始化失败，回退 MemoryJobQueue", exc_info=True)
                if _mem_queue is None:
                    _mem_queue = MemoryJobQueue()
                queue = _mem_queue
            _log.info(
                "JobService store=MysqlJobStore queue=%s", type(queue).__name__
            )
        else:
            if _mem_store is None:
                _mem_store = MemoryJobStore()
            if _mem_queue is None:
                _mem_queue = MemoryJobQueue()
            store = _mem_store
            queue = _mem_queue
            _log.warning(
                "MySQL 不可用，JobService 使用内存（API 与 Worker 须同进程）"
            )
        _svc = JobService(store, queue, max_active_per_tenant=1)
    return _svc


def reset_job_service_for_tests() -> None:
    global _svc, _mem_store, _mem_queue
    _svc = None
    _mem_store = None
    _mem_queue = None
