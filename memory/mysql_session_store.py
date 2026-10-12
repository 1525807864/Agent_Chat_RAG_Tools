"""MySQL 会话存储：实现 BaseSessionStore，作为商用权威后端。

知识点：
- 与 RedisSessionStore / SQLiteSessionStore 互换（策略模式）
- 热路径仍可用 Redis 做缓存；本类保证重启/多实例不丢消息
"""
from __future__ import annotations

from typing import Any

# 复用项目里已有的连接参数拼装（密码只从环境读）
from api.auth.mysql_conn import mysql_kwargs
# 抽象基类：必须实现全部 abstract 方法
from memory.session_store import BaseSessionStore
from shared.timeutil import now_mysql as _now


class MySQLSessionStore(BaseSessionStore):
    """权威会话后端：chat_sessions + chat_messages。"""

    def __init__(self, *, tenant_id_fallback: str = "default") -> None:
        # 当 session_id 解不出租户时的兜底（正常应是 default__web-xxx）
        self._tenant_fallback = tenant_id_fallback
        # 懒连接：第一次用时再 ping，避免 import 阶段就连库失败
        self._ensure_schema()

    def _connect(self):
        """每次短连接：简单稳妥；高并发可再换成连接池。"""
        import pymysql
        from pymysql.cursors import DictCursor

        kw = mysql_kwargs()
        # DictCursor：row["role"] 这种写法与现有 user_store 一致
        return pymysql.connect(**kw, cursorclass=DictCursor)

    def _ensure_schema(self) -> None:
        """幂等建表：开发环境没跑 sql 文件时也能自举（生产建议只用 sql 文件）。"""
        # 这里只建最小表；完整注释版见 sql/p0_schema.sql
        ddl_sessions = """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id VARCHAR(191) NOT NULL,
            tenant_id VARCHAR(128) NOT NULL DEFAULT 'default',
            title VARCHAR(255) NULL,
            mode VARCHAR(32) NOT NULL DEFAULT 'chat',
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            last_active_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                ON UPDATE CURRENT_TIMESTAMP(6),
            PRIMARY KEY (id),
            KEY idx_sessions_tenant_active (tenant_id, last_active_at DESC)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        ddl_messages = """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            session_id VARCHAR(191) NOT NULL,
            tenant_id VARCHAR(128) NOT NULL DEFAULT 'default',
            role VARCHAR(32) NOT NULL,
            content MEDIUMTEXT NOT NULL,
            tokens_in INT UNSIGNED NOT NULL DEFAULT 0,
            tokens_out INT UNSIGNED NOT NULL DEFAULT 0,
            model VARCHAR(128) NULL,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            PRIMARY KEY (id),
            KEY idx_msg_session_time (session_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(ddl_sessions)
                cur.execute(ddl_messages)
            conn.commit()
        finally:
            conn.close()

    def _tenant_of(self, session_id: str) -> str:
        """从 default__web-xxx 解析租户；解析失败用 fallback。"""
        sid = session_id or "default"
        if "__" in sid:
            return sid.split("__", 1)[0] or self._tenant_fallback
        return self._tenant_fallback

    def _touch_session(self, cur, session_id: str, tenant_id: str) -> None:
        """确保 chat_sessions 有一行，并刷新 last_active_at。"""
        cur.execute(
            """
            INSERT INTO chat_sessions (id, tenant_id, created_at, last_active_at)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE last_active_at = VALUES(last_active_at)
            """,
            (session_id, tenant_id, _now(), _now()),
        )

    async def get_messages(self, session_id: str) -> list[dict]:
        """全量历史（按时间升序）。大会话生产应用分页，这里对齐现有接口。"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT role, content FROM chat_messages
                    WHERE session_id=%s ORDER BY id ASC
                    """,
                    (session_id,),
                )
                rows = cur.fetchall() or []
            return [{"role": r["role"], "content": r["content"]} for r in rows]
        finally:
            conn.close()

    async def add_message(self, session_id: str, role: str, content: str) -> None:
        """追加一条消息（只 INSERT）。"""
        tenant_id = self._tenant_of(session_id)
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                self._touch_session(cur, session_id, tenant_id)
                cur.execute(
                    """
                    INSERT INTO chat_messages
                        (session_id, tenant_id, role, content, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (session_id, tenant_id, role, content or "", _now()),
                )
            conn.commit()
        finally:
            conn.close()

    async def get_recent_messages(self, session_id: str, n: int = 20) -> list[dict]:
        """最近 n 条，返回顺序为时间升序（与 SQLite 实现一致）。"""
        n = max(1, int(n))
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT role, content FROM (
                        SELECT id, role, content FROM chat_messages
                        WHERE session_id=%s
                        ORDER BY id DESC LIMIT %s
                    ) t ORDER BY id ASC
                    """,
                    (session_id, n),
                )
                rows = cur.fetchall() or []
            return [{"role": r["role"], "content": r["content"]} for r in rows]
        finally:
            conn.close()

    async def clear_session(self, session_id: str) -> None:
        """删消息 + 会话行（硬删；商用可改软删 deleted_at）。"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM chat_messages WHERE session_id=%s", (session_id,)
                )
                cur.execute(
                    "DELETE FROM chat_sessions WHERE id=%s", (session_id,)
                )
            conn.commit()
        finally:
            conn.close()

    async def list_sessions(self) -> list[str]:
        """列出会话 id（优先元数据表；没有则从消息 DISTINCT）。"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM chat_sessions ORDER BY last_active_at DESC"
                )
                rows = cur.fetchall() or []
                if rows:
                    return [r["id"] for r in rows]
                cur.execute("SELECT DISTINCT session_id AS id FROM chat_messages")
                rows = cur.fetchall() or []
            return [r["id"] for r in rows]
        finally:
            conn.close()

    async def delete_old_sessions(self, max_age_days: int = 7) -> int:
        """按天清理旧消息（简化版；生产建议归档到对象存储再删）。"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM chat_messages
                    WHERE created_at < (NOW(6) - INTERVAL %s DAY)
                    """,
                    (int(max_age_days),),
                )
                deleted = cur.rowcount
            conn.commit()
            return int(deleted or 0)
        finally:
            conn.close()