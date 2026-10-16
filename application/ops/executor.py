"""
按OpsTarget路由一次调查
- platform: 本平台HOLMES_API_BASE
- remote_agent: 客户Agent地址；执行器从API获取
- dedicated_holmes: 客户专用Holmes地址；执行器从API获取
"""
from __future__ import annotations 
from typing import Any 
from application.ops.holmes_client import HolmesClient, HolmesError
from application.ops.targets import OpsTarget, get_target
from config.settings import get_settings

class OpsExecError(Exception):
    """执行异常"""
    def __init__(self,message:str,*,status_code:int | None = None)->None:
        super().__init__(message)
        self.status_code = status_code 

def _enrich_message(message: str, target: OpsTarget) -> str:
    """把目标元数据拼进 ask，方便模型/工具知道默认 ns（不传密钥）。"""
    parts = [(message or "").strip()]
    meta = [
        f"targetId={target.id}",
        f"targetName={target.name}",
        f"targetType={target.target_type}",
    ]
    if target.default_namespace:
        meta.append(f"defaultNamespace={target.default_namespace}")
    parts.append(
        "\n\n---\n[Nexora Ops Target]\n" + "\n".join(meta) + "\n---"
    )
    return "".join(parts)

def resolve_client(target:OpsTarget)->HolmesClient:
    """根据类型构造HTTP客户端"""
    s = get_settings()
    if target.target_type == "platform":
        return HolmesClient()
    if target.target_type in ("remote_agent","dedicated_holmes"):
        if not target.endpoint_base:
            raise OpsExecError(f"目标类型{target.target_type}必须提供 endpoint_base",status_code=400)
        return HolmesClient(
            base=target.endpoint_base,
            # 客户 Agent / 专用 Holmes 的 token（已解密）
            api_key=target.auth_token if target.auth_token is not None else "",
            default_model=s.holmes_default_model,
            timeout=s.holmes_timeout_sec,
        )
    raise OpsExecError(f"未知目标类型: {target.target_type}",status_code=400)

def ask_on_target(
    *,
    tenant_id: str,
    target_id: str | None,
    message: str,
    conversation_history: list[dict[str, Any]] | None,
    model: str | None,
    user_id: str | None,
) -> tuple[OpsTarget, dict[str, Any]]:
    """供 /api/ops/ask 调用：校验租户 → 取目标 → HTTP 调查。"""
    tid = (tenant_id or "").strip()
    if not tid:
        raise OpsExecError("租户ID不能为空", status_code=400)
    tgt_id = (target_id or "").strip()
    if not tgt_id:
        raise OpsExecError(
            "必须指定 targetId（先在运维页选择或登记客户项目）",
            status_code=400,
        )
    target = get_target(tid, tgt_id, for_exec=True)
    if target is None:
        raise OpsExecError("运维目标不存在或无权访问", status_code=404)
    if not target.enabled:
        raise OpsExecError("该运维目标已禁用", status_code=403)
    client = resolve_client(target)
    try:
        data = client.ask(
            message=_enrich_message(message,target),
            conversation_history=conversation_history,
            model=model,
            user_id=user_id,
            stream=False,
        )
    except HolmesError as exc:
        # 原样上抛，路由转 HTTP
        raise OpsExecError(str(exc), status_code=exc.status_code or 502) from exc
    return target, data