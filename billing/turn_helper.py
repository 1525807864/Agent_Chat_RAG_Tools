"""统一finalize+safe_record，方便编排层调用"""
#全mode共用的[回合收尾]工具
#把多跳累加的TurnUsage汇总成前端需要的meta,并写入唯一账本Usageleger 
from __future__ import annotations 
from typing import Any 
from billing.extract import merge_usage #多段usage合并 
from billing.recorder import record_turn 
from domain.usage import TurnUsage #不可变用量值对象

def empty_turn(*,model:str="")->TurnUsage:
    """空回合，用于开局/跳过/中断等场景"""
    return TurnUsage(
        tokens_in=0,
        tokens_out=0,
        requests=0,
        model=model,
    )

def finalize_turn(
    turn:TurnUsage,*,model:str=""
)->TurnUsage:
    """
    无论内部llm调了几次，对账本只记得requests=1,并合并token用量 
    """
    return TurnUsage(
        tokens_in=int(turn.tokens_in),
        tokens_out=int(turn.tokens_out),
        requests=1, #强制1，覆盖merge里累加的requests
        model=(model or turn.model or "")
    )

def safe_record_turn(
    app:Any,
    tenant_id: str,
    turn: TurnUsage,
    *,
    model:str=""
)->dict:
    """
    安全地记录回合用量，并返回前端meta 
    """
    final = finalize_turn(turn,model=model)
    # 从门面取唯一账本(reids或内存)，没有就只返回字典
    ledger = getattr(app,"usage_ledger",None)
    if ledger is None:
        return {"usage":final.to_dict()}
    try:
        return record_turn(ledger,tenant_id,final)
    except Exception as exc:
        # 写入失败，返回字典但不清账本
        logger = getattr(app,"logger",None)
        if logger is not None:
            logger.error(f"用量收集失败: {exc}")
        return {"usage":final.to_dict()}


def merge_message(
    acc: TurnUsage,
    msg: object,
    *,
    model:str=""
)->TurnUsage:
    """
    合并消息中的usage，确保requests=1
    """
    from billing.extract import usage_from_message
    piece = usage_from_message(msg,model=model)
    # 合并多段usage，确保requests=1
    return merge_usage(acc,piece)

