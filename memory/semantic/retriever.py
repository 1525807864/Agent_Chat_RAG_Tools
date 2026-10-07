"""语义记忆召回：关键词 +（可选）embedding 余弦 —— 商业混合检索。

无 embedding 时降级纯关键词，与旧 RelevanceFilter 行为兼容。
"""

from __future__ import annotations

import logging
import math
import re
import time
from typing import Any, Callable

from memory.observability import memory_event, memory_warn

_log = logging.getLogger(__name__)


def _tokenize(text: str) -> set[str]:
    text = (text or "").lower()
    return set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{1,4}", text))


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(y * y for y in b)) or 1e-9
    return dot / (na * nb)


class HybridMemoryRetriever:
    """混合召回器（Mem0 / Zep 常见：sparse + dense）。"""

    def __init__(
        self,
        *,
        embed_fn: Callable[[str], list[float]] | None = None,
        min_score: float = 0.05,
    ) -> None:
        self.embed_fn = embed_fn
        self.min_score = min_score

    def retrieve(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        *,
        top_k: int = 6,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []
        t0 = time.perf_counter()
        q_tok = _tokenize(query)
        q_vec: list[float] | None = None
        if self.embed_fn:
            try:
                q_vec = self.embed_fn(query)
            except Exception as e:  # noqa: BLE001
                memory_warn("embed_query_failed", e, query_preview=(query or "")[:60])
                q_vec = None

        scored: list[tuple[float, dict[str, Any]]] = []
        for it in candidates:
            text = str(it.get("text") or "")
            overlap = (
                len(q_tok & _tokenize(text)) / max(1, len(q_tok)) if q_tok else 0.0
            )
            imp = float(it.get("importance") or it.get("score_hint") or 0.5)
            sem = 0.0
            if q_vec is not None and self.embed_fn:
                try:
                    v = it.get("embedding")
                    if not isinstance(v, list):
                        v = self.embed_fn(text)
                    sem = _cosine(q_vec, v)  # type: ignore[arg-type]
                except Exception as e:  # noqa: BLE001
                    memory_warn(
                        "embed_doc_failed",
                        e,
                        item_id=it.get("id"),
                    )
                    sem = 0.0
            # 地点类对「天气」类 query 轻微加权（商业启发式，可配置化）
            kind = str(it.get("kind") or "")
            kind_boost = 0.08 if kind == "location" and re.search(
                r"(天气|下雨|气温|温度)", query or ""
            ) else 0.0
            score = 0.45 * overlap + 0.40 * sem + 0.15 * imp + kind_boost
            if score >= self.min_score:
                scored.append((score, it))

        scored.sort(key=lambda x: x[0], reverse=True)
        hits = [it for _, it in scored[:top_k]]
        memory_event(
            "hybrid_retrieve",
            candidates=len(candidates),
            hits=len(hits),
            top_k=top_k,
            used_embedding=bool(q_vec),
            latency_ms=int((time.perf_counter() - t0) * 1000),
            query_preview=(query or "")[:80],
            top_score=round(scored[0][0], 4) if scored else 0.0,
        )
        return hits
