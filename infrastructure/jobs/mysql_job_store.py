"""JobStorePort：MySQL 真相源。"""

from __future__ import annotations

import json
from typing import Any, Optional

from domain.jobs import Job
from domain.ports import JobStorePort


class MysqlJobStore(JobStorePort):
    def _connect(self):
        import pymysql
        from pymysql.cursors import DictCursor

        from api.auth.mysql_conn import mysql_kwargs

        return pymysql.connect(**mysql_kwargs(), cursorclass=DictCursor)

    def _row_to_job(self, row: dict[str, Any]) -> Job:
        payload = row.get("payload_json") or {}
        result = row.get("result_json") or {}
        if isinstance(payload, str):
            payload = json.loads(payload or "{}")
        if isinstance(result, str):
            result = json.loads(result or "{}")
        return Job(
            id=row["id"],
            job_type=row["job_type"],
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            status=row["status"],
            progress=int(row["progress"] or 0),
            message=row.get("message") or "",
            payload=payload if isinstance(payload, dict) else {},
            result=result if isinstance(result, dict) else {},
            error=row.get("error"),
            attempts=int(row.get("attempts") or 0),
        )

    def create(self, job: Job) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO jobs
                      (id, job_type, tenant_id, user_id, status, progress,
                       message, payload_json, attempts)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        job.id,
                        job.job_type,
                        job.tenant_id,
                        job.user_id,
                        job.status,
                        job.progress,
                        job.message,
                        json.dumps(job.payload, ensure_ascii=False),
                        job.attempts,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def get(self, job_id: str) -> Optional[Job]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM jobs WHERE id=%s", (job_id,))
                row = cur.fetchone()
            return self._row_to_job(row) if row else None
        finally:
            conn.close()

    def save(self, job: Job) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs SET
                      status=%s, progress=%s, message=%s,
                      payload_json=%s, result_json=%s, error=%s, attempts=%s,
                      started_at=IF(%s='running' AND started_at IS NULL, NOW(), started_at),
                      finished_at=IF(%s IN ('done','failed','dead'), NOW(), finished_at)
                    WHERE id=%s
                    """,
                    (
                        job.status,
                        job.progress,
                        job.message,
                        json.dumps(job.payload, ensure_ascii=False),
                        json.dumps(job.result, ensure_ascii=False),
                        job.error,
                        job.attempts,
                        job.status,
                        job.status,
                        job.id,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def count_active(self, tenant_id: str, job_type: str) -> int:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS c FROM jobs
                    WHERE tenant_id=%s AND job_type=%s
                      AND status IN ('queued','running')
                    """,
                    (tenant_id, job_type),
                )
                row = cur.fetchone() or {}
            return int(row.get("c") or 0)
        finally:
            conn.close()
