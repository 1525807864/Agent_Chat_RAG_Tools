"""组装 AccessService（进程内单例）。"""

from __future__ import annotations

from application.access.service import AccessService
from config.settings import get_settings
from infrastructure.access.memory_member_store import MemoryMemberStore
from infrastructure.access.mysql_member_store import MysqlMemberStore
from utils.logger import get_logger

_log = get_logger("nexora.access.factory")
_svc: AccessService | None = None


def get_access_service() -> AccessService:
    """按鉴权后端选择成员存储：mysql 用表，其它用进程内存（本地开发）。"""
    global _svc
    if _svc is None:
        backend = (get_settings().auth_backend or "mysql").strip().lower()
        if backend == "mysql":
            store = MysqlMemberStore()
            _log.info("AccessService 使用 MysqlMemberStore")
        else:
            store = MemoryMemberStore()
            _log.info("AccessService 使用 MemoryMemberStore (auth_backend=%s)", backend)
        _svc = AccessService(store)
    return _svc


def reset_access_service_for_tests() -> None:
    """单测重置单例。"""
    global _svc
    _svc = None
