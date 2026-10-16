"""FastAPI 依赖：把 AccessService 失败映射为 HTTP。

路由写法::

    user: AuthUser = Depends(require_perm(PERM_KB_WRITE))
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from api.auth.deps import AuthUser, get_current_user
from application.access.factory import get_access_service
from application.access.service import AccessError
from config.settings import get_settings
from utils.logger import get_logger

_log = get_logger("nexora.access.deps")


def require_perm(action: str):
    """校验当前用户是否拥有 action；AUTH_ENABLED=false 时直接放行。"""

    async def _dep(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        settings = get_settings()
        if not settings.auth_enabled:
            return user
        try:
            get_access_service().require(user.tenant_id, user.user_id, action)
        except AccessError as exc:
            raise HTTPException(status_code=403, detail=exc.message) from exc
        except Exception as exc:  # noqa: BLE001
            # 成员表尚未建好等基础设施故障：拒绝写操作更安全
            _log.exception("权限校验异常 action=%s", action)
            raise HTTPException(
                status_code=503,
                detail="权限服务暂时不可用，请稍后重试",
            ) from exc
        return user

    return _dep
