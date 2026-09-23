"""从Settings/环境变量解析MCP服务器列表。"""
from __future__ import annotations  

import json 
import logging 

from application.mcp.spec import McpServerSpec 

_log = logging.getLogger(__name__) 

def parse_mcp_servers_json(raw:str)->list[McpServerSpec]:
    """解析 JSON 字符串为 MCP 服务器列表
    期望格式（JSON 数组）::
            [
              {
                "name": "playwright",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@playwright/mcp@latest", "--headless"]
              }
            ]
    空字符串或 [] → 返回空列表（不算错误，表示本轮不用外部 MCP）。
    """
    text = (raw or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        _log.error("解析 MCP 服务器列表失败: %s", e)
        return []
    if not isinstance(data, list):
        _log.error("MCP 服务器列表格式错误: 应为数组, 实际为 %s", type(data))
        return []
    out: list[McpServerSpec] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            _log.warning("跳过第 %s 项：不是对象", i)
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            _log.warning("跳过第 %s 项：name 为空", i)
            continue 
        args_raw = item.get("args") or []
        if isinstance(args_raw,str):
            # 也允许逗号分隔，和 E2E_MCP_ARGS 习惯一致
            args = tuple(a for a in args_raw.split(",") if a.strip())
        else:
            args = tuple(str(a) for a in args_raw)
        env_raw = item.get("env") or {}
        env = {str(k):str(v) for k,v in env_raw.items()} if isinstance(env_raw,dict) else {}
        out.append(
            McpServerSpec(
                name=name,
                transport=str(item.get("transport") or "stdio"),
                command=str(item.get("command") or "npx"),
                args=args,
                env=env,
            )
        )
    return out 