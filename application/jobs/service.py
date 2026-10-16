"""任务入队用例：校验配额 → 落库 queued → 推入队列。

边界：
- 不在这里执行建库 / Playwright
- 不 import FastAPI
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from domain.jobs import JOB_KB_BUILD, STATUS_QUEUED, Job
from domain.ports import JobQueuePort, JobStorePort


class JobError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        # quota | invalid | not_found | forbidden
        self.code = code
        self.message = message


@dataclass(frozen=True)
class EnqueueResult:
    job_id: str
    status: str


class JobService:
    def __init__(
        self,
        store: JobStorePort,
        queue: JobQueuePort,
        *,
        max_active_per_tenant: int = 1,
    ) -> None:
        self._store = store
        self._queue = queue
        self._max_active = max_active_per_tenant

    def enqueue_kb_build(
        self,
        *,
        tenant_id: str,
        user_id: str,
        doc_dir: str,
    ) -> EnqueueResult:
        active = self._store.count_active(tenant_id, JOB_KB_BUILD)
        if active >= self._max_active:
            raise JobError("quota", "该租户已有进行中的建库任务，请稍后再试")

        job = Job(
            id=f"job_{uuid.uuid4().hex[:12]}",
            job_type=JOB_KB_BUILD,
            tenant_id=tenant_id,
            user_id=user_id,
            status=STATUS_QUEUED,
            message="queued",
            payload={"doc_dir": doc_dir},
        )
        self._store.create(job)
        # 先落库再入队：Worker 即使先抢到 id，也能查到行
        self._queue.enqueue(job.id)
        return EnqueueResult(job_id=job.id, status=job.status)

    def get_for_tenant(self, job_id: str, tenant_id: str) -> Job:
        job = self._store.get(job_id)
        if job is None or job.tenant_id != tenant_id:
            # 同文案，避免跨租户探测
            raise JobError("not_found", "任务不存在")
        return job
