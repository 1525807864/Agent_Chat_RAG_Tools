"""P0 鉴权冒烟测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.auth.jwt_auth import create_access_token, decode_access_token
from config.settings import get_settings


def test_jwt_roundtrip():
    token = create_access_token(subject="u1", tenant_id="t1")
    payload = decode_access_token(token)
    assert payload["sub"] == "u1"
    assert payload["tenant_id"] == "t1"


def test_dev_token_and_chat_meta_when_auth_disabled():
    settings = get_settings()
    if settings.auth_enabled:
        pytest.skip("AUTH_ENABLED=true，跳过匿名通路测试")
    if not settings.auth_debug_enabled:
        pytest.skip("AUTH_DEBUG_ENABLED=false，跳过 dev-token")

    from api.server import app

    with TestClient(app) as client:
        r = client.post(
            "/api/auth/dev-token",
            json={"user_id": "u1", "tenant_id": "default"},
        )
        assert r.status_code == 200
        assert "access_token" in r.json()


def test_login_issues_jwt():
    from api.server import app

    settings = get_settings()
    with TestClient(app) as client:
        r = client.post(
            "/api/auth/login",
            json={
                "username": settings.admin_username,
                "password": settings.admin_password,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["access_token"]
        assert body["user_id"] == settings.admin_username
        payload = decode_access_token(body["access_token"])
        assert payload["sub"] == settings.admin_username
