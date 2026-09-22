"""分配策略。只根据 mode 和消息文本做决定，方便以后加规则而不改 SDK。"""

from __future__ import annotations

from dataclasses import dataclass


# 普通 chat 里出现这些说法，才认为用户要改代码。
# 不要把「写一篇说明」这类话加进来，否则闲聊也会启动 Cursor。
_CODE_HINTS = (
    "改代码",
    "修改代码",
    "修bug",
    "修复bug",
    "重构",
    "写测试",
    "补测试",
    "改文件",
    "实现这个功能",
    "refactor",
    "fix the",
    "implement ",
)


@dataclass(frozen=True)
class RouteChoice:
    """一次分配结果。provider 只有 deepseek 或 cursor。"""

    provider: str
    reason: str


def decide(mode: str, message: str, *, has_cursor_key: bool) -> RouteChoice:
    """决定本条消息用哪个后端。

    rag / consult / graph-rag / multi 必须留在 DeepSeek，
    因为引用、因子和多智能体都不在 Cursor SDK 里。
    """
    # 没密钥就没有 Cursor 这条路，调用方不用再判断。
    if not has_cursor_key:
        return RouteChoice("deepseek", "no_cursor_key")

    # 知识库和协作模式不交给会改工作区的 Agent。
    if mode in {"rag", "consult", "graph-rag", "multi"}:
        return RouteChoice("deepseek", f"mode_{mode}")

    # agent 模式本身就是改代码，有密钥就走 Cursor。
    if mode == "agent":
        return RouteChoice("cursor", "mode_agent")

    text = (message or "").lower()
    # 普通聊天只有命中改代码说法才切过去。
    if mode == "chat" and any(hint in text for hint in _CODE_HINTS):
        return RouteChoice("cursor", "chat_code_hint")

    return RouteChoice("deepseek", "default_chat")