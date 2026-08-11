"""CLI 入口与向后兼容导出。

架构说明
========
- 业务门面：``application.services.agent_application.AgentApplication``
- CLI 循环：``interfaces.cli.app.run_cli``
- HTTP：``uvicorn api.server:app``（``api.deps`` 导入同一 ``AgentApplication``）

为保持旧代码 ``from main import AgentApplication`` 可用，本模块再导出一次。
"""

from __future__ import annotations

import asyncio

from dotenv import load_dotenv

load_dotenv()

# 向后兼容：api.deps / 旧脚本可能 from main import AgentApplication
from application.services.agent_application import AgentApplication  # noqa: E402
from interfaces.cli.app import run_cli  # noqa: E402

__all__ = ["AgentApplication", "main", "run_cli"]


async def main() -> None:
    """异步 CLI 入口。"""
    await run_cli()


if __name__ == "__main__":
    asyncio.run(main())
