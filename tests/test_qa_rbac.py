"""QA RBAC：首次用户 admin；execute 能跑不能改；不能删最后一名 admin。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from api.auth.deps import AuthUser
from application.qa.rbac import (
    PERMISSIONS,
    bootstrap_owner,
    require_member,
    resolve_member,
)
from application.qa.service import QaApplication
from infrastructure.qa.filesystem import QaFileStore


def test_permission_matrix() -> None:
    assert "execute" not in PERMISSIONS["case:write"]
    assert "execute" in PERMISSIONS["run:execute"]
    assert "view" not in PERMISSIONS["run:execute"]
    assert PERMISSIONS["member:manage"] == frozenset({"admin"})


def test_first_user_becomes_admin(tmp_path: Path) -> None:
    store = QaFileStore("acme", root=tmp_path)
    members = bootstrap_owner("acme", "alice", store=store)
    assert len(members) == 1
    assert members[0].user_id == "alice"
    assert members[0].role == "admin"

    # 第二次不应再造第二个 admin；bob 未邀请
    again = bootstrap_owner("acme", "bob", store=store)
    assert len(again) == 1
    assert again[0].user_id == "alice"
    assert resolve_member("acme", "bob", store=store) is None


def test_require_member_403_for_non_member(tmp_path: Path) -> None:
    store = QaFileStore("t2", root=tmp_path)
    bootstrap_owner("t2", "owner", store=store)
    # resolve 已确认 bob 不在；require_member 走默认 data 目录，这里直接测 resolve
    assert resolve_member("t2", "bob", store=store) is None


def test_cannot_drop_last_admin(tmp_path: Path) -> None:
    app = QaApplication("t1")
    app.store = QaFileStore("t1", root=tmp_path)
    app.add_member("owner", "owner", "admin")
    members = app.list_members()
    assert len(members) == 1
    with pytest.raises(ValueError, match="最后一个管理员"):
        app.delete_member(members[0].id)
    with pytest.raises(ValueError, match="最后一个管理员"):
        app.set_member_role(members[0].id, "view")


def test_require_member_uses_auth_user_id(tmp_path: Path, monkeypatch) -> None:
    """require_member 必须读 AuthUser.user_id（不是 .id）。"""
    store = QaFileStore("t3", root=tmp_path)
    bootstrap_owner("t3", "carol", store=store)

    def _fake_store(tenant_id: str) -> QaFileStore:
        return store

    monkeypatch.setattr("application.qa.rbac._store", _fake_store)
    member = require_member(AuthUser(user_id="carol", tenant_id="t3"))
    assert member.role == "admin"
    with pytest.raises(HTTPException) as ei:
        require_member(AuthUser(user_id="dave", tenant_id="t3"))
    assert ei.value.status_code == 403
