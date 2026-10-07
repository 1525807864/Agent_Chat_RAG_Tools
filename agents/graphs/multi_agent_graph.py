from __future__ import annotations 
import time 
from typing import Any,Literal 
from langgraph.graph import END,START,StateGraph
from agents.graphs.state import MultiAgentState
from agents.orchestrator import OrchestratorResult#复用现在结构

async def _call(agent:Any,prompt:str,context: dict|None = None)->dict[str,Any]:
    raw = await agent.run(prompt,context)
    if isinstance(raw,dict):
        return raw 
    return {"result":str(raw)}

def _text(raw:dict[str,Any])->str:
    return str(raw.get("result") or "")

def build_multi_agent_graph(agents:dict[str,Any], context: dict | None = None):
    """构建多Agent协作图，支持sequential/debate/router三种模式。

    context 透传给图内每个 Agent.run()（如 {"intent_guard": guard}）。
    """
    researcher = agents["researcher"]
    coder = agents["coder"]
    reviewer = agents["reviewer"]
    async def researcher_node(state:MultiAgentState)->dict:
        raw = await _call(researcher, state["task"], context)
        return {
            "current":_text(raw),
            "last_agent":"researcher",
            "agent_outputs":{"researcher":raw},
            "execution_log":["[researcher]完成"],
        }
    async def coder_node(state:MultiAgentState)->dict:
        task = state["task"]
        prev = state.get("current") or ""
        prompt = (
            f"用户原任务: {task}\n\n"
            f"上一 Agent 的结果（可能含 web_search 内容，请采信其中的链接与摘要）:\n"
            f"{prev}\n\n"
            f"请基于以上结果继续处理，不要声称无法联网。"
        )
        raw = await _call(coder,prompt,context)
        return {
            "current":_text(raw),
            "last_agent":"coder",
            "agent_outputs":{"coder":raw},
            "execution_log":["[coder]完成"],
        }
    async def reviewer_node(state:MultiAgentState)->dict:
        task = state["task"]
        prev = state.get("current") or ""
        prompt = (
            f"用户原任务: {task}\n\n"
            f"上一 Agent 的结果（可能含 web_search 内容，请采信其中的链接与摘要）:\n"
            f"{prev}\n\n"
            f"请基于以上结果继续处理，不要声称无法联网。"
        )
        raw = await _call(reviewer,prompt,context)
        final = _text(raw).strip() or prev
        return {
            "current": final,
            "last_agent": "reviewer",
            "agent_outputs": {"reviewer": raw},
            "execution_log": ["[reviewer]完成"],
            "success": True,
        }

    async def route_decide(state:MultiAgentState)->dict:
        names = "\n".join(
            f"- {n}: {a.role}" for n, a in agents.items() if n != "researcher"
        )
        prompt = (
            f"用户任务:{state['task']}\n\n可用Agent列表:\n{names}\n\n"
            f"请只回复最适合处理此任务的Agent名称(只回复一个名称):"
        )
        raw = await _call(researcher,prompt,context)
        selected = _text(raw).strip()
        for name in agents:
            if name.lower() in selected.lower():
                selected = name
                break
        if selected not in agents:
            selected = "coder"
        return {
            "selected":selected,
            "agent_outputs":{"router":raw},
            "execution_log":[f"Router选择了:{selected}"]
        }
    async def route_run(state:MultiAgentState)->dict:
        name = state.get("selected") or "coder"
        agent = agents[name]
        raw = await _call(agent,state["task"],context)
        return {
            "current":_text(raw),
            "last_agent":name,
            "agent_outputs":{name:raw},
            "execution_log":[f"[router]{name}完成"],
            "success":True,
        }
    async def debate_turn(state:MultiAgentState)->dict:
        r = int(state.get("debate_round") or 0)
        idx = r % 3
        name = ["researcher","coder","reviewer"][idx]
        agent = agents[name]
        context_text = "\n".join(state.get("opinions") or []) or "（首轮发言）"
        prompt = (
            f"讨论话题: {state['task']}\n\n"
            f"之前的观点:\n{context_text}\n\n"
            f"请发表你的观点 (可以赞同、反对或补充):"
        )
        raw = await _call(agent,prompt,context)
        opinion = _text(raw)
        round_no = r//3 + 1
        key = f"{name}_round{round_no}"
        return {
            "debate_round":r+1,
            "opinions":[f"[{name}]: {opinion}"],
            "agent_outputs":{key:raw},
            "execution_log":[f"[debate r{round_no}]{name}"]
        }
    def debate_should_continue(state:MultiAgentState)->Literal["debate","summarize"]:
        max_r = int(state.get("max_debate_rounds") or 2)
        #每轮3个agent 2轮=6次turn
        if int(state.get("debate_round") or 0) < max_r * 3:
            return "debate"
        return "summarize"

    async def summarize(state:MultiAgentState)->dict:
        opinions = "\n".join(state.get("opinions") or [])
        prompt = (
            f"原始话题: {state['task']}\n\n所有观点:\n{opinions}\n\n"
            f"请总结以上辩论, 给出最终结论和建议:"
        )
        raw = await _call(researcher,prompt,context)
        return {
            "current": _text(raw),
            "last_agent": "researcher",
            "agent_outputs": {"summary": raw},
            "execution_log": ["[debate] 汇总完成"],
            "success": True,
        }
    def after_start(state: MultiAgentState) -> Literal["researcher", "route", "debate"]:
        mode = state.get("mode") or "sequential"
        if mode == "router":
            return "route"
        if mode == "debate":
            return "debate"
        return "researcher"
    g = StateGraph(MultiAgentState)
    g.add_node("researcher", researcher_node)
    g.add_node("coder", coder_node)
    g.add_node("reviewer", reviewer_node)
    g.add_node("route", route_decide)
    g.add_node("route_run", route_run)
    g.add_node("debate", debate_turn)
    g.add_node("summarize", summarize)
    g.add_conditional_edges(
        START,
        after_start,
        {"researcher": "researcher", "route": "route", "debate": "debate"},
    )
    g.add_edge("researcher", "coder")
    g.add_edge("coder", "reviewer")
    g.add_edge("reviewer", END)
    g.add_edge("route", "route_run")
    g.add_edge("route_run", END)
    g.add_conditional_edges(
        "debate",
        debate_should_continue,
        {"debate": "debate", "summarize": "summarize"},
    )
    g.add_edge("summarize", END)
    return g.compile()

async def run_multi_agent_graph(
    agents: dict[str, Any],
    task: str,
    mode: str = "sequential",
    debate_rounds: int = 2,
    context: dict | None = None,
) -> OrchestratorResult:
    start = time.time()
    graph = build_multi_agent_graph(agents, context=context)
    if mode not in ("sequential", "router", "debate"):
        mode = "router"
    try:
        final = await graph.ainvoke(
            {
                "task": task,
                "mode": mode,
                "current": "",
                "debate_round": 0,
                "max_debate_rounds": debate_rounds,
                "agent_outputs": {},
                "execution_log": [],
                "opinions": [],
                "success": False,
                "error": "",
            }
        )
        current = (final.get("current") or "").strip()
        outputs = final.get("agent_outputs") or {}
        if not current and "researcher" in outputs:
            current = _text(outputs["researcher"])
        ok = bool(final.get("success")) and not (final.get("error") or "")
        return OrchestratorResult(
            success=ok,
            final_answer=current,
            agent_outputs=outputs,
            execution_log=list(final.get("execution_log") or []),
            total_time_ms=(time.time() - start) * 1000,
        )
    except Exception as e:  # noqa: BLE001
        return OrchestratorResult(
            success=False,
            final_answer=str(e),
            agent_outputs={},
            execution_log=[f"graph failed: {e}"],
            total_time_ms=(time.time() - start) * 1000,
        )