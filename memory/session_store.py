"""多会话历史管理系统 — 支持 Redis / SQLite 两种后端

知识点:
1. 策略模式: 定义统一接口, 不同后端实现可互换
2. 为什么不用 InMemory? → 服务重启后历史丢失, 无法横向扩展
3. Redis TTL → 自动过期, 适合缓存场景
4. SQLite → 适合本地持久化, 无需额外服务
"""

from abc import ABC, abstractmethod
from datetime import datetime
import json
from pathlib import Path


class BaseSessionStore(ABC):
    """会话存储抽象基类"""

    @abstractmethod
    async def get_messages(self, session_id: str) -> list[dict]:
        """获取指定会话的所有历史消息"""
        ...

    @abstractmethod
    async def add_message(self, session_id: str, role: str, content: str) -> None:
        """向会话添加一条消息"""
        ...

    @abstractmethod
    async def get_recent_messages(self, session_id: str, n: int = 20) -> list[dict]:
        """获取最近 n 条消息"""
        ...

    @abstractmethod
    async def clear_session(self, session_id: str) -> None:
        """清除指定会话"""
        ...

    @abstractmethod
    async def list_sessions(self) -> list[str]:
        """列出所有会话 ID"""
        ...

    @abstractmethod
    async def delete_old_sessions(self, max_age_days: int = 7) -> int:
        """清理过期会话, 返回清理数量"""
        ...


# ============ Redis 实现 ============

class RedisSessionStore(BaseSessionStore):
    """Redis 会话存储

    知识点:
    - Redis List (LPUSH/LRANGE/LTRIM) → 天然适合消息队列
    - EXPIRE → 每个 session 设置 TTL, 自动过期
    - SCAN → 代替 KEYS, 避免阻塞 Redis
    """

    def __init__(self, redis_url: str, ttl_seconds: int = 3600):
        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ImportError("请安装 redis: pip install redis[hiredis]")
        self.redis = aioredis.from_url(redis_url, decode_responses=True)
        self.ttl = ttl_seconds

    def _key(self, session_id: str) -> str:
        return f"chat:session:{session_id}"

    async def get_messages(self, session_id: str) -> list[dict]:
        raw = await self.redis.lrange(self._key(session_id), 0, -1)
        return [json.loads(m) for m in reversed(raw)]

    async def add_message(self, session_id: str, role: str, content: str) -> None:
        key = self._key(session_id)
        msg = json.dumps({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        await self.redis.lpush(key, msg)
        await self.redis.expire(key, self.ttl)

    async def get_recent_messages(self, session_id: str, n: int = 20) -> list[dict]:
        raw = await self.redis.lrange(self._key(session_id), 0, n - 1)
        return [json.loads(m) for m in reversed(raw)]

    async def clear_session(self, session_id: str) -> None:
        await self.redis.delete(self._key(session_id))

    async def list_sessions(self) -> list[str]:
        keys: list[str] = []
        cursor = 0
        while True:
            cursor, batch = await self.redis.scan(cursor, match="chat:session:*")
            keys.extend(batch)
            if cursor == 0:
                break
        return [k.replace("chat:session:", "") for k in keys]

    async def delete_old_sessions(self, max_age_days: int = 7) -> int:
        """Redis TTL 自动处理过期, 此方法主要用于手动清理无 TTL 的 key"""
        count = 0
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(cursor, match="chat:session:*")
            for key in keys:
                ttl = await self.redis.ttl(key)
                if ttl == -1:  # 没有设置过期时间
                    await self.redis.expire(key, self.ttl)
                    count += 1
            if cursor == 0:
                break
        return count


# ============ SQLite 实现 ============

class SQLiteSessionStore(BaseSessionStore):
    """SQLite 会话存储

    知识点:
    - aiomysql/aiohttp 的异步模式
    - 索引优化: 在 (session_id, timestamp) 上建联合索引加速查询
    """

    def __init__(self, db_path: str = "data/chat_history.db"):
        import sqlite3
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_time
                ON messages(session_id, created_at DESC)
            """)

    def _get_conn(self):
        import sqlite3
        return sqlite3.connect(self.db_path)

    async def get_messages(self, session_id: str) -> list[dict]:
        import sqlite3
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in rows]

    async def add_message(self, session_id: str, role: str, content: str) -> None:
        import sqlite3
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )
            conn.commit()

    async def get_recent_messages(self, session_id: str, n: int = 20) -> list[dict]:
        import sqlite3
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, n),
            ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    async def clear_session(self, session_id: str) -> None:
        import sqlite3
        with self._get_conn() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.commit()

    async def list_sessions(self) -> list[str]:
        import sqlite3
        with self._get_conn() as conn:
            rows = conn.execute("SELECT DISTINCT session_id FROM messages").fetchall()
        return [r[0] for r in rows]

    async def delete_old_sessions(self, max_age_days: int = 7) -> int:
        import sqlite3
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM messages WHERE created_at < datetime('now', ?)",
                (f"-{max_age_days} days",),
            )
            conn.commit()
            return cursor.rowcount


# ============ 工厂函数 ============

async def create_session_store(backend: str = "sqlite", **kwargs) -> BaseSessionStore:
    """工厂函数: 根据配置创建对应的存储后端

    - 本地开发：MEMORY_BACKEND = SQLITE
    - 单机热缓存：redis
    - 商用权威：mysql
    知识点: 工厂模式 — 调用方不需要知道具体实现类, 只需传类型字符串
    """
    raw = (backend or "sqlite").strip().lower()
    if raw == "redis":
        # 原有redis实现，kwargs里应有redis_url / ttl_seconds
        return RedisSessionStore(**kwargs)
    if raw == "sqlite":
        # 原有本地文件库
        return SQLiteSessionStore(**kwargs)
    if raw == "mysql":
        # 延迟导入，避免没装 pymysql 时拖垮其它 backend
        from memory.mysql_session_store import MySQLSessionStore

        return MySQLSessionStore(
            tenant_id_fallback=str(kwargs.get("tenant_id_fallback") or "default")
        )
    raise ValueError(f"不支持的后端类型: {backend}, 可选: redis/sqlite/mysql")