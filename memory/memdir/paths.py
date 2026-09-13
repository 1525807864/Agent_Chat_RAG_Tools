"""
- 所有[记忆落在哪]的规则集中在一起，避免sotre/facade各写各的
- 方便以后改成SQlite时只换store,paths语义仍可复用(project/session分区)
"""
from __future__ import annotations 
from pathlib import Path 

def default_memdir_path(project_root:Path)->Path:
    """默认根:<项目录>/data/memdir"""
    return (project_root/ "data" / "memdir").resolve()

def project_memdir_path(root:Path)->Path:
    """项目级记忆（跨session共享），如用户长期偏好等等"""
    return root / "project_memory.json"

def session_memdir_file(root:Path,session_id:str)->Path:
    """会话级记忆：摘要沉淀、本会话Solip、open_loos等"""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
    safe = safe[:128] or "default"
    return root / "sessions" / f"{safe}.json" 

   
