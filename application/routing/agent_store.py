"""会话和cursor agnet_id的对应关系，不关系消息内容"""
from __future__ import annotations  
import json 
from pathlib import Path

from application.tenancy import tenant_root 

def _safe_session(session_id:str)->str:
    """session_id 里有default::这种前缀，不能直接当文件名"""
    safe = "".join(
        ch if ch.isalnum() or ch in "-_" else "_" for ch in (session_id or "default")
    )
    return safe or "default" #默认还是default 

def _path(project_root:Path,tenant_id:str,session_id:str)->Path:
    """按租户id和会话id找文件，例：data/tenants/acme/agent_sessions/default.json"""
    dir = tenant_root(project_root,tenant_id) / "cursor_agents"
    return dir / f"{_safe_session(session_id)}.json"

def load_agent_id(project_root:Path,tenant_id:str,session_id:str)->str:
    """加载租户会话对应的cursor agent_id，没有就返回None"""
    path = _path(project_root,tenant_id,session_id)
    if not path.is_file(): 
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8")) 
    except (OSError,json.JSONDecodeError):
        return ""
    return str(data.get("agent_id","") or "")

def save_agent_id(
    project_root: Path,
    tenant_id: str,
    session_id: str, 
    agent_id: str,
)->None:
    path = _path(project_root,tenant_id,session_id)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(
        json.dumps({"agent_id":agent_id},ensure_ascii=False),
        encoding="utf-8",
    )

