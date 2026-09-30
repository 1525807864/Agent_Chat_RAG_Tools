"""给聊天路由用的唯一入口：要么返回 Cursor 的回答，要么返回 None 表示继续走 DeepSeek。"""

from __future__ import annotations

from pathlib import Path

from application.routing.policy import decide
from infrastructure.db.session_routing_store import load_agent_id, save_agent_id


def project_root() -> Path:
    """application/routing/handoff.py 往上两级就是仓库根。"""
    return Path(__file__).resolve().parents[2]


async def try_cursor_answer(
    *,
    mode: str,
    message: str,
    session_id: str,
    tenant_id: str,
    api_key: str,
    model: str,
    workspace_root: str | None,
) -> tuple[str, dict] | None:
    """返回 (answer, extra) 表示这条已经由 Cursor 回答。

    返回 None 表示调用方应继续原来的 ask_chat / ask_agent。
    """
    choice = decide(mode, message, has_cursor_key=bool(api_key))
    if choice.provider != "cursor":
        return None

    # SDK 没装好时退回 DeepSeek，避免整站聊天起不来。
    try:
        from cursor_sdk import CursorAgentError

        from application.routing.cursor_runner import CursorRunner
    except ImportError:
        return None

    root = project_root()
    # 用户传了存在的工作区就用它；否则用仓库根。Cursor 会改这个目录里的文件。
    cwd = workspace_root if workspace_root and Path(workspace_root).is_dir() else str(root)
    saved = load_agent_id(root, tenant_id, session_id)
    try:
        answer, agent_id = await CursorRunner(api_key, model, cwd).ask(message, saved)
    except CursorAgentError:
        # 没启动成功，退回 DeepSeek。已经跑失败的 RuntimeError 不在这里吞掉。
        return None
    except Exception:
        return None 

    if agent_id:
        save_agent_id(root, tenant_id, session_id, agent_id)
    return answer, {
        "provider": "cursor",
        "route_reason": choice.reason,
        "cursor_agent_id": agent_id,
    }
