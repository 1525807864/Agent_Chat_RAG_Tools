"""用量查询 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.auth.deps import AuthUser, get_current_user
from api.schemas import UsageResponse
from billing.usage import LEDGER

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/usage", response_model=UsageResponse)
async def get_usage(user: AuthUser = Depends(get_current_user)) -> UsageResponse:
    return UsageResponse(
        tenant_id=user.tenant_id,
        usage=LEDGER.snapshot(user.tenant_id),
    )
