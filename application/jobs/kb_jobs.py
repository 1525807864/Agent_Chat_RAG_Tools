"""知识库异步 Job：进度回调 + 僵尸 running 清理。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Optional

from shared.timeutil import now_epoch

_log = logging.getLogger(__name__)


@dataclass
class KbJob:
    """建库任务状态。"""

    id: str
    tenant_id: str
    doc_dir: str
    status: str = "queued"  # queued|running|done|failed
    progress: int = 0
    message: str = ""
    chunk_count: int = 0
    error: Optional[str] = None
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def touch(self) -> None:
        self.updated_at = now_epoch()


_jobs: dict[str, KbJob] = {}
_lock = asyncio.Lock()


def _connect():
    import pymysql
    from pymysql.cursors import DictCursor

    from api.auth.mysql_conn import mysql_kwargs

    return pymysql.connect(**mysql_kwargs(), cursorclass=DictCursor)


def _save_job(job: KbJob) -> None:
    """写 MySQL；失败只保留内存。"""
    job.touch()
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO kb_jobs
                      (id, tenant_id, doc_dir, status, progress, message, chunk_count, error)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                      status=VALUES(status),
                      progress=VALUES(progress),
                      message=VALUES(message),
                      chunk_count=VALUES(chunk_count),
                      error=VALUES(error)
                    """,
                    (
                        job.id,
                        job.tenant_id,
                        job.doc_dir,
                        job.status,
                        job.progress,
                        job.message,
                        job.chunk_count,
                        job.error,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        _log.debug("kb_jobs MySQL 写入跳过: %s", e)


def _load_job_mysql(job_id: str) -> Optional[KbJob]:
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM kb_jobs WHERE id=%s", (job_id,))
                row = cur.fetchone()
            if not row:
                return None
            job = KbJob(
                id=row["id"],
                tenant_id=row["tenant_id"],
                doc_dir=row["doc_dir"],
                status=row["status"],
                progress=int(row["progress"] or 0),
                message=row["message"] or "",
                chunk_count=int(row["chunk_count"] or 0),
                error=row.get("error"),
            )
            job.touch()
            return job
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        _log.debug("kb_jobs MySQL 读取跳过: %s", e)
        return None


def fail_stale_running_jobs(*, max_age_seconds: int = 60) -> int:
    """启动 / reload 后清理僵尸 running 任务。

    - 内存：本进程里所有 running 一律 failed（旧 asyncio task 已随进程死亡）
    - MySQL：updated_at 过旧的 running → failed
    """
    n = 0
    for job in list(_jobs.values()):
        if job.status == "running":
            job.status = "failed"
            job.error = "进程重启，任务中断（请重新构建）"
            job.message = "failed"
            job.progress = 100
            _save_job(job)
            n += 1

    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE kb_jobs
                    SET status='failed',
                        message='failed',
                        error='任务超时或服务重启，请重新构建',
                        progress=100
                    WHERE status='running'
                      AND updated_at < (NOW(6) - INTERVAL %s SECOND)
                    """,
                    (int(max_age_seconds),),
                )
                n += int(cur.rowcount or 0)
            conn.commit()
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        _log.debug("fail_stale_running_jobs MySQL 跳过: %s", e)

    if n:
        _log.warning("已清理 %s 个僵尸 kb_jobs", n)
    return n


async def _run_safe(
    app: Any,
    job: KbJob,
    doc_dir: str,
    tenant_id: str,
    on_progress,
) -> None:
    job.status = "running"
    job.message = "starting"
    job.progress = 5
    _save_job(job)
    try:

        def _call() -> int:
            return int(
                app.build_knowledge_base(
                    doc_dir, tenant_id, on_progress=on_progress
                )
                or 0
            )

        count = await asyncio.to_thread(_call)
        job.chunk_count = count
        job.progress = 100
        job.status = "done"
        job.message = "ok"
    except Exception as e:  # noqa: BLE001
        job.status = "failed"
        job.error = str(e)
        job.message = "failed"
        job.progress = 100
    _save_job(job)


async def enqueue_kb_build(app: Any, *, tenant_id: str, doc_dir: str) -> KbJob:
    """入队并后台执行 build_knowledge_base（带阶段进度）。"""
    job = KbJob(
        id=f"job_{uuid.uuid4().hex[:10]}",
        tenant_id=tenant_id,
        doc_dir=doc_dir,
    )
    job.touch()
    async with _lock:
        _jobs[job.id] = job
    _save_job(job)

    def on_progress(pct: int, msg: str) -> None:
        job.progress = max(0, min(100, int(pct)))
        job.message = msg or job.message
        job.status = "running"
        _save_job(job)

    asyncio.create_task(_run_safe(app, job, doc_dir, tenant_id, on_progress))
    return job


def get_job(job_id: str) -> Optional[KbJob]:
    """先内存，再 MySQL（多实例 / 重启后）。"""
    cached = _jobs.get(job_id)
    if cached is not None:
        return cached
    loaded = _load_job_mysql(job_id)
    if loaded is not None:
        _jobs[job_id] = loaded
    return loaded
