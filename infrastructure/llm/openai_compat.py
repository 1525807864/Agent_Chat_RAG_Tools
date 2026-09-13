"""OpenAI 兼容 Chat 客户端（支持 stream + bind_tools）。"""

from __future__ import annotations

from langchain_openai import ChatOpenAI


def create_chat_openai(
    *,
    api_key: str,
    api_base: str,
    model: str,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    streaming: bool = False,
) -> ChatOpenAI:
    """创建 ChatOpenAI，可指向 DeepSeek 等兼容 Base。"""
    return ChatOpenAI(
        api_key=api_key,
        base_url=api_base,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=streaming,
    )
