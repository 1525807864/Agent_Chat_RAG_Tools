"""后台消费者：从队列取 job_id，查库，执行，回写状态。

启动示例（仓库根目录）::

    python -m worker.run_jobs

K8s 可用与 api 相同镜像，只改 command 为本模块。
"""

from __future__ import annotations

import logging
import time

from application.jobs.handlers_kb import run_kb_build
from config.settings import get_settings
from domain.jobs import JOB_KB_BUILD, STATUS_DEAD, STATUS_FAILED
from infrastructure.db.schema import ensure_all_schemas, mysql_reachable
from infrastructure.jobs.memory_job_store import MemoryJobStore
from infrastructure.jobs.mysql_job_store import MysqlJobStore
from infrastructure.jobs.redis_queue import MemoryJobQueue, RedisJobQueue
from domain.ports import JobQueuePort, JobStorePort

_log = logging.getLogger("nexora.worker")
MAX_ATTEMPTS = 3


def _build_backends() -> tuple[JobStorePort, JobQueuePort]:
    settings = get_settings()
    if mysql_reachable():
        store: JobStorePort = MysqlJobStore()
        try:
            queue: JobQueuePort = RedisJobQueue(settings.redis_url)
            return store, queue
        except Exception:  # noqa: BLE001
            _log.warning("Redis 不可用，Worker 使用 MemoryJobQueue", exc_info=True)
            return store, MemoryJobQueue()
    _log.warning("MySQL 不可用，Worker 使用内存存储（须与 API 同进程才可见任务）")
    return MemoryJobStore(), MemoryJobQueue()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    ensure_all_schemas()
    store, queue = _build_backends()
    _log.info(
        "worker 已启动 store=%s queue=%s",
        type(store).__name__,
        type(queue).__name__,
    )

    while True:
        try:
            job_id = queue.dequeue(timeout_sec=5)
        except Exception:  # noqa: BLE001
            _log.exception("dequeue 失败，稍后重试")
            time.sleep(2)
            continue
        if not job_id:
            continue
        if job_id == "__ping__":
            continue

        job = store.get(job_id)
        if job is None:
            _log.warning("丢弃未知 job_id=%s", job_id)
            continue

        job.attempts += 1
        job.mark_running()
        store.save(job)
        try:
            if job.job_type == JOB_KB_BUILD:
                run_kb_build(job, store)
            else:
                raise ValueError(f"未知 job_type={job.job_type}")
        except Exception as exc:  # noqa: BLE001
            _log.exception("job 失败 id=%s", job_id)
            job.error = str(exc)[:2000]
            if job.attempts >= MAX_ATTEMPTS:
                job.status = STATUS_DEAD
                job.message = "dead"
                store.save(job)
            else:
                job.status = STATUS_FAILED
                job.message = "failed"
                store.save(job)
                # 简单重试：再入队
                try:
                    queue.enqueue(job.id)
                except Exception:  # noqa: BLE001
                    _log.exception("重新入队失败 job_id=%s", job.id)


if __name__ == "__main__":
    main()
