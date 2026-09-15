"""SQLite 用户表：username 唯一，密码只存 Argon2 哈希。"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from api.auth.password import hash_password, verify_password
from application.tenancy import sanitize_tenant_id
from config.settings import get_settings
from shared.path_security import get_project_root

# 用户不存在时仍走一次 verify，减轻时序侧信道（启动时算一次即可）
_DUMMY_HASH = hash_password("dummy-timing-pad")


@dataclass(frozen=True)
class StoredUser:
    username: str
    tenant_id: str
    is_active: bool


_lock = threading.Lock()
_initialized = False


def _db_path() -> Path:
    settings = get_settings()
    raw = Path(settings.auth_users_db_path)
    if raw.is_absolute():
        return raw
    return get_project_root() / raw


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_user_store() -> None:
    """建表并在空库时用 ADMIN_USERNAME / ADMIN_PASSWORD 种第一个管理员。"""
    global _initialized
    with _lock:
        with _connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)"
            )
            settings = get_settings()
            row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
            if int(row["n"] or 0) == 0:
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, tenant_id, is_active, created_at)
                    VALUES (?, ?, ?, 1, ?)
                    """,
                    (
                        settings.admin_username.strip(),
                        hash_password(settings.admin_password),
                        sanitize_tenant_id(settings.default_tenant_id),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            elif settings.auth_bootstrap_reset_admin:
                conn.execute(
                    """
                    UPDATE users SET password_hash = ?, tenant_id = ?, is_active = 1
                    WHERE username = ?
                    """,
                    (
                        hash_password(settings.admin_password),
                        sanitize_tenant_id(settings.default_tenant_id),
                        settings.admin_username.strip(),
                    ),
                )
            conn.commit()
        _initialized = True


def get_user(username: str) -> StoredUser | None:
    init_user_store()
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT username, tenant_id, is_active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None:
        return None
    return StoredUser(
        username=str(row["username"]),
        tenant_id=str(row["tenant_id"]),
        is_active=bool(row["is_active"]),
    )


def authenticate(username: str, password: str) -> StoredUser | None:
    """用户名不存在时仍做一次假校验，减轻用户枚举。"""
    init_user_store()
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT username, password_hash, tenant_id, is_active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    stored_hash = str(row["password_hash"]) if row is not None else _DUMMY_HASH
    ok = verify_password(password, stored_hash)
    if row is None or not ok or not bool(row["is_active"]):
        return None
    return StoredUser(
        username=str(row["username"]),
        tenant_id=str(row["tenant_id"]),
        is_active=True,
    )


def create_user(username: str, password: str, tenant_id: str | None = None) -> StoredUser:
    settings = get_settings()
    tenant = sanitize_tenant_id(tenant_id or settings.default_tenant_id)
    init_user_store()
    with _lock, _connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, tenant_id, is_active, created_at)
                VALUES (?, ?, ?, 1, ?)
                """,
                (
                    username,
                    hash_password(password),
                    tenant,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("用户名已存在") from exc
    return StoredUser(username=username, tenant_id=tenant, is_active=True)
