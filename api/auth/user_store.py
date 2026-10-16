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
from api.auth.username_rules import normalize_new_username
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


def _usernames_exactly_equal(stored: str, requested: str) -> bool:
    """用户名必须字面完全一致（区分大小写）。

    切勿使用 lower()/casefold()——那会重新变成不区分大小写。
    MySQL utf8mb4_bin + 本函数双保险，防止旧库 _ci 校对漏网。
    """
    return stored == requested


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
    """初始化 MySQL users 表。
    关键安全约定：
    - username 列必须 COLLATE utf8mb4_bin（区分大小写）；
    - CREATE TABLE IF NOT EXISTS 不会修改「已经存在」的旧表，
      所以后面要再跑一次幂等 ALTER，把旧的 _ci 校对改掉。
    """
    settings = get_settings()
    conn = _connect_mysql_with_retry()
    try:
        with conn.cursor() as cur:
            # ---- 1) 新库：直接按 bin 校对建表 ----
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                    -- utf8mb4_bin：比较区分大小写；UNIQUE 也区分 admin / ADMIN
                    username VARCHAR(128) NOT NULL COLLATE utf8mb4_bin,
                    password_hash VARCHAR(255) NOT NULL,
                    tenant_id VARCHAR(128) NOT NULL DEFAULT 'default',
                    is_active TINYINT(1) NOT NULL DEFAULT 1,
                    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                    PRIMARY KEY (id),
                    UNIQUE KEY uk_users_username (username)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            # ---- 2) 旧库：幂等把已有列改成 bin（重复执行也安全）----
            # 若库里还是 unicode_ci，不跑这段则 ADMIN 仍能登录成 admin。
            cur.execute(
                """
                ALTER TABLE users
                  MODIFY COLUMN username VARCHAR(128) NOT NULL COLLATE utf8mb4_bin
                """
            )
            # ---- 3) 空库种管理员 / 可选重置密码 ----
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
                # WHERE 在 bin 校对下已区分大小写；传入的必须与库中完全一致
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


def _is_missing_users_table(exc: BaseException) -> bool:
    """MySQL 1146：库在但 users 表没了（K8s emptyDir 重建后常见）。"""
    try:
        import pymysql

        if isinstance(exc, pymysql.err.ProgrammingError):
            # args[0] 是 errno
            return int(exc.args[0]) == 1146 and "users" in str(exc.args[1]).lower()
    except Exception:  # noqa: BLE001
        pass
    msg = str(exc).lower()
    return "1146" in msg and "users" in msg


def init_user_store(*, force: bool = False) -> None:
    """建表并在空库时用 ADMIN_USERNAME / ADMIN_PASSWORD 种第一个管理员。

    force=True：忽略进程内缓存，重新跑 CREATE IF NOT EXISTS（MySQL 数据卷被 wipe 后用）。
    """
    global _initialized
    with _lock:
        if _initialized and not force:
            return
        if _use_mysql():
            _init_mysql()
        else:
            _init_sqlite()
        _initialized = True


def _run_with_users_schema_repair(op):
    """执行一次 MySQL 读/写；若表不存在则强制建表后重试一次。"""
    try:
        return op()
    except Exception as exc:  # noqa: BLE001 — 仅捕获后判断是否 1146
        if not _use_mysql() or not _is_missing_users_table(exc):
            raise
        init_user_store(force=True)
        return op()


def get_user(username: str) -> StoredUser | None:
    """按用户名读取；必须与库中字面完全一致（区分大小写）。"""
    init_user_store()
    if _use_mysql():

        def _read() -> StoredUser | None:
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
            # 应用层二次校验：旧库若仍是 _ci，防止 ADMIN 命中 admin
            if not _usernames_exactly_equal(str(row["username"]), username):
                return None
            return StoredUser(
                username=str(row["username"]),
                tenant_id=str(row["tenant_id"]),
                is_active=bool(int(row["is_active"])),
            )

        return _run_with_users_schema_repair(_read)

    with _lock, _connect_sqlite() as conn:
        row = conn.execute(
            # COLLATE BINARY：按字节比较，强制区分大小写
            "SELECT username, tenant_id, is_active FROM users WHERE username = ? COLLATE BINARY",
            (username,),
        ).fetchone()
    if row is None:
        return None
    if not _usernames_exactly_equal(str(row["username"]), username):
        return None
    return StoredUser(
        username=str(row["username"]),
        tenant_id=str(row["tenant_id"]),
        is_active=bool(row["is_active"]),
    )


def authenticate(username: str, password: str) -> StoredUser | None:
    """校验用户名+密码。

    顺序不能乱：
    1) 无论是否存在用户，都 verify_password 一次（不存在用 _DUMMY_HASH）防时序枚举；
    2) 再检查存在 / 密码 / 启用；
    3) 最后强制 username 字面相等（admin ≠ ADMIN）。
    """
    init_user_store()
    if _use_mysql():

        def _auth() -> StoredUser | None:
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
            # ① 始终验密一次
            stored_hash = str(row["password_hash"]) if row is not None else _DUMMY_HASH
            ok = verify_password(password, stored_hash)
            # ② 不存在 / 错密 / 停用
            if row is None or not ok or not int(row["is_active"]):
                return None
            # ③ 大小写必须完全一致
            if not _usernames_exactly_equal(str(row["username"]), username):
                return None
            return StoredUser(
                username=str(row["username"]),
                tenant_id=str(row["tenant_id"]),
                is_active=True,
            )

        return _run_with_users_schema_repair(_auth)

    with _lock, _connect_sqlite() as conn:
        row = conn.execute(
            """
            SELECT username, password_hash, tenant_id, is_active
            FROM users WHERE username = ? COLLATE BINARY
            """,
            (username,),
        ).fetchone()
    stored_hash = str(row["password_hash"]) if row is not None else _DUMMY_HASH
    ok = verify_password(password, stored_hash)
    if row is None or not ok or not bool(row["is_active"]):
        return None
    if not _usernames_exactly_equal(str(row["username"]), username):
        return None
    return StoredUser(
        username=str(row["username"]),
        tenant_id=str(row["tenant_id"]),
        is_active=True,
    )


def create_user(username: str, password: str, tenant_id: str | None = None) -> StoredUser:
    """创建用户：先校验用户名格式，再 INSERT（用规范化后的 name，保留大小写）。"""
    settings = get_settings()
    # ★ 必须在连库 / INSERT 之前；非法名绝不能进库
    name = normalize_new_username(username)
    # 未显式传 tenant 时用用户名作租户；已传则仍 sanitize
    tenant = sanitize_tenant_id(tenant_id if tenant_id is not None else name)
    init_user_store()
    pwd_hash = hash_password(password)

    if _use_mysql():
        import pymysql

        def _insert() -> StoredUser:
            conn = _connect_mysql()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO users (username, password_hash, tenant_id, is_active, created_at)
                        VALUES (%s, %s, %s, 1, %s)
                        """,
                        (name, pwd_hash, tenant, now_mysql()),
                    )
                conn.commit()
            except pymysql.err.IntegrityError as exc:
                conn.rollback()
                # utf8mb4_bin：仅「完全同名（含大小写）」才冲突
                raise ValueError("用户名已存在") from exc
            finally:
                conn.close()
            return StoredUser(username=name, tenant_id=tenant, is_active=True)

        return _run_with_users_schema_repair(_insert)

    with _lock, _connect_sqlite() as conn:
        try:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, tenant_id, is_active, created_at)
                VALUES (?, ?, ?, 1, ?)
                """,
                (name, pwd_hash, tenant, now_iso()),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("用户名已存在") from exc
    return StoredUser(username=name, tenant_id=tenant, is_active=True)
