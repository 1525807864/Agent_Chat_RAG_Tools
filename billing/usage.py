"""P4: 简易用量账本（进程内）。商用应落库。"""

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
                return dict(self.data.get(tenant_id, {}))
            return {k: dict(v) for k, v in self.data.items()}


LEDGER = UsageLedger()
