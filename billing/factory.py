"""根据 Settings 选择账本实现（DIP：上层只依赖 Port）。"""

from __future__ import annotations

from typing import Any

from billing.usage import UsageLedger
from domain.ports import UsageLedgerPort


def create_usage_ledger(settings: Any) -> UsageLedgerPort:
    """优先 Redis；连不上则回退内存，保证本地无 Redis 也能跑。"""
    url = (getattr(settings, "redis_url", None) or "").strip()
    if url:
        try:
            from billing.redis_ledger import RedisUsageLedger

            ledger = RedisUsageLedger(url)
            ledger._r.ping()
            return ledger
        except Exception:
            pass
    return UsageLedger()
