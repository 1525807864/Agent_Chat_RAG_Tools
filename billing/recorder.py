"""记一笔用量并组装前端需要的meta"""
from __future__ import annotations 
from domain.ports import UsageLedgerPort 
from domain.usage import TurnUsage 

def record_turn(
    ledger: UsageLedgerPort,
    tenant_id: str,
    turn: TurnUsage,
)->dict:
    """
    1）写入redis/内存账本
    2) 返回{usage,tenant_usage}给RunResult.meta 
    """
    # 热路径只打账本，不碰mysql 
    ledger.add(
        tenant_id,
        requests=turn.requests,
        tokens_in=turn.tokens_in,
        tokens_out=turn.tokens_out,
    )
    # 读回累计，给顶栏/气泡旁[租户合计]
    snap = ledger.snapshot(tenant_id)
    return {
        "usage": turn.to_dict(),
        "tenant_usage": {
            "requests": int(snap.get("requests",0)),
            "tokens_in": int(snap.get("tokens_in",0)),
            "tokens_out": int(snap.get("tokens_out",0)),
        },
    }