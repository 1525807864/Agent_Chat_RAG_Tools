"""客户集群内的轻量 Ops Agent。

职责：
- 暴露与 Holmes 兼容的 POST /api/chat、GET /healthz
- 默认把请求转发到客户集群内的 Holmes
- 用 AGENT_TOKEN 校验 Nexora 带来的 Bearer / X-API-Key

Nexora 侧登记示例：
  targetType=remote_agent
  endpointBase=https://ops-agent.customer.example
  authToken=<与 AGENT_TOKEN 相同>
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Nexora Customer Ops Agent", docs_url=None, redoc_url=None)

AGENT_TOKEN = (os.getenv("AGENT_TOKEN") or "").strip()
HOLMES_URL = (os.getenv("HOLMES_URL") or "http://holmes:5050").rstrip("/")


def _check_auth(
    authorization: str | None,
    x_api_key: str | None,
) -> None:
    if not AGENT_TOKEN:
        return
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    got = (x_api_key or bearer or "").strip()
    if got != AGENT_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


class ChatBody(BaseModel):
    ask: str = ""
    stream: bool = False
    conversation_history: list[dict[str, Any]] | None = None
    model: str | None = None
    user_id: str | None = None


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat")
def chat(
    body: ChatBody,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    _check_auth(authorization, x_api_key)
    payload: dict[str, Any] = {"ask": body.ask, "stream": False}
    if body.conversation_history:
        payload["conversation_history"] = body.conversation_history
    if body.model:
        payload["model"] = body.model
    if body.user_id:
        payload["user_id"] = body.user_id

    try:
        with httpx.Client(timeout=300.0) as client:
            r = client.post(f"{HOLMES_URL}/api/chat", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"upstream holmes: {exc}") from exc

    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=r.text[:800])
    data = r.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="bad upstream json")
    return data
