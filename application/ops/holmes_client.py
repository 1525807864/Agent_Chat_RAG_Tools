"""HolmesGPT HTTP 客户端。

设计原则：
- Nexora 不 import D:\\holmesgpt 源码，只 HTTP 调用 POST /api/chat
- 浏览器永不直连 Holmes；一律经 /api/ops/* + JWT
- 超时、鉴权、模型名从 Settings 读取，方便换 Docker/Helm 地址
"""

from __future__ import annotations

from typing import Any

import httpx

from config.settings import get_settings


class HolmesError(Exception):
    """调用 Holmes 失败时抛出，由路由转成 502/503/504。"""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HolmesClient:
    """薄封装：ask() → Holmes /api/chat。"""

    def __init__(
        self,
        *,
        base: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        s = get_settings()
        # 允许执行器传入[客户Agent/专用Holmes]地址 

        self.base = (base if base is not None else s.holmes_api_base or "").rstrip("/") #去掉尾斜杠，避免 //api/chat
        if api_key is None:
            self.api_key = (s.holmes_api_key or "").strip()
        else:
            self.api_key = (api_key or "").strip()
        
        self.default_model = (
            (default_model if default_model is not None else s.holmes_default_model) or ""
        ).strip() or None
        self.timeout = float(timeout if timeout is not None else s.holmes_timeout_sec)

    def _headers(self) -> dict[str, str]:
        """Holmes 可选鉴权：HOLMES_API_KEY 非空才带。"""
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            # 文档支持 X-API-Key 与 Bearer，两者等价
            headers["X-API-Key"] = self.api_key
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def health(self) -> bool:
        """探活 Holmes /healthz；失败返回 False，不抛异常。"""
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(f"{self.base}/healthz", headers=self._headers())
            return r.status_code == 200
        except Exception:
            return False

    def ask(
        self,
        *,
        message: str,
        conversation_history: list[dict[str, Any]] | None = None,
        model: str | None = None,
        user_id: str | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """同步调查。

        参数：
          message: 用户问题（对应 Holmes 字段 ask）
          conversation_history: 多轮上下文；首条一般是 system（由 Holmes 上一轮返回）
          model: 覆盖默认模型；有 modelList 时传「键名」如 deepseek
          user_id: 可选，传给 Holmes 做技能/隔离
          stream: Phase1 固定 False；前端要流式时再开 SSE 透传

        返回：
          Holmes JSON，常见字段 analysis / conversation_history / tool_calls
        """
        text = (message or "").strip()
        if not text and not conversation_history:
            raise HolmesError("ask 不能为空")

        body: dict[str, Any] = {
            "ask": text,
            "stream": bool(stream),
        }
        if conversation_history:
            body["conversation_history"] = conversation_history
        chosen = (model or self.default_model or "").strip()
        if chosen:
            body["model"] = chosen
        if user_id:
            body["user_id"] = user_id

        url = f"{self.base}/api/chat"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=body, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise HolmesError(
                f"Holmes 超时（>{self.timeout}s），调查可能仍在进行",
                status_code=504,
            ) from exc
        except httpx.RequestError as exc:
            raise HolmesError(
                f"无法连接 Holmes（{self.base}）：{exc}",
                status_code=502,
            ) from exc

        if resp.status_code >= 400:
            # 尽量把 Holmes 返回的 detail 透出，方便排 DeepSeek/鉴权问题
            detail = resp.text[:800]
            try:
                detail = str(resp.json().get("detail") or detail)
            except Exception:
                pass
            raise HolmesError(
                f"Holmes HTTP {resp.status_code}: {detail}",
                status_code=502,
            )

        try:
            data = resp.json()
        except Exception as exc:
            raise HolmesError("Holmes 返回非 JSON", status_code=502) from exc
        if not isinstance(data, dict):
            raise HolmesError("Holmes 返回格式异常", status_code=502)
        return data