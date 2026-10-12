"""沙箱会话元数据落盘。进程重启后可扫残骸 / 恢复登记。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.settings import get_settings
from infrastructure.sandbox.models import (
    SandboxLimits,
    SandboxPolicySnapshot,
    SandboxSession,
)
from shared.path_security import get_project_root


def _root() -> Path:
    return get_project_root() / get_settings().sandbox_workspace_host


def session_meta_path(tenant_id: str, session_id: str) -> Path:
    return _root() / tenant_id / session_id / "session.json"


def save_session(sess: SandboxSession) -> None:
    path = session_meta_path(sess.tenant_id, sess.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "id": sess.id,
        "tenant_id": sess.tenant_id,
        "vertical": sess.vertical,
        "capabilities": sorted(sess.capabilities),
        "container_id": sess.container_id,
        "workspace_host": sess.workspace_host,
        "created_at": sess.created_at,
        "last_active_at": sess.last_active_at,
        "status": sess.status,
        "limits": sess.limits.__dict__,
        "policy": {
            "mode": sess.policy.mode,
            "network_mode": sess.policy.network_mode,
            "approval": sess.policy.approval,
            "allow_shell_string": sess.policy.allow_shell_string,
            "egress_allowlist": list(sess.policy.egress_allowlist),
        },
        "meta": sess.meta,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def delete_session_meta(tenant_id: str, session_id: str) -> None:
    path = session_meta_path(tenant_id, session_id)
    if path.exists():
        path.unlink()


def load_all() -> list[SandboxSession]:
    root = _root()
    if not root.is_dir():
        return []
    out: list[SandboxSession] = []
    for meta in root.glob("*/*/session.json"):
        try:
            raw: dict[str, Any] = json.loads(meta.read_text(encoding="utf-8"))
            pol = raw.get("policy") or {}
            lim = raw.get("limits") or {}
            limit_keys = SandboxLimits.__dataclass_fields__
            out.append(
                SandboxSession(
                    id=raw["id"],
                    tenant_id=raw["tenant_id"],
                    vertical=raw.get("vertical") or "generic",
                    capabilities=frozenset(raw.get("capabilities") or []),
                    container_id=raw.get("container_id") or "",
                    workspace_host=raw.get("workspace_host") or str(meta.parent),
                    created_at=raw.get("created_at") or "",
                    last_active_at=raw.get("last_active_at") or "",
                    status=raw.get("status") or "running",
                    limits=SandboxLimits(
                        **{k: lim[k] for k in limit_keys if k in lim}
                    ),
                    policy=SandboxPolicySnapshot(
                        mode=pol.get("mode", "workspace-write"),
                        network_mode=pol.get("network_mode", "deny"),
                        approval=pol.get("approval", "on-risky"),
                        egress_allowlist=tuple(pol.get("egress_allowlist") or ()),
                        allow_shell_string=bool(pol.get("allow_shell_string")),
                    ),
                    meta=raw.get("meta") or {},
                )
            )
        except Exception:  # noqa: BLE001
            continue
    return out
