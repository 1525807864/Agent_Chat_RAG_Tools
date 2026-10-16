"""进程内 Job 存储：无 MySQL 时与 MemoryQueue 搭配（单机开发）。"""

from __future__ import annotations

from threading import Lock
from typing import Optional

from domain.jobs import Job, STATUS_QUEUED, STATUS_RUNNING
from domain.ports import JobStorePort


class MemoryJobStore(JobStorePort):
    def __init__(self) -> None:
        self._lock = Lock()
        self._jobs: dict[str, Job] = {}

    def create(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def save(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def count_active(self, tenant_id: str, job_type: str) -> int:
        with self._lock:
            return sum(
                1
                for j in self._jobs.values()
                if j.tenant_id == tenant_id
                and j.job_type == job_type
                and j.status in (STATUS_QUEUED, STATUS_RUNNING)
            )
