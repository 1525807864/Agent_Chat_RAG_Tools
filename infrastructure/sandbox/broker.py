"""Sandbox Broker：申请 / 执行 / 回收。

所有垂直 Agent 只许走这里。会话策略在 acquire 时固化；
Permission（capability/approval）与 Enforcement（docker/egress）分离。
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from application.tenancy import sanitize_tenant_id
from config.settings import get_settings
from infrastructure.sandbox.audit import log_exec, log_lifecycle
from infrastructure.sandbox.command_risk import assess_risk
from infrastructure.sandbox.docker_runtime import DockerSandboxRuntime
from infrastructure.sandbox.egress_proxy import ensure_egress_proxy
from infrastructure.sandbox.models import (
    ExecRequest,
    ExecResult,
    SandboxLimits,
    SandboxSession,
)
from infrastructure.sandbox.policy import (
    assert_exec_kind,
    assert_mode_allows_write,
    build_policy_snapshot,
    need_proxy_network,
    resolve_capabilities,
)
from infrastructure.sandbox.session_store import (
    delete_session_meta,
    save_session,
)
from infrastructure.sandbox import workspace_fs
from shared.errors import AppError, ErrorCode
from shared.path_security import get_project_root
from shared.timeutil import now_iso


class SandboxBroker:
    """进程内沙箱编排器。"""

    def __init__(self) -> None:
        s = get_settings()
        self._rt = DockerSandboxRuntime(
            image=s.sandbox_image,
            default_network=s.sandbox_network,
        )
        self._sessions: dict[str, SandboxSession] = {}
        self._lock = asyncio.Lock()
        self._limits = SandboxLimits(
            memory=s.sandbox_memory,
            cpus=str(s.sandbox_cpus),
            pids=s.sandbox_pids,
            exec_timeout_sec=s.sandbox_exec_timeout_sec,
            max_output_bytes=s.sandbox_max_output_bytes,
            idle_sec=s.sandbox_idle_sec,
        )

    def restore(self, sess: SandboxSession) -> None:
        """reaper 启动时把落盘会话装回内存。"""
        if sess.status == "running" and sess.id not in self._sessions:
            self._sessions[sess.id] = sess

    async def acquire(
        self,
        *,
        tenant_id: str,
        vertical: str = "generic",
        extra_caps: frozenset[str] | None = None,
    ) -> SandboxSession:
        if not get_settings().sandbox_enabled:
            raise AppError(
                ErrorCode.SANDBOX_UNAVAILABLE,
                "沙箱未启用（请设置 SANDBOX_ENABLED=true）",
                http_status=503,
            )
        tenant = sanitize_tenant_id(tenant_id)
        try:
            caps = resolve_capabilities(vertical, extra_caps)
        except ValueError as exc:
            raise AppError(ErrorCode.VALIDATION, str(exc), http_status=400) from exc

        policy = build_policy_snapshot()
        # 0 = 不限制并发（本地调试用）
        max_sess = int(get_settings().sandbox_max_sessions_per_tenant)
        if max_sess > 0:
            async with self._lock:
                alive = [
                    s
                    for s in self._sessions.values()
                    if s.tenant_id == tenant and s.status == "running"
                ]
            if len(alive) >= max_sess:
                raise AppError(
                    ErrorCode.SANDBOX_DENIED,
                    "超过租户沙箱并发上限",
                    http_status=429,
                )

        sid = uuid4().hex[:12]
        ws = (
            get_project_root()
            / get_settings().sandbox_workspace_host
            / tenant
            / sid
        )
        proxy_url = ""
        net = "none"
        if need_proxy_network(policy, caps):
            proxy = await ensure_egress_proxy(
                get_settings().sandbox_egress_proxy_port,
                policy.egress_allowlist,
            )
            proxy_url = f"http://host.docker.internal:{proxy.port}"
            net = "bridge"

        try:
            cid = await self._rt.create(
                session_id=sid,
                tenant_id=tenant,
                caps=caps,
                limits=self._limits,
                workspace_host=str(ws),
                network=net,
                proxy_url=proxy_url,
            )
        except Exception as exc:  # noqa: BLE001
            import logging

            logging.getLogger("nexora.sandbox").exception(
                "sandbox.create failed session=%s tenant=%s image=%s ws=%s err=%s",
                sid,
                tenant,
                get_settings().sandbox_image,
                ws,
                exc,
            )
            raise AppError(
                ErrorCode.SANDBOX_UNAVAILABLE,
                "沙箱启动失败，请确认 Docker 与镜像已就绪",
                http_status=503,
                internal=str(exc)[:400],
            ) from exc

        now = now_iso()
        sess = SandboxSession(
            id=sid,
            tenant_id=tenant,
            vertical=(vertical or "generic").strip().lower(),
            capabilities=caps,
            container_id=cid,
            workspace_host=str(ws),
            created_at=now,
            last_active_at=now,
            limits=self._limits,
            policy=policy,
        )
        async with self._lock:
            self._sessions[sid] = sess
        save_session(sess)
        log_lifecycle("acquire", tenant=tenant, session=sid, vertical=sess.vertical)
        return sess

    async def exec(self, req: ExecRequest) -> ExecResult:
        sess = await self._get_owned(req.session_id, req.tenant_id)
        try:
            assert_exec_kind(sess.capabilities, req.kind)
            assert_mode_allows_write(sess.policy, req.kind)
        except PermissionError as exc:
            raise AppError(ErrorCode.SANDBOX_DENIED, str(exc), http_status=403) from exc

        need, reason = assess_risk(req, sess.policy)
        if need:
            raise AppError(
                ErrorCode.SANDBOX_APPROVAL_REQUIRED,
                reason or "需要人工审批",
                http_status=409,
                extras={"sessionId": req.session_id, "risk": reason},
            )

        if req.kind == "fs_list":
            result = workspace_fs.fs_list(sess, req)
        elif req.kind == "fs_read":
            result = workspace_fs.fs_read(sess, req)
        elif req.kind == "fs_write":
            result = workspace_fs.fs_write(sess, req)
        else:
            try:
                result = await self._rt.exec(
                    sess,
                    req,
                    allow_shell_string=sess.policy.allow_shell_string,
                )
            except PermissionError as exc:
                raise AppError(
                    ErrorCode.SANDBOX_DENIED, str(exc), http_status=403
                ) from exc

        sess.last_active_at = now_iso()
        save_session(sess)
        log_exec(req, result, vertical=sess.vertical)
        return result

    async def release(self, *, session_id: str, tenant_id: str) -> None:
        sess = await self._get_owned(session_id, tenant_id)
        # P4：先关掉挂在该沙箱上的 ttyd，再毁容器
        try:
            from application.ops.ttyd_manager import get_ttyd_manager

            await get_ttyd_manager().close_by_sandbox(session_id)
        except Exception:  # noqa: BLE001
            pass
        await self._rt.destroy(sess)
        sess.status = "released"
        async with self._lock:
            self._sessions.pop(session_id, None)
        delete_session_meta(sess.tenant_id, session_id)
        log_lifecycle("release", tenant=sess.tenant_id, session=session_id)

    def get_public(self, session_id: str, tenant_id: str) -> dict[str, Any]:
        tenant = sanitize_tenant_id(tenant_id)
        sess = self._sessions.get(session_id)
        if sess is None or sess.status != "running" or sess.tenant_id != tenant:
            raise AppError(ErrorCode.NOT_FOUND, "沙箱会话不存在", http_status=404)
        return {
            "id": sess.id,
            "vertical": sess.vertical,
            "capabilities": sorted(sess.capabilities),
            "createdAt": sess.created_at,
            "lastActiveAt": sess.last_active_at,
            "status": sess.status,
            "policy": {
                "mode": sess.policy.mode,
                "networkMode": sess.policy.network_mode,
                "approval": sess.policy.approval,
            },
        }

    def iter_running(self) -> list[SandboxSession]:
        return [s for s in self._sessions.values() if s.status == "running"]

    async def _get_owned(self, session_id: str, tenant_id: str) -> SandboxSession:
        tenant = sanitize_tenant_id(tenant_id)
        async with self._lock:
            sess = self._sessions.get(session_id)
        if sess is None or sess.status != "running":
            raise AppError(ErrorCode.NOT_FOUND, "沙箱会话不存在", http_status=404)
        if sess.tenant_id != tenant:
            raise AppError(ErrorCode.NOT_FOUND, "沙箱会话不存在", http_status=404)
        return sess


_broker: SandboxBroker | None = None


def get_sandbox_broker() -> SandboxBroker:
    global _broker
    if _broker is None:
        _broker = SandboxBroker()
    return _broker
