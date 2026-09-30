"""领域用量值对象：不依赖Redis / FastApi / LangChain 等基础设施"""
from __future__ import annotations 
from dataclasses import dataclass 

@dataclass(frozen=True)
class TurnUsage:
    """一轮对话的token用量（不可变，方便传递meta）"""
    tokens_in: int = 0  #输入token
    tokens_out: int = 0  #输出token
    requests: int = 1 #本轮请求次数
    model: str = "" #模型名 

    @property
    def tokens_total(self)->int:
        """总token"""
        return self.tokens_in + self.tokens_out  
    
    def to_dict(self)->dict:
        """转字典"""
        return {
            "tokens_in": int(self.tokens_in),
            "tokens_out": int(self.tokens_out),
            "tokens_total": int(self.tokens_total),
            "requests": int(self.requests),
            "model": str(self.model),
        }

