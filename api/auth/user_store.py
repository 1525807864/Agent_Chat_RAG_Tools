"""用户表：默认 MySQL，可用 AUTH_BACKEND=sqlite 回退到本地 users.db。

密码只存 Argon2 哈希，不明文。MySQL 占位符必须是 %s，不能再用 SQLite 的 ?。
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from api.auth.password import hash_password, verify_password
from application.tenancy import sanitize_tenant_id
from config.settings import get_settings
from shared.path_security import get_project_root
from shared.timeutil import now_iso, now_mysql

# 用户不存在时仍走一次 verify，减轻时序侧信道（启动时算一次即可）
_DUMMY_HASH = hash_password("dummy-timing-pad")
_lock = threading.Lock()
_initialized = False


@dataclass(frozen=True)
class StoredUser:
    username: str
    tenant_id: str
    is_active: bool


def _use_mysql() -> bool:
    """生产默认 mysql；单测 / 本地无 MySQL 时设 AUTH_BACKEND=sqlite。"""
    return get_settings().auth_backend == "mysql"


def _db_path() -> Path:
    settings = get_settings()
    raw = Path(settings.auth_users_db_path)
    if raw.is_absolute():
        return raw
    return get_project_root() / raw


def _connect_sqlite() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_mysql():
    """短连接：登录不频繁，避免在 2G 机器上常驻连接池。"""
    import pymysql
    from pymysql.cursors import DictCursor

    from api.auth.mysql_conn import mysql_kwargs

    return pymysql.connect(**mysql_kwargs(), cursorclass=DictCursor)


def _connect_mysql_with_retry(retries: int = 30, delay: float = 2.0):
    """Compose 里 API 可能比 MySQL 先起来，启动时重试避免直接挂掉。"""
    last: Exception | None = None
    for _ in range(retries):
        try:
            return _connect_mysql()
        except Exception as exc:  # noqa: BLE001 — 等 mysqld 就绪，任何连不上都重试
            last = exc
            time.sleep(delay)
    assert last is not None
    raise last


def _init_mysql() -> None:
    settings = get_settings()
    conn = _connect_mysql_with_retry()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                    username VARCHAR(128) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    tenant_id VARCHAR(128) NOT NULL DEFAULT 'default',
                    is_active TINYINT(1) NOT NULL DEFAULT 1,
                    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                    PRIMARY KEY (id),
                    UNIQUE KEY uk_users_username (username)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute("SELECT COUNT(*) AS n FROM users")
            row = cur.fetchone() or {}
            n = int(row.get("n") or 0)
            if n == 0:
                cur.execute(
                    """
                    INSERT INTO users (username, password_hash, tenant_id, is_active, created_at)
                    VALUES (%s, %s, %s, 1, %s)
                    """,
                    (
                        settings.admin_username.strip(),
                        hash_password(settings.admin_password),
                        sanitize_tenant_id(settings.default_tenant_id),
                        now_mysql(),
                    ),
                )
            elif settings.auth_bootstrap_reset_admin:
                cur.execute(
                    """
                    UPDATE users SET password_hash=%s, tenant_id=%s, is_active=1
                    WHERE username=%s
                    """,
                    (
                        hash_password(settings.admin_password),
                        sanitize_tenant_id(settings.default_tenant_id),
                        settings.admin_username.strip(),
                    ),
                )
        conn.commit()
    finally:
        conn.close()


def _init_sqlite() -> None:
    settings = get_settings()
    with _connect_sqlite() as conn:
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
                    now_iso(),
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


def init_user_store() -> None:
    """建表并在空库时用 ADMIN_USERNAME / ADMIN_PASSWORD 种第一个管理员。"""
    global _initialized
    with _lock:
        if _initialized:
            return
        if _use_mysql():
            _init_mysql()
        else:
            _init_sqlite()
        _initialized = True


def get_user(username: str) -> StoredUser | None:
    init_user_store()
    if _use_mysql():
        conn = _connect_mysql()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT username, tenant_id, is_active FROM users WHERE username=%s",
                    (username,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return StoredUser(
            username=str(row["username"]),
            tenant_id=str(row["tenant_id"]),
            is_active=bool(int(row["is_active"])),
        )

    with _lock, _connect_sqlite() as conn:
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
    if _use_mysql():
        conn = _connect_mysql()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT username, password_hash, tenant_id, is_active
                    FROM users WHERE username=%s
                    """,
                    (username,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        stored_hash = str(row["password_hash"]) if row is not None else _DUMMY_HASH
        ok = verify_password(password, stored_hash)
        if row is None or not ok or not int(row["is_active"]):
            return None
        return StoredUser(
            username=str(row["username"]),
            tenant_id=str(row["tenant_id"]),
            is_active=True,
        )

    with _lock, _connect_sqlite() as conn:
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
    if _use_mysql():
        import pymysql

        conn = _connect_mysql()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (username, password_hash, tenant_id, is_active, created_at)
                    VALUES (%s, %s, %s, 1, %s)
                    """,
                    (username, hash_password(password), tenant, now_mysql()),
                )
            conn.commit()
        except pymysql.err.IntegrityError as exc:
            conn.rollback()
            raise ValueError("用户名已存在") from exc
        finally:
            conn.close()
        return StoredUser(username=username, tenant_id=tenant, is_active=True)

    with _lock, _connect_sqlite() as conn:
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
                    now_iso(),
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("用户名已存在") from exc
    return StoredUser(username=username, tenant_id=tenant, is_active=True)
