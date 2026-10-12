"""通过官方 Playwright MCP 向 Agent 注入浏览器工具（不自研 click/fill）。

要点
====
1. 使用 ``langchain-mcp-adapters`` 拉起 ``npx @playwright/mcp``
2. **必须**用有状态 session：``async with client.session(...)``，
   否则每次工具调用都会新开浏览器，snapshot 后无法再点
3. 只在 navigate 类工具外包一层 ``url_guard``（SSRF / 锁定 origin）
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from urllib.parse import urlparse

from langchain_core.tools import BaseTool, StructuredTool

from config.settings import get_settings
from e2e.url_guard import E2EUrlError, start_path_from_url, validate_base_url

_log = logging.getLogger(__name__)

# 默认只暴露常用子集，避免 20+ 工具撑爆 ReAct prompt（其余可按需放开）
_DEFAULT_TOOL_ALLOW = {
    "browser_navigate",
    "browser_snapshot",
    "browser_click",
    "browser_type",
    "browser_fill_form",
    "browser_wait_for",
    "browser_take_screenshot",
    "browser_press_key",
    "browser_select_option",
    "browser_handle_dialog",
    "browser_close",
    "browser_console_messages",
}


def filter_playwright_tools(tools: list[BaseTool]) -> list[BaseTool]:
    """裁剪为常用浏览器工具；若一个都匹配不到则原样返回（兼容改名）。"""
    kept = [t for t in tools if t.name in _DEFAULT_TOOL_ALLOW]
    return kept if kept else list(tools)


# Playwright MCP 里会打开页面的工具名（子串匹配，兼容改名）
_NAVIGATE_HINTS = ("navigate", "goto", "open")


def _playwright_connection(*, headed: bool = False) -> dict[str, Any]:
    """从 Settings 拼 MCP stdio。headed=True 时去掉 --headless，让 Chrome 可见。"""
    s = get_settings()
    cmd = (getattr(s, "e2e_mcp_command", None) or "npx").strip()
    # 默认: npx -y @playwright/mcp@latest --headless
    raw_args = (getattr(s, "e2e_mcp_args", None) or "").strip()
    if raw_args:
        args = [a.strip() for a in raw_args.split(",") if a.strip()]
    else:
        args = ["-y", "@playwright/mcp@latest", "--headless"]
    # UI 测试要看见窗口：只去掉 headless，保留 -y 与包名
    if headed:
        args = [a for a in args if a.lower() not in ("--headless", "headless")]
        if not any("playwright/mcp" in a for a in args):
            args = ["-y", "@playwright/mcp@latest"]
    return {
        "transport": "stdio",
        "command": cmd,
        "args": args,
    }


def _is_navigate_tool(name: str) -> bool:
    n = (name or "").lower()
    return any(h in n for h in _NAVIGATE_HINTS)


def _extract_url_from_args(args: dict[str, Any]) -> str | None:
    """从 MCP 工具参数里捞出 URL 字段。"""
    if not isinstance(args, dict):
        return None
    for key in ("url", "uri", "href", "to", "target"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _guard_url(
    raw: str,
    *,
    locked_url: str | None,
    allow_local: bool,
) -> str:
    """校验并必要时改写成锁定站点下的完整 URL。"""
    text = (raw or "").strip()
    if not text:
        raise E2EUrlError("navigate url 不能为空")

    # 相对路径：必须先有锁定站点
    parsed = urlparse(text)
    if not parsed.scheme:
        if not locked_url:
            raise E2EUrlError("相对路径导航需要先配置 e2e_base_url")
        origin = validate_base_url(locked_url, allow_local=allow_local)
        path = text if text.startswith("/") else "/" + text
        return origin + path

    # 绝对 URL：校验协议/内网，并强制同源（若本轮锁定了站点）
    origin = validate_base_url(text, allow_local=allow_local)
    if locked_url:
        want = validate_base_url(locked_url, allow_local=allow_local)
        if origin != want:
            raise E2EUrlError(f"禁止跳到非本轮站点: {origin}（只允许 {want}）")
    return text


def _wrap_navigate_tool(
    tool: BaseTool,
    *,
    locked_url: str | None,
    allow_local: bool,
) -> BaseTool:
    """包装 navigate：调用前过 url_guard；失败返回字符串给模型。"""

    async def _arun(**kwargs: Any) -> str:
        try:
            data = dict(kwargs or {})
            url = _extract_url_from_args(data)
            if url is not None:
                data["url"] = _guard_url(
                    url, locked_url=locked_url, allow_local=allow_local
                )
            # 部分 MCP 工具把参数嵌在 input 字符串里
            if url is None and isinstance(data.get("input"), str):
                try:
                    inner = json.loads(data["input"])
                    if isinstance(inner, dict) and inner.get("url"):
                        inner["url"] = _guard_url(
                            str(inner["url"]),
                            locked_url=locked_url,
                            allow_local=allow_local,
                        )
                        data["input"] = json.dumps(inner, ensure_ascii=False)
                except json.JSONDecodeError:
                    pass
            if hasattr(tool, "ainvoke"):
                return str(await tool.ainvoke(data))
            return str(tool.invoke(data))
        except E2EUrlError as exc:
            return f"URL 校验失败: {exc}"
        except Exception as exc:  # noqa: BLE001
            return f"浏览器导航失败: {exc}"

    def _run(**kwargs: Any) -> str:
        # ReAct 同步兜底：尽量走 asyncio
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 已在协程里时不应走 sync；返回提示
                return "请使用异步调用浏览器工具"
            return loop.run_until_complete(_arun(**kwargs))
        except RuntimeError:
            return asyncio.run(_arun(**kwargs))

    return StructuredTool.from_function(
        name=tool.name,
        description=tool.description or "Playwright MCP navigate",
        coroutine=_arun,
        func=_run,
        args_schema=getattr(tool, "args_schema", None),
    )


def apply_navigate_guard(
    tools: list[BaseTool],
    *,
    locked_url: str | None,
    allow_local: bool,
) -> list[BaseTool]:
    """对 navigate 类工具套同源闸门；其余原样返回。"""
    out: list[BaseTool] = []
    for t in tools:
        if _is_navigate_tool(t.name):
            out.append(
                _wrap_navigate_tool(
                    t, locked_url=locked_url, allow_local=allow_local
                )
            )
        else:
            out.append(t)
    return out


def e2e_system_hint(*, locked_url: str | None, user: str, password: str) -> str:
    """拼进 ReAct system_prompt 的 E2E 说明（禁止写 spec）。"""
    lines = [
        "\n你是 Web E2E 测试助手。禁止编写 .spec.ts / Playwright 源码。",
        "使用 Playwright MCP 工具：browser_navigate → browser_snapshot → "
        "browser_type / browser_click →（可用 browser_wait_for）→ 用中文总结。",
        "SPA 若 snapshot 没有表单，先 wait 再 snapshot，不要瞎点。",
        "登录按钮点「登录」，不要点「SSO登录」。",
        "不要用 web_search；不要编造通过/失败。",
    ]
    if locked_url:
        origin = ""
        path = "/"
        try:
            origin = validate_base_url(
                locked_url, allow_local=get_settings().e2e_allow_local
            )
            path = start_path_from_url(locked_url)
        except E2EUrlError:
            origin = locked_url
        target = origin + path if origin else locked_url
        lines.append(f"本轮必须先 browser_navigate 到: {target}")
    if user:
        lines.append(f"测试用户名: {user}")
    if password:
        lines.append(f"测试密码: {password}")
    else:
        lines.append("未配置 E2E_PASSWORD 时不要猜测密码。")
    return "\n".join(lines)


@asynccontextmanager
async def playwright_mcp_session(
    *,
    locked_url: str | None = None,
    headed: bool = False,
) -> AsyncIterator[list[BaseTool]]:
    """有状态 Playwright MCP：yield 期间共用同一浏览器。headed 时弹出窗口。"""
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        from langchain_mcp_adapters.tools import load_mcp_tools
    except ImportError as exc:
        raise RuntimeError(
            "未安装 langchain-mcp-adapters，请 pip install langchain-mcp-adapters"
        ) from exc

    settings = get_settings()
    allow_local = bool(settings.e2e_allow_local)
    conn = _playwright_connection(headed=headed)
    client = MultiServerMCPClient({"playwright": conn})
    _log.info(
        "启动 Playwright MCP headed=%s: %s %s",
        headed,
        conn["command"],
        conn["args"],
    )

    async with client.session("playwright") as session:
        tools = await load_mcp_tools(session)
        tools = filter_playwright_tools(tools)
        tools = apply_navigate_guard(
            tools, locked_url=locked_url, allow_local=allow_local
        )
        _log.info("Playwright MCP 工具数=%s", len(tools))
        yield tools