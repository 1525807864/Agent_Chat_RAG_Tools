"""把 RedisUsageLedger 的脏租户刷进 MySQL usage_events / usage_daily。

热路径：Redis HINCRBY（已有）
冷路径：本模块定时或手动 flush（绝不在聊天请求里同步刷库）
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from api.auth.mysql_conn import mysql_kwargs


def _connect():
    import pymysql
    from pymysql.cursors import DictCursor

    return pymysql.connect(**mysql_kwargs(), cursorclass=DictCursor)


def _ensure_usage_tables(cur) -> None:
    """幂等建用量表（也可用 sql/p0_schema.sql）。"""
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_events (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            tenant_id VARCHAR(128) NOT NULL,
            session_id VARCHAR(191) NULL,
            requests INT UNSIGNED NOT NULL DEFAULT 0,
            tokens_in INT UNSIGNED NOT NULL DEFAULT 0,
            tokens_out INT UNSIGNED NOT NULL DEFAULT 0,
            model VARCHAR(128) NULL,
            source VARCHAR(32) NOT NULL DEFAULT 'redis_flush',
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            PRIMARY KEY (id),
            KEY idx_usage_tenant_time (tenant_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_daily (
            tenant_id VARCHAR(128) NOT NULL,
            day DATE NOT NULL,
            requests BIGINT UNSIGNED NOT NULL DEFAULT 0,
            tokens_in BIGINT UNSIGNED NOT NULL DEFAULT 0,
            tokens_out BIGINT UNSIGNED NOT NULL DEFAULT 0,
            updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                ON UPDATE CURRENT_TIMESTAMP(6),
            PRIMARY KEY (tenant_id, day)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def flush_dirty_tenants(redis_client: Any, *, reset_redis: bool = True) -> int:
    """扫描 usage:dirty，把每个租户 HASH 写成一条 event + 累加 daily。

    参数：
      redis_client: redis.Redis 实例（与 RedisUsageLedger._r 相同）
      reset_redis: flush 成功后是否把 HASH 清零（避免重复入账）
    返回：成功 flush 的租户数
    """
    dirty_key = "usage:dirty"
    tenants = list(redis_client.smembers(dirty_key) or [])
    if not tenants:
        return 0

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ok = 0
    conn = _connect()
    try:
        with conn.cursor() as cur:
            _ensure_usage_tables(cur)
            for tid in tenants:
                tid = str(tid)
                key = f"usage:tenant:{tid}"
                raw = redis_client.hgetall(key) or {}
                req = int(raw.get("requests") or 0)
                tin = int(raw.get("tokens_in") or 0)
                tout = int(raw.get("tokens_out") or 0)
                # 全 0 也从 dirty 摘掉，避免空转
                if req == 0 and tin == 0 and tout == 0:
                    redis_client.srem(dirty_key, tid)
                    continue

                # 1) 明细事件（可审计）
                cur.execute(
                    """
                    INSERT INTO usage_events
                        (tenant_id, requests, tokens_in, tokens_out, source, created_at)
                    VALUES (%s, %s, %s, %s, 'redis_flush', UTC_TIMESTAMP(6))
                    """,
                    (tid, req, tin, tout),
                )
                # 2) 日汇总 UPSERT
                cur.execute(
                    """
                    INSERT INTO usage_daily
                        (tenant_id, day, requests, tokens_in, tokens_out)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        requests = requests + VALUES(requests),
                        tokens_in = tokens_in + VALUES(tokens_in),
                        tokens_out = tokens_out + VALUES(tokens_out)
                    """,
                    (tid, day, req, tin, tout),
                )

                if reset_redis:
                    # 清零热账本，避免下次 flush 重复加
                    redis_client.delete(key)
                redis_client.srem(dirty_key, tid)
                ok += 1
        conn.commit()
    finally:
        conn.close()
    return ok