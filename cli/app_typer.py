"""P3: 运维 CLI — Typer 子命令 + --json。

运行::
    python -m cli.app_typer config-check
    python -m cli.app_typer ask -m "你好" --mode chat --json
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer
from dotenv import load_dotenv

load_dotenv()

app = typer.Typer(help="LangChain Demo 运维 CLI", no_args_is_help=True)


def _run(coro):
    return asyncio.run(coro)


@app.command("ask")
def ask(
    message: str = typer.Option(..., "--message", "-m", help="用户问题"),
    mode: str = typer.Option("chat", "--mode", help="chat|rag|graph-rag|agent|multi"),
    session_id: str = typer.Option("cli-default", "--session"),
    multi_mode: str = typer.Option("sequential", "--multi-mode"),
    as_json: bool = typer.Option(False, "--json", help="JSON 输出"),
    tenant_id: str = typer.Option("default", "--tenant"),
) -> None:
    """非交互问答。"""
    from application.services.agent_application import AgentApplication

    async def _go():
        agent = AgentApplication()
        await agent.init_session_store()
        if mode == "chat":
            return await agent.ask_chat(message, session_id=session_id)
        if mode == "rag":
            answer, sources = await agent.ask_rag(message, tenant_id=tenant_id)
            return {"answer": answer, "sources": sources}
        if mode == "graph-rag":
            answer, sources = await agent.ask_graph_rag(message, tenant_id=tenant_id)
            return {"answer": answer, "sources": sources}
        if mode == "agent":
            return await agent.ask_agent(message)
        if mode == "multi":
            return await agent.ask_multi_agent(message, mode=multi_mode)
        raise typer.BadParameter(f"不支持 mode={mode}")

    try:
        result = _run(_go())
        payload = {"ok": True, "mode": mode, "result": result}
        code = 0
    except Exception as e:  # noqa: BLE001
        payload = {"ok": False, "error": str(e)}
        code = 1
        if not as_json:
            typer.echo(f"错误: {e}", err=True)
            raise SystemExit(code)

    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, default=str))
    else:
        if isinstance(result, dict) and "answer" in result:
            typer.echo(result["answer"])
        elif isinstance(result, dict) and "final_answer" in result:
            typer.echo(result["final_answer"])
        else:
            typer.echo(result if isinstance(result, str) else json.dumps(result, ensure_ascii=False))
    raise SystemExit(code)


@app.command("config-check")
def config_check() -> None:
    """检查关键配置。退出码 0=通过，2=缺配置。"""
    from config.settings import get_settings

    s = get_settings()
    problems: list[str] = []
    if not (s.deepseek_api_key or "").strip():
        problems.append("缺少 DEEPSEEK_API_KEY")
    if not (s.embedding_api_key or "").strip():
        problems.append("缺少 EMBEDDING_API_KEY（RAG 需要）")
    if problems:
        typer.echo("FAIL: " + "; ".join(problems))
        raise SystemExit(2)
    typer.echo("OK")
    raise SystemExit(0)


@app.command("kb-build")
def kb_build(
    doc_dir: str = typer.Option("data/docs", "--doc-dir"),
    tenant_id: str = typer.Option("default", "--tenant"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """同步构建租户知识库。"""
    from application.services.agent_application import AgentApplication

    try:
        agent = AgentApplication()
        count = agent.build_knowledge_base(doc_dir, tenant_id=tenant_id)
        payload = {"ok": True, "chunk_count": count, "tenant_id": tenant_id}
        code = 0
    except Exception as e:  # noqa: BLE001
        payload = {"ok": False, "error": str(e)}
        code = 1

    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(payload if code else f"ok chunks={payload.get('chunk_count')}")
    raise SystemExit(code)


if __name__ == "__main__":
    app()
