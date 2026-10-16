"""知识库建库任务处理器（供 Worker 调用，不经过 HTTP）。"""

from __future__ import annotations

import logging

from domain.jobs import Job
from domain.ports import JobStorePort

_log = logging.getLogger("nexora.jobs.kb")


def run_kb_build(job: Job, store: JobStorePort) -> None:
    """执行 build_knowledge_base，并把进度写回 JobStore。"""
    from application.services.agent_application import AgentApplication

    doc_dir = str((job.payload or {}).get("doc_dir") or "").strip()
    if not doc_dir:
        raise ValueError("payload.doc_dir 为空")

    app = AgentApplication()

    def on_progress(pct: int, msg: str) -> None:
        job.mark_progress(pct, msg or "")
        job.status = "running"
        store.save(job)

    _log.info(
        "开始建库 job_id=%s tenant=%s doc_dir=%s",
        job.id,
        job.tenant_id,
        doc_dir,
    )
    count = int(
        app.build_knowledge_base(
            doc_dir, tenant_id=job.tenant_id, on_progress=on_progress
        )
        or 0
    )
    job.mark_done({"chunk_count": count})
    store.save(job)
    _log.info("建库完成 job_id=%s chunks=%s", job.id, count)
