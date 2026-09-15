"""商用级鉴权：Argon2、启动护栏、租户会话、登录失败。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.auth.jwt_auth import create_access_token, decode_access_token
from api.auth.password import hash_password, verify_password
from api.auth.security_guard import SecurityConfigError, assert_auth_config
from api.auth.session_scope import bind_session_id, public_session_id
from api.auth.user_store import authenticate, create_user, init_user_store
from config.settings import get_settings
import api.auth.user_store as user_store
import config.settings as settings_mod


def test_argon2_roundtrip():
    hashed = hash_password("correct-horse")
    assert hashed != "correct-horse"
    assert hashed.startswith("$argon2")
    assert verify_password("correct-horse", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_extra_cannot_overwrite_sub():
    token = create_access_token(
        subject="u1",
        tenant_id="t1",
        extra={"sub": "hacker", "tenant_id": "other", "exp": 1},
    )
    payload = decode_access_token(token)
    assert payload["sub"] == "u1"
    assert payload["tenant_id"] == "t1"
    assert payload["exp"] != 1


def test_weak_jwt_secret_rejected_when_auth_on():
    settings = get_settings().model_copy(
        update={
            "auth_enabled": True,
            "jwt_secret": "too-short",
            "strict_production": False,
        }
    )
    with pytest.raises(SecurityConfigError):
        assert_auth_config(settings)


def test_strict_production_rejects_debug_and_default_password():
    settings = get_settings().model_copy(
        update={
            "auth_enabled": True,
            "jwt_secret": "a" * 32,
            "strict_production": True,
            "auth_debug_enabled": True,
            "openapi_enabled": False,
            "enable_execute_python": False,
            "admin_password": "admin123456",
            "cors_origins": "https://ok.example",
            "rate_limit_backend": "redis",
            "search_ssl_verify": True,
        }
    )
    with pytest.raises(SecurityConfigError):
        assert_auth_config(settings)


def test_bind_session_rejects_other_tenant():
    assert bind_session_id("acme", "web-1") == "acme::web-1"
    with pytest.raises(HTTPException) as ei:
        bind_session_id("acme", "beta::web-1")
    assert ei.value.status_code == 404
    assert public_session_id("acme", "acme::web-1") == "web-1"
    assert public_session_id("acme", "beta::web-1") is None


def test_user_store_authenticate(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_USERS_DB_PATH", str(tmp_path / "users.db"))
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin123456")
    settings_mod._settings = None
    user_store._initialized = False
    init_user_store()
    assert authenticate("admin", "admin123456") is not None
    assert authenticate("admin", "nope") is None
    assert authenticate("missing", "admin123456") is None
    create_user("alice", "alice-pass-1")
    alice = authenticate("alice", "alice-pass-1")
    assert alice is not None
    assert alice.username == "alice"
    settings_mod._settings = None
    user_store._initialized = False


def test_login_wrong_password():
    from api.server import app

    with TestClient(app) as client:
        r = client.post(
            "/api/auth/login",
            json={"username": get_settings().admin_username, "password": "definitely-wrong"},
        )
        assert r.status_code == 401


def test_register_disabled_is_404():
    if get_settings().allow_register:
        pytest.skip("ALLOW_REGISTER=true")
    from api.server import app

    with TestClient(app) as client:
        r = client.post(
            "/api/auth/register",
            json={"username": "newbie", "password": "abcdefgh"},
        )
        assert r.status_code == 404


def test_login_issues_jwt_and_ignores_tenant_spoof():
    from api.server import app

    settings = get_settings()
    with TestClient(app) as client:
        r = client.post(
            "/api/auth/login",
            json={
                "username": settings.admin_username,
                "password": settings.admin_password,
                "tenant_id": "evil-tenant",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["access_token"]
        assert body["user_id"] == settings.admin_username
        token = body["access_token"]
        payload = decode_access_token(token)
        assert payload["tenant_id"] != "evil-tenant"


def test_auth_required_when_enabled():
    settings = get_settings()
    if not settings.auth_enabled:
        pytest.skip("AUTH_ENABLED=false")
    from api.server import app

    with TestClient(app) as client:
        r = client.get("/api/sessions")
        assert r.status_code == 401
