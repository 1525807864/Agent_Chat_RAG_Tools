"""会话存储 + MemoryFacade 启动组装。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from memory.facade import MemoryFacade
from memory.session_store import create_session_store


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
    session_store = await create_session_store(backend=backend, **kwargs)

    mem_root = Path(settings.memdir_path)
    if not mem_root.is_absolute():
        mem_root = (project_root / mem_root).resolve()

    memory = MemoryFacade(
        session_store=session_store,
        llm=llm,
        project_root=project_root,
        window_size=settings.memory_window_size,
        solip_enabled=settings.memory_solip_enabled,
        solip_top_k=settings.memory_solip_top_k,
        relevance_top_k=settings.memory_relevance_top_k,
        memdir_root=mem_root,
    )
    return session_store, memory
