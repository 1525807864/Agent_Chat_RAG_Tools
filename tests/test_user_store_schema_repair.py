"""MySQL users 表被 wipe 后应能强制重建（1146 自愈）。"""

from __future__ import annotations

import pymysql

from api.auth import user_store


def test_is_missing_users_table_detects_1146():
    exc = pymysql.err.ProgrammingError(1146, "Table 'langchain_demo.users' doesn't exist")
    assert user_store._is_missing_users_table(exc) is True


def test_is_missing_users_table_ignores_other_errors():
    exc = pymysql.err.ProgrammingError(1064, "You have an error in your SQL syntax")
    assert user_store._is_missing_users_table(exc) is False


def test_init_user_store_force_reruns_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_BACKEND", "sqlite")
    monkeypatch.setenv("AUTH_USERS_DB_PATH", str(tmp_path / "users.db"))
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin123456")
    from config import settings as settings_mod

    settings_mod._settings = None
    user_store._initialized = False
    user_store.init_user_store()
    assert user_store._initialized is True
    # 模拟「以为已初始化」再 force 一次，不应抛错
    user_store.init_user_store(force=True)
    assert user_store.authenticate("admin", "admin123456") is not None
    settings_mod._settings = None
    user_store._initialized = False
