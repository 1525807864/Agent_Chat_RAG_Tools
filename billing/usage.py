"""P4: 简易用量账本（进程内）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class UsageLedger:
    data: dict[str, dict[str, int]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def add(
        self,
        tenant_id: str,
        *,
        requests: int = 1,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        tid = tenant_id or "default"
        with self._lock:
            row = self.data.setdefault(
                tid, {"requests": 0, "tokens_in": 0, "tokens_out": 0}
            )
            row["requests"] += requests
            row["tokens_in"] += tokens_in
            row["tokens_out"] += tokens_out

    def snapshot(self, tenant_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            if tenant_id:
                row = self.data.get(tenant_id) or {}
                return {
                    "requests": int(row.get("requests") or 0),
                    "tokens_in": int(row.get("tokens_in") or 0),
                    "tokens_out": int(row.get("tokens_out") or 0),
                }
            return {k: dict(v) for k, v in self.data.items()}

    def flush_to_mysql(self, *, reset: bool = True) -> int:
        """内存账本无法刷库；保持与 RedisUsageLedger 同签名。"""
        _ = reset
        return 0


LEDGER = UsageLedger()
