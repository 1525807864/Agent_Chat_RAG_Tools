"""MCP 服务器描述。不连接网络，只存配置。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class McpServerSpec:
    """
    一条 MCP 服务器配置，对应 MultiServerMCPClient 的一个 key。
    name: 客户端里的逻辑名，例如 "playwright"、"perception"
    transport: 目前只做 stdio（和现有 Playwright 一致）
    command / args: 例如 npx + ["-y", "@playwright/mcp@latest", "--headless"]
    env: 传给子进程的额外环境变量（可空）
    """

    name: str
    transport: str = "stdio"
    command: str = "npx"
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)

    def to_client_dict(self) -> dict[str, Any]:
        """转成 langchain_mcp_adapters 认识的连接字典（不含 name，name 是外层 key）。"""
        if self.transport != "stdio":
            raise ValueError(f"暂不支持 transport={self.transport}，请用 stdio")
        cfg: dict[str, Any] = {
            "transport": "stdio",
            "command": self.command,
            "args": list(self.args),
        }
        if self.env:
            cfg["env"] = dict(self.env)
        return cfg
