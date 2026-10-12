"""QA UI 测试：有头 Playwright MCP，逐步 yield 给 SSE。

流程
====
1. 弹出浏览器（headed session）
2. browser_navigate 打开用户填的 URL
3. browser_snapshot 看页面是否起来
4. 每步把 {type,i,action,detail,ok,error} 推给前端
5. finally 里 browser_close，窗口关掉

判定不经过 LLM：工具报错或页面明显失败才 fail。
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from langchain_core.tools import BaseTool

from e2e.mcp_playwright import playwright_mcp_session

_log = logging.getLogger(__name__)


def _find_tool(tools: list[BaseTool], *names: str) -> BaseTool | None:
    """按名字找 MCP 工具；兼容官方改名（含子串）。"""
    lower_map = {t.name.lower(): t for t in tools}
    for n in names:
        hit = lower_map.get(n.lower())
        if hit:
            return hit
    for t in tools:
        tn = t.name.lower()
        if any(n.lower() in tn for n in names):
            return t
    return None


def _flatten_tool_text(raw:Any)->str:
    """把MCP/LangChain返回收回纯文本，避免list/dict原样进前端。"""
    if raw is None:
        return ""
    if isinstance(raw,str):
        return raw 
    if isinstance(raw,list):
        parts: list[str] = []
        for item in raw:
            if isinstance(item,dict) and isinstance(item.get("text"),str):
                parts.append(item["text"])
            else:
                parts.append(_flatten_tool_text(item)) # 递归处理
        return "\n".join(p for p in parts if p)
    if isinstance(raw,dict):
        if isinstance(raw.get("text"),str):
            return raw["text"]
        if isinstance(raw.get("content"),str):
            return raw["content"]
        return str(raw)
    return str(raw)

async def _call(tool:BaseTool,payload:dict[str,Any]|None=None)->str:
    """调用一条MCP工具，统一收成字符串。"""
    data = payload or {}
    try:
        if hasattr(tool,"ainvoke"):
            raw = await tool.ainvoke(data)
        else:
            raw = tool.invoke(data)
        return _flatten_tool_text(raw)
    except Exception as exc: # noqa: BLE001
        return f"工具调用失败: {exc}"
    
def _looks_fail(text:str)->bool:
    """禁止把setTimeout / 快照YAML误判成fail。"""
    t = (text or "").strip()
    if not t:
        return False 
    if t.startswith("工具调用失败"):
        return True 
    if t.startswith("URL 校验失败") or t.startswith("浏览器导航失败"):
        return True 
    low = t.lower()
    if "waited for" in low and "settimeout" in low:
        return False 
    phrases = (
        "timed out",
        "timeouterror",
        "timeout exceeded",
        "校验失败",
        "navigation failed",
        "net::err_",
        "not found",
        "target closed",
    )
    return any(p in low for p in phrases)

async def iter_ui_steps(*, name: str, url: str) -> AsyncIterator[dict[str, Any]]:
    """对 url 跑一轮可见 UI 测试，逐步 yield 事件字典。

    事件：
    - type=step：一步结束
    - type=done：整轮结束（带 verdict / summary / steps）
    """
    steps: list[dict[str, Any]] = []
    index = 0
    verdict = "pass"
    summary = ""

    def _emit(action: str, detail: str, ok: bool, error: str = "") -> dict[str, Any]:
        nonlocal index, verdict
        index += 1
        if not ok:
            verdict = "fail"
        item = {
            "type": "step",
            "i": index,
            "action": action,
            "detail": (detail or "")[:800],
            "ok": ok,
            "error": (error or "")[:400],
        }
        steps.append(item)
        return item

    try:
        # headed=True：本机弹出 Chrome；云上请改回 False / 加 --headless
        async with playwright_mcp_session(locked_url=url, headed=True) as tools:
            nav = _find_tool(tools, "browser_navigate")
            snap = _find_tool(tools, "browser_snapshot")
            wait = _find_tool(tools, "browser_wait_for")
            close = _find_tool(tools, "browser_close")

            if nav is None:
                yield _emit("启动浏览器", "未找到 browser_navigate", False, "MCP 工具缺失")
                verdict = "error"
                summary = "Playwright MCP 未提供导航工具"
            else:
                yield _emit("启动浏览器", f"开始 UI 测试「{name}」", True)

                # 1) 打开页面 —— 用户此时应看到浏览器窗口
                nav_out = await _call(nav, {"url": url})
                nav_ok = not _looks_fail(nav_out)
                yield _emit(
                    "打开页面",
                    url if nav_ok else nav_out,
                    nav_ok,
                    "" if nav_ok else nav_out,
                )

                # 2) 稍等 SPA 渲染（工具没有就跳过）
                if wait is not None:
                    wait_out = await _call(wait, {"time": 2})
                    wait_ok = not _looks_fail(wait_out)
                    yield _emit(
                        "等待页面",
                        "等待约 2 秒" if wait_ok else wait_out,
                        wait_ok,
                        "" if wait_ok else wait_out,
                    )

                # 3) 快照：有可访问结构则视为探活通过
                if snap is not None:
                    snap_out = await _call(snap, {})
                    snap_ok = bool(snap_out.strip()) and not _looks_fail(snap_out)
                    preview = snap_out.replace("\n", " ")[:200]
                    yield _emit(
                        "页面快照",
                        preview if snap_ok else snap_out,
                        snap_ok,
                        "" if snap_ok else snap_out,
                    )

            # 4) 无论成败都关浏览器
            if close is not None:
                close_out = await _call(close, {})
                close_ok = not _looks_fail(close_out)
                yield _emit(
                    "关闭浏览器",
                    "browser_close",
                    close_ok,
                    "" if close_ok else close_out,
                )

        if not summary:
            if verdict == "pass":
                summary = f"UI 测试「{name}」通过：已打开 {url} 并完成快照"
            else:
                summary = f"UI 测试「{name}」未通过：{url}"
    except Exception as exc:  # noqa: BLE001
        _log.exception("UI 测试异常")
        verdict = "error"
        summary = str(exc)[:500]
        yield _emit("异常", summary, False, summary)

    yield {
        "type": "done",
        "verdict": verdict,
        "summary": summary,
        "steps": steps,
        "name": name,
        "url": url,
    }
