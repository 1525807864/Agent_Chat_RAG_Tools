# 评测用例的schema 

from __future__ import annotations 
from dataclasses import dataclass,field 
from typing import Any,Literal 

PassMode = Literal["pass_at_k","pass_hat_k"]
JudgeType = Literal["deterministic", "checklist", "rubric_llm"]
MatchMode = Literal["subset","superset","unordered","strict"]

@dataclass 
class EvalInput:
    """一次请求打进系统的输入"""
    mode: str = "chat"
    message: str = ""
    tenant_id: str = "default"
    session_id: str | None = None 
    multi_mode: str = "sequential"
    extra: dict[str,Any] = field(default_factory=dict)

@dataclass 
class EvalExpect:
    """一次请求打进系统的输出期望"""
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    match_any_of_must_contain: bool = False 

@dataclass 
class EvalJudge:
    """语义评判配置(Rubric LLM)"""
    type: JudgeType = "rubric_llm"
    threshold: float = 0.6
    criteria: str = "" #GEval准则

@dataclass 
class EvalTrajectory:
    expected_tools: list[str] = field(default_factory=list)
    match_mode: MatchMode = "subset"
    # None = 不限制次数；用于「最多搜一次」类约束
    max_tool_calls: int | None = None

@dataclass
class EvalCase:
    """一条完整用例=题面+期望+评判+轨迹+重复次数策略"""
    id: str 
    domain: str = "E1"
    tags: list[str] = field(default_factory=list)
    # 默认业务可靠（Pass^k）；能力探索题在 YAML 里显式写 pass_at_k
    pass_mode: PassMode = "pass_hat_k"
    k: int = 1
    input: EvalInput = field(default_factory=EvalInput)
    expect: EvalExpect = field(default_factory=EvalExpect)
    judge: EvalJudge = field(default_factory=EvalJudge)
    trajectory: EvalTrajectory = field(default_factory=EvalTrajectory)
    def is_p0(self)->bool:
        return "p0" in {t.lower() for t in self.tags}

    