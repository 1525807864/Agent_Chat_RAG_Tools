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
    # 不启动完整 lifespan 时可能失败；用 settings 覆盖
    settings = get_settings()
    if settings.auth_enabled:
        pytest.skip("AUTH_ENABLED=true，跳过匿名通路测试")

    from api.server import app

    with TestClient(app) as client:
        r = client.post(
            "/api/auth/dev-token",
            json={"user_id": "u1", "tenant_id": "default"},
        )
        assert r.status_code == 200
        assert "access_token" in r.json()
