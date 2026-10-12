"""
测试平台UI智能体
职责:
===
- 有头
- 大模型来决定下一步做什么
- pass/fail由playwright来判断
- 每一步写入steps，供SSE与Excel/Word/PDF导出
"""
from __future__ import annotations 
import logging 
from typing import Any,AsyncIterator 
from langchain_core.messages import AIMessage,HumanMessage,SystemMessage,ToolMessage 
from application.qa.ui_runner import _flatten_tool_text, _looks_fail
from config.settings import get_settings 
from e2e.mcp_playwright import e2e_system_hint, playwright_mcp_session
from infrastructure.llm.openai_compat import create_chat_openai

_log = logging.getLogger(__name__) 
#单次任务最多工具回合，防止模型无限调用工具，空转自己浪费token
_MAX_ROUNDS = 16 

def _system_prompt(*, url: str, goal: str)->str:
    """约束模型：先打开锁定站点，用 snapshot 找元素，结束前必须关浏览器。"""
    base = e2e_system_hint(
        locked_url=url,
        user=get_settings().e2e_user,
        password=get_settings().e2e_password,
    )
    return (
        base
        + "\n你是商业测试执行智能体，不是脚本生成器。禁止输出 Playwright 源码。\n"
        "必须通过工具完成用户目标。每做一次点击或输入前，先 browser_snapshot。\n"
        "断言以页面 URL、标题、snapshot 中的可见文案为准，不要编造「测试通过」。\n"
        "目标完成后用一句话说明观察到的结果，然后调用 browser_close。\n"
        f"本轮锁定站点: {url}\n"
        f"测试目标: {goal}\n" 
    )

def _llm():
    """复用项目里的OpenAI兼容客户端"""
    s = get_settings() 
    if not (s.deepseek_api_key or "").strip():
        raise RuntimeError("请配置 DeepSeek API Key")
    return create_chat_openai(
        api_key=s.deepseek_api_key,
        api_base=s.deepseek_api_base,
        model=s.model_name,
        temperature=0.1,
        max_tokens=2048,
        streaming=False,
    )

async def _invoke_tool(tool:Any,args:dict)->str:
    try:
        if hasattr(tool,"ainvoke"):
            raw = await tool.ainvoke(args or {})
        else:
            raw = tool.invoke(args or {})
        return _flatten_tool_text(raw)
    except Exception as exc:
        return f"工具调用失败: {exc}"
    
def _args_brief(args:Any)->str:
    """给测试人员看的参数摘要，避免把整份snapshot塞进报告"""
    if not isinstance(args,dict):
        return str(args)[:1000]
    keep = {k:args[k] for k in ("url","text","element","ref","time","key") if k in args}
    text = str(keep or args)
    return text[:1000]

async def iter_agent_ui(*,name:str,url:str,goal:str)->AsyncIterator[dict[str,Any]]:
    """跑一轮智能UI测试。yield step。最后yield done"""
    task = (goal or name or "打开页面并确认可访问").strip()
    steps: list[dict[str,Any]] = [] # 每一步都记录
    index = 0 # 步骤序号
    any_fail = False # 是否失败过
    saw_navigate = False # 是否已经导航过
    def emit(action: str,detail: str,ok: bool,error: str = "")->dict[str,Any]:
        nonlocal index,any_fail
        index += 1 
        if not ok:
            any_fail = True 
        item = {
            "type":"step",
            "i": index,
            "action": action,
            "detail": ( detail or "")[:800],
            "ok":ok,
            "error": (error or "")[:800],
        }
        steps.append(item)
        return item 
    try:
        # headed=True：浏览器开在跑本进程的机器上（Electron 本机 API 即用户电脑）
        async with playwright_mcp_session(locked_url=url, headed=True) as tools:
            if not tools:
                yield emit("启动", "Playwright MCP 未返回工具", False, "无工具")
                yield _done("error", "浏览器工具不可用", steps, name, url, task)
                return 
            # 大模型来决定下一步来做什么
            llm = _llm().bind_tools(tools)
            by_name = {t.name:t for t in tools}
            messages: list = [
                SystemMessage(content=_system_prompt(url=url, goal=task)),
                HumanMessage(content=f"测试名称：{name}\n请开始执行。第一步必须打开 {url}"),
            ]
            yield emit("启动浏览器",f"智能执行{name}",True)
            final_text = ""
            for _round in range(_MAX_ROUNDS):
                ai: AIMessage = await llm.ainvoke(messages)
                messages.append(ai)
                calls = getattr(ai,"tool_calls",None) or []
                if not calls:
                    final_text = ai.content if isinstance(ai.content,str) else str(ai.content or "")
                    break 
                for call in calls:
                    if isinstance(call, dict):
                        name_tool = str(call.get("name") or "")
                        args = call.get("args") or {}
                        call_id = str(call.get("id") or name_tool)
                    else:
                        name_tool = str(getattr(call, "name", "") or "")
                        args = getattr(call, "args", None) or {}
                        call_id = str(getattr(call, "id", None) or name_tool)
                    tool = by_name.get(name_tool)
                    if tool is None:
                        out = f"未知工具: {name_tool}"
                    else:
                        out = await _invoke_tool(tool, args if isinstance(args, dict) else {})
                    ok = not _looks_fail(out)
                    if "navigate" in name_tool.lower():
                        saw_navigate = True
                    # 模型的思考不作为判定；判定只看 ok
                    yield emit(
                        name_tool or "tool",
                        _args_brief(args),
                        ok,
                        "" if ok else out[:400],
                    )
                    messages.append(ToolMessage(content=out[:6000], tool_call_id=call_id))
            else:
                final_text = "达到最大执行轮次，已停止"
            # 关闭浏览器
            close = by_name.get("browser_close")
            if close is not None:
                out = await _invoke_tool(close, {})
                ok = not _looks_fail(out) 
                yield emit("关闭浏览器", "浏览器关闭", ok, "" if ok else out[:400])
        if not saw_navigate:
            verdict, summary = "error", "未执行打开页面，结果无效"
        elif any_fail:
            verdict, summary = "fail", f"「{name}」存在失败步骤。模型观察：{final_text[:200]}"
        else:
            verdict, summary = "pass", f"「{name}」工具链未报错。模型观察：{final_text[:200]}"
        yield _done(verdict, summary, steps, name, url, task)
    except Exception as exc:  # noqa: BLE001
        _log.exception("UI 智能体失败")
        yield emit("异常", str(exc)[:500], False, str(exc)[:400])
        yield _done("error", str(exc)[:500], steps, name, url, task)

def _done(verdict: str, summary: str, steps: list, name: str, url: str, goal: str) -> dict:
    return {
        "type": "done",
        "verdict": verdict,
        "summary": summary,
        "steps": steps,
        "name": name,
        "url": url,
        "goal": goal,
    }