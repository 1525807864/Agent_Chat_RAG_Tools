"""租户级语义记忆持久化（文件 JSONL，可渐进迁 MySQL）。

商业约束：
- 路径按 tenant_id 隔离，session_id 做安全化，防路径穿越
- append-only，便于审计与回放
- 单文件过大时可按日切分（本期不做，预留注释）
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any

from memory.observability import memory_event, memory_warn

_log = logging.getLogger(__name__)

# 仅允许字母数字与 -_，其余替换，限制长度
_SAFE_RE = re.compile(r"[^a-zA-Z0-9_\-]+")


def _safe_id(raw: str, *, max_len: int = 180) -> str:
    s = _SAFE_RE.sub("_", (raw or "").strip()) or "unknown"
    return s[:max_len]


class SemanticMemoryStore:
    """语义 / 事实记忆仓库（Mem0 风格 durable facts 的本地实现）。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        _log.info("SemanticMemoryStore ready root=%s", self.root)

    def _session_file(self, tenant_id: str, session_id: str) -> Path:
        d = self.root / _safe_id(tenant_id, max_len=64)
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{_safe_id(session_id)}.jsonl"

    def append(
        self,
        *,
        tenant_id: str,
        session_id: str,
        text: str,
        kind: str,
        importance: float,
        meta: dict | None = None,
    ) -> str:
        """追加一条事实；返回 item_id。"""
        item_id = uuid.uuid4().hex
        row = {
            "id": item_id,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "text": (text or "")[:800],
            "kind": kind or "fact",
            "importance": float(importance),
            # score_hint 兼容旧 RelevanceFilter / HybridMemoryRetriever
            "score_hint": float(importance),
            "meta": meta or {},
            "ts": time.time(),
        }
        path = self._session_file(tenant_id, session_id)
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            memory_event(
                "semantic_append",
                tenant_id=tenant_id,
                session_id=session_id,
                kind=kind,
                item_id=item_id,
                text_preview=(text or "")[:80],
            )
        except OSError as e:
            memory_warn(
                "semantic_append_failed",
                e,
                tenant_id=tenant_id,
                session_id=session_id,
            )
            raise
        return item_id

    def load_session(self, tenant_id: str, session_id: str) -> list[dict[str, Any]]:
        """加载该会话全部语义条目（调用方再做 top_k）。"""
        path = self._session_file(tenant_id, session_id)
        if not path.exists():
            return []
        items: list[dict[str, Any]] = []
        bad = 0
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    bad += 1
        except OSError as e:
            memory_warn(
                "semantic_load_failed",
                e,
                tenant_id=tenant_id,
                session_id=session_id,
            )
            return []
        if bad:
            memory_warn(
                "semantic_load_corrupt_lines",
                f"bad_lines={bad}",
                tenant_id=tenant_id,
                session_id=session_id,
            )
        memory_event(
            "semantic_load",
            tenant_id=tenant_id,
            session_id=session_id,
            count=len(items),
        )
        return items
