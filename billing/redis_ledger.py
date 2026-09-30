"""Redis 用量账本：高频 HINCRBY，绝不在这里写 MySQL。"""

from __future__ import annotations

from typing import Any

# redis 同步客户端即可（用量写入很快；若要全 async 可再换 redis.asyncio）
import redis


class RedisUsageLedger:
    """实现 UsageLedgerPort：每个租户一个 HASH。"""

    def __init__(self, redis_url: str) -> None:
        # 解析连接串，例如 redis://redis:6379/0
        self._r = redis.Redis.from_url(redis_url, decode_responses=True)
        # 脏集合：后续 MySQL flush 只扫有变更的租户（本期可先不用）
        self._dirty_key = "usage:dirty"

    def _key(self, tenant_id: str) -> str:
        # 统一 key，避免租户 id 污染命名空间
        tid = (tenant_id or "default").strip() or "default"
        return f"usage:tenant:{tid}"

    def add(
        self,
        tenant_id: str,
        *,
        requests: int = 1,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        """原子累加；失败时由上层决定是否吞掉（建议打日志，别让聊天挂掉）。"""
        key = self._key(tenant_id)
        pipe = self._r.pipeline()
        # 三个字段分别累加
        pipe.hincrby(key, "requests", int(requests))
        pipe.hincrby(key, "tokens_in", int(tokens_in))
        pipe.hincrby(key, "tokens_out", int(tokens_out))
        # 标记脏租户，供以后批量刷 MySQL
        pipe.sadd(self._dirty_key, (tenant_id or "default").strip() or "default")
        pipe.execute()

    def snapshot(self, tenant_id: str | None = None) -> dict[str, Any]:
        """读快照；单租户返回 {requests, tokens_in, tokens_out}。"""
        if tenant_id:
            raw = self._r.hgetall(self._key(tenant_id)) or {}
            return {
                "requests": int(raw.get("requests") or 0),
                "tokens_in": int(raw.get("tokens_in") or 0),
                "tokens_out": int(raw.get("tokens_out") or 0),
            }
        # 全量：扫 dirty 或 SCAN key（生产建议只查当前租户，勿扫全库）
        out: dict[str, Any] = {}
        for tid in self._r.smembers(self._dirty_key) or []:
            out[str(tid)] = self.snapshot(str(tid))
        return out

    def flush_to_mysql(self,*,reset:bool=True)->int:
        """把脏租户刷进mysql：供定时任务/管理接口调用。"""
        from billing.mysql_flush import flush_dirty_tenants
        return flush_dirty_tenants(self._r,reset_redis=reset)