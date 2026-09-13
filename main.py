"""CLI 入口。

架构说明
========
- 业务门面：``application.services.agent_application.AgentApplication``
- CLI 循环：``interfaces.cli.app.run_cli``
- HTTP：``uvicorn api.server:app``（``api.deps`` 导入同一 ``AgentApplication``）
"""

from __future__ import annotations

import asyncio

from dotenv import load_dotenv

load_dotenv()

from interfaces.cli.app import run_cli  # noqa: E402

__all__ = ["main", "run_cli"]


async def main() -> None:
    """异步 CLI 入口。"""
    await run_cli()


if __name__ == "__main__":
    asyncio.run(main())
