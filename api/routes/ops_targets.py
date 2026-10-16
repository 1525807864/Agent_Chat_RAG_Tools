"""运维目标（客户项目）CRUD。凭证只可写不可读"""
from __future__ import annotations 
from typing import Any 
from fastapi import APIRouter,Depends,HTTPException  
from pydantic import BaseModel,Field 
from api.auth.deps import AuthUser, get_current_user
from application.ops import targets as tgt_store

# 前缀必须带前导 /，否则挂不到 /api/ops/targets
router = APIRouter(prefix="/api/ops/targets", tags=["ops-targets"])

class TargetCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    # platform | remote_agent | dedicated_holmes
    targetType: str = Field(default="remote_agent", max_length=32)
    endpointBase: str | None = Field(default=None, max_length=1024)
    # 明文只在创建/更新时传入一次，入库即加密
    authToken: str | None = Field(default=None, max_length=8192)
    kubeconfig: str | None = Field(default=None, max_length=200_000)
    defaultNamespace: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=1000)
    enabled: bool = True

class TargetUpdateBody(BaseModel):
    name: str | None = Field(default=None, max_length=256)
    endpointBase: str | None = Field(default=None, max_length=1024)
    authToken: str | None = Field(default=None, max_length=8192)
    kubeconfig: str | None = Field(default=None, max_length=200_000)
    defaultNamespace: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=1000)
    enabled: bool | None = None
    # 显式清空凭证
    clearAuthToken: bool = False
    clearKubeconfig: bool = False

@router.get("")
async def list_ops_targets(
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """列出本租户全部目标（不含明文凭证）。"""
    items = tgt_store.list_targets(user.tenant_id)
    return {"items": [tgt_store.to_public_dict(t) for t in items]}

@router.post("")
async def create_ops_target(
    body: TargetCreateBody,
    user: AuthUser = Depends(get_current_user),
)->dict[str,Any]:
    """创建目标"""
    try:
        t = tgt_store.create_target(
            tenant_id=user.tenant_id,
            name=body.name,
            target_type=body.targetType,
            created_by=user.user_id,
            endpoint_base=body.endpointBase,
            auth_token=body.authToken,
            kubeconfig=body.kubeconfig,
            default_namespace=body.defaultNamespace,
            notes=body.notes,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return tgt_store.to_public_dict(t)

@router.patch("/{target_id}")
async def patch_ops_target(
    target_id: str,
    body: TargetUpdateBody,
    user: AuthUser = Depends(get_current_user),
)->dict[str,Any]:
    """更新目标"""
    try:
        t = tgt_store.update_target(
            tenant_id=user.tenant_id,
            target_id=target_id,
            name=body.name,
            enabled=body.enabled,
            endpoint_base=body.endpointBase,
            auth_token=body.authToken,
            kubeconfig=body.kubeconfig,
            default_namespace=body.defaultNamespace,
            notes=body.notes,
            clear_auth_token=body.clearAuthToken,
            clear_kubeconfig=body.clearKubeconfig,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="目标不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return tgt_store.to_public_dict(t)

@router.delete("/{target_id}")
async def delete_ops_target(
    target_id: str,
    user: AuthUser = Depends(get_current_user),
)->dict[str,Any]:
    """删除目标""" 
    ok = tgt_store.delete_target(user.tenant_id, target_id)
    if not ok:
        raise HTTPException(status_code=404, detail="目标不存在")
    return {"ok":True,"id":target_id}