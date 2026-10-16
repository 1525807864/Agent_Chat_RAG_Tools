"""用量查询 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.auth.access_deps import require_perm
from api.auth.deps import AuthUser
from api.deps import get_agent_app
from api.schemas import UsageResponse
from application.services.agent_application import AgentApplication
from domain.access import PERM_BILLING_ADMIN, PERM_BILLING_READ

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    user: AuthUser = Depends(require_perm(PERM_BILLING_READ)),
    app: AgentApplication = Depends(get_agent_app),
) -> UsageResponse:
    return UsageResponse(
        tenant_id=user.tenant_id,
        usage=app.usage_ledger.snapshot(user.tenant_id),
    )


@router.post("/flush")
async def flush_usage(
    user: AuthUser = Depends(require_perm(PERM_BILLING_ADMIN)),
    app: AgentApplication = Depends(get_agent_app),
) -> dict:
    """把 Redis 脏租户刷进 MySQL usage_events / usage_daily。

    仅当 usage_ledger 实现了 flush_to_mysql（Redis 账本）时有效。
    """
    flush = getattr(app.usage_ledger, "flush_to_mysql", None)
    if flush is None or not callable(flush):
        raise HTTPException(
            status_code=501,
            detail="当前用量账本不支持 flush（请用 RedisUsageLedger）",
        )
    try:
        n = int(flush(reset=True))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"flush 失败: {e}") from e
    return {"flushed_tenants": n, "tenant_id": user.tenant_id}
