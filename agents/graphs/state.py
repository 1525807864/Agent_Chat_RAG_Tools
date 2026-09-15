"""
用一个state类管理所有状态
"""
from __future__ import annotations
from operator import add 
from typing import Annotated,Any,Literal,TypedDict 

def merge_dicts(left:dict[str,Any],right:dict[str,Any])->dict[str,Any]:
    out = dict(left or {})
    out.update(right or {})
    return out 

class MultiAgentState(TypedDict,total=False):
    task:str
    mode:Literal["sequential","debate","router"]
    current: str
    last_agent: str
    selected: str
    debate_round: int 
    max_debate_rounds: int 
    success: bool 
    error: str
    agent_outputs: Annotated[dict[str,Any],merge_dicts]
    execution_log: Annotated[list[str],add]
    opinions: Annotated[list[str],add]