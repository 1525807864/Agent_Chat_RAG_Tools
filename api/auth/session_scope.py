"""把客户端 session_id 绑到当前租户，防止跨租户读写会话。"""

from __future__ import annotations

from fastapi import HTTPException

SEP = "::"


def bind_session_id(tenant_id: str, session_id: str) -> str:
    """返回入库用的 ``{tenant}::{id}``。带错租户前缀则 404，避免探测。"""
    sid = (session_id or "").strip()
    if not sid or len(sid) > 128:
        raise HTTPException(status_code=400, detail="非法 session_id")
    if "/" in sid or "\\" in sid or "\x00" in sid:
        raise HTTPException(status_code=400, detail="非法 session_id")
    if SEP in sid:
        left, right = sid.split(SEP, 1)
        if left != tenant_id or not right:
            raise HTTPException(status_code=404, detail="session not found")
        return sid
    return f"{tenant_id}{SEP}{sid}"


def public_session_id(tenant_id: str, stored_id: str) -> str | None:
    """仅当会话属于该租户时返回给前端的短 id。"""
    prefix = f"{tenant_id}{SEP}"
    if stored_id.startswith(prefix):
        return stored_id[len(prefix) :]
    # 兼容旧数据：无前缀的会话只对 default 租户可见
    if tenant_id == "default" and SEP not in stored_id:
        return stored_id
    return None
