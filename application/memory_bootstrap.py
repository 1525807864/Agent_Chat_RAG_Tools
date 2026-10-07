"""会话存储 + MemoryFacade 启动组装（含 Memory V2 商业组件）。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from memory.facade import MemoryFacade
from memory.semantic.retriever import HybridMemoryRetriever
from memory.semantic.store import SemanticMemoryStore
from memory.session_store import create_session_store

_log = logging.getLogger(__name__)


def _try_build_embed_fn(settings: Any) -> Callable[[str], list[float]] | None:
    """有 Embedding Key 才启用 dense 召回；否则纯关键词（fail-open）。"""
    key = (getattr(settings, "embedding_api_key", None) or "").strip()
    if not key:
        _log.info("Memory V2: 无 EMBEDDING_API_KEY，混合召回降级为关键词")
        return None
    try:
        from infrastructure.embeddings.factory import create_embeddings

        emb = create_embeddings()

        def _embed(text: str) -> list[float]:
            return list(emb.embed_query(text or ""))

        _log.info("Memory V2: embedding 召回已启用 model=%s", settings.embedding_model)
        return _embed
    except Exception as e:  # noqa: BLE001
        _log.warning("Memory V2: embedding 初始化失败，降级关键词: %s", e)
        return None


async def bootstrap_session_memory(
    *,
    settings: Any,
    project_root: Path,
    llm: Any,
) -> tuple[Any, MemoryFacade]:
    """返回 (session_store, memory)。"""
    backend = settings.memory_backend
    kwargs: dict = {}
    if backend == "redis":
        kwargs["redis_url"] = settings.redis_url
        kwargs["ttl_seconds"] = settings.memory_ttl_seconds
    elif backend == "sqlite":
        kwargs["db_path"] = settings.sqlite_db_path
    elif backend == "mysql":
        # mysql_session_store 由 create_session_store 内部读 settings
        pass
    session_store = await create_session_store(backend=backend, **kwargs)

    mem_root = Path(settings.memdir_path)
    if not mem_root.is_absolute():
        mem_root = (project_root / mem_root).resolve()

    v2 = bool(getattr(settings, "memory_v2_enabled", False))
    semantic_store = None
    retriever = HybridMemoryRetriever()
    if v2:
        sem_root = Path(getattr(settings, "memory_semantic_path", "data/memory_semantic"))
        if not sem_root.is_absolute():
            sem_root = (project_root / sem_root).resolve()
        semantic_store = SemanticMemoryStore(sem_root)
        retriever = HybridMemoryRetriever(embed_fn=_try_build_embed_fn(settings))
        _log.info(
            "Memory V2 bootstrap: rewrite=%s fact_extract=%s semantic_root=%s",
            getattr(settings, "memory_query_rewrite_enabled", True),
            getattr(settings, "memory_fact_extract_enabled", True),
            sem_root,
        )

    memory = MemoryFacade(
        session_store=session_store,
        llm=llm,
        project_root=project_root,
        window_size=settings.memory_window_size,
        solip_enabled=settings.memory_solip_enabled,
        solip_top_k=settings.memory_solip_top_k,
        relevance_top_k=settings.memory_relevance_top_k,
        memdir_root=mem_root,
        v2_enabled=v2,
        query_rewrite_enabled=bool(
            getattr(settings, "memory_query_rewrite_enabled", True)
        ),
        fact_extract_enabled=bool(
            getattr(settings, "memory_fact_extract_enabled", True)
        ),
        semantic_store=semantic_store,
        retriever=retriever,
        semantic_top_k=int(getattr(settings, "memory_semantic_top_k", 6)),
        summary_max_tokens=int(getattr(settings, "memory_summary_max_tokens", 480)),
        compress_min_messages=int(getattr(settings, "memory_compress_min_messages", 12)),
        compress_max_context_tokens=int(
            getattr(settings, "memory_compress_max_context_tokens", 3500)
        ),
    )
    return session_store, memory
