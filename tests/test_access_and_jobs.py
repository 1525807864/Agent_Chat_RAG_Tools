"""租户权限矩阵与任务入队（内存后端，不依赖 MySQL）。"""

from __future__ import annotations

import pytest

from application.access.service import AccessError, AccessService
from application.jobs.service import JobError, JobService
from domain.access import (
    PERM_KB_WRITE,
    PERM_OPS_ASK,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROLE_VIEWER,
    TenantMember,
)
from infrastructure.access.memory_member_store import MemoryMemberStore
from infrastructure.jobs.memory_job_store import MemoryJobStore
from infrastructure.jobs.redis_queue import MemoryJobQueue


def test_owner_can_write_kb_viewer_cannot():
    store = MemoryMemberStore()
    svc = AccessService(store)
    store.ensure_owner("t1", "alice")
    store.upsert(
        TenantMember(tenant_id="t1", user_id="bob", role=ROLE_VIEWER),
        invited_by="alice",
    )
    svc.require("t1", "alice", PERM_KB_WRITE)
    with pytest.raises(AccessError) as ei:
        svc.require("t1", "bob", PERM_KB_WRITE)
    assert ei.value.code == "forbidden"


def test_member_cannot_ops_ask():
    store = MemoryMemberStore()
    svc = AccessService(store)
    store.upsert(
        TenantMember(tenant_id="t1", user_id="m1", role=ROLE_MEMBER)
    )
    with pytest.raises(AccessError):
        svc.require("t1", "m1", PERM_OPS_ASK)


def test_enqueue_kb_quota():
    jobs = MemoryJobStore()
    q = MemoryJobQueue()
    svc = JobService(jobs, q, max_active_per_tenant=1)
    a = svc.enqueue_kb_build(tenant_id="t1", user_id="u1", doc_dir="data/x")
    assert a.status == "queued"
    assert q.dequeue(timeout_sec=1) == a.job_id
    # 上面 dequeue 后仍算 queued 在库里 → 再入队应触发配额
    with pytest.raises(JobError) as ei:
        svc.enqueue_kb_build(tenant_id="t1", user_id="u1", doc_dir="data/x")
    assert ei.value.code == "quota"


def test_get_job_hides_other_tenant():
    jobs = MemoryJobStore()
    q = MemoryJobQueue()
    svc = JobService(jobs, q)
    enq = svc.enqueue_kb_build(tenant_id="t1", user_id="u1", doc_dir="d")
    with pytest.raises(JobError) as ei:
        svc.get_for_tenant(enq.job_id, "other")
    assert ei.value.code == "not_found"


def test_maybe_bootstrap_only_when_empty():
    store = MemoryMemberStore()
    svc = AccessService(store)
    m = svc.maybe_bootstrap_owner_on_login("t1", "alice")
    assert m is not None and m.role == ROLE_OWNER
    store.upsert(
        TenantMember(tenant_id="t1", user_id="bob", role=ROLE_MEMBER),
        invited_by="alice",
    )
    assert svc.maybe_bootstrap_owner_on_login("t1", "carol") is None
