"""
后台任务领域模型，状态机与类型常量
API负责创建queued;worker负责running->done|failed 
禁止在HTTP请求线程里直接跑重计算
"""
from __future__ import annotations 
from dataclasses import dataclass,field 
from typing import Any,Optional 

JOB_KB_BUILD = "kb_build"
JOB_QA_UI_RUN = "qa_ui_run"
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running" 
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_DEAD = "dead" # 超时 / 意外失败 

TERMINAL = frozenset({STATUS_DONE,STATUS_FAILED,STATUS_DEAD})
# 状态机：queued->running->done|failed|dead

# 一次可追踪的任务，payload只放小json,大文件走租户目录
@dataclass 
class Job:
    id: str 
    job_type: str 
    tenant_id: str 
    user_id: str 
    status: str = STATUS_QUEUED 
    progress: int = 0 
    message: str = ""
    payload: dict[str,Any] = field(default_factory=dict)
    result: dict[str,Any] = field(default_factory=dict)
    error: Optional[str] = None 
    attempts: int = 0 
    def mark_running(self)->None:
        """标记为运行中"""
        self.status = STATUS_RUNNING 
        self.message = self.message or "正在运行..." 
    def mark_progress(self,pct:int,msg:str="")->None:
        """更新进度"""
        self.progress = max(0,min(100,int(pct)))
        if msg:
            self.message = msg 
    def mark_done(self,result:dict[str,Any] | None=None)->None:
        """标记为完成"""
        self.status = STATUS_DONE 
        self.progress = 100 
        self.message = "done"
        if result is not None:
            self.result = result  
        self.error = None 
    
    def mark_failed(self, err: str) -> None:
        self.status = STATUS_FAILED
        self.error = (err or "failed")[:2000]
        self.message = "failed"
