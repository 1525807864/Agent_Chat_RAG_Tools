"""P1: 单机内存版知识库构建 Job（异步）。商用可换成 Celery/RQ。"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Optional


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_jobs: dict[str, KbJob] = {}
_lock = asyncio.Lock()


async def enqueue_kb_build(app: Any, *, tenant_id: str, doc_dir: str) -> KbJob:
    """入队并后台执行 build_knowledge_base。"""
    job = KbJob(
        id=f"job_{uuid.uuid4().hex[:10]}",
        tenant_id=tenant_id,
        doc_dir=doc_dir,
    )
    async with _lock:
        _jobs[job.id] = job

    async def _run() -> None:
        job.status = "running"
        job.message = "building"
        job.progress = 10
        try:
            count = await asyncio.to_thread(
                app.build_knowledge_base,
                doc_dir,
                tenant_id,
            )
            job.chunk_count = int(count or 0)
            job.progress = 100
            job.status = "done"
            job.message = "ok"
        except Exception as e:  # noqa: BLE001
            job.status = "failed"
            job.error = str(e)
            job.message = "failed"
            job.progress = 100

    asyncio.create_task(_run())
    return job


def get_job(job_id: str) -> Optional[KbJob]:
    return _jobs.get(job_id)
