"""
记录：建库时每个源文件一条，给检索时当结构化证据
会话记录：对话过程中用户不上的因子，按session_id存
"""
from __future__ import annotations 
import json 
from pathlib import Path  
from rag.structured.schema import empty_factor_dict #空因子模板

def save_record(path:Path,records:list[dict])->None:
    """整份覆盖写入租户因子记录"""
    path.parent.mkdir(parents=True,exist_ok=True) #目录不存在就建 
    path.write_text(
        json.dumps({"records":records},ensure_ascii=False,indent=2), #中文不转义
        encoding="utf-8",
    )

def load_record(path:Path)->list[dict]:
    """读取因子记录，文件没有或坏了就返回空列表"""
    if not path.is_file(): #还没有建过库
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [] #坏文件直接返回空
    items = raw.get("records") if isinstance(raw,dict) else None #可能坏，但只要records
    return list(items or []) #列表套列表

def load_session_factors(path:Path,suffix:str="")->dict[str,str]:
    """读本会话已经填上的因子，没有文件就给空模板"""
    base = empty_factor_dict(suffix)#至少含有核心因子
    if not path.is_file(): #没有会话记录
        return base 
    
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return base 
    if not isinstance(saved,dict):
        return base 
    merged = dict(base) #以模板为底，避免旧文件缺新字段
    for key,value in saved.items():
        if value is None:
            continue 
        merged[str(key)] = str(value).strip()
    return merged  

def save_session_factors(path:Path,factors:dict[str,str])->None:
    """保存本会话已经填上的因子"""
    path.parent.mkdir(parents=True,exist_ok=True) #目录不存在就建 
    path.write_text(
        json.dumps(factors,ensure_ascii=False,indent=2), #中文不转义
        encoding="utf-8",
    )

def merge_factors(old:dict[str,str],new:dict[str,str])->dict[str,str]:
    """新值非空才覆盖，空字符串表示[这次没有抽到]，不能把旧值擦掉"""
    out = dict(old) #拷贝一份，避免改到全局
    for key,value in new.items():
        text = "" if value is None else str(value).strip()
        if text:
            out[str(key)] = text  
    return out 