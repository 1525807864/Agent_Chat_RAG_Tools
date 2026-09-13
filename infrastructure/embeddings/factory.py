"""P0: 创建可用的 Embeddings，禁止误用 DeepSeek Chat Base。"""

from __future__ import annotations

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from config.settings import get_settings


def create_embeddings() -> Embeddings:
    """根据 Settings 创建 Embedding 客户端。

    返回示例::
        OpenAIEmbeddings(model="text-embedding-3-small", ...)

    调试:
    - embedding_api_key 为空 → 立刻抛错（fail-closed）
    - base 若仍是 api.deepseek.com → 警告（DeepSeek 通常无该 embedding 模型）
    """
    s = get_settings()
    key = (s.embedding_api_key or "").strip()
    base = (s.embedding_api_base or "").strip()
    model = (s.embedding_model or "").strip()

    if not key:
        raise RuntimeError(
            "未配置 EMBEDDING_API_KEY：RAG 无法工作。"
            "请在 .env 设置独立的 Embedding Key（不要用 DeepSeek Chat Key 凑合，除非厂商明确支持）。"
        )
    if "deepseek.com" in base.lower():
        # 不直接 raise，方便你实验；商用建议改成 raise
        import logging
        logging.getLogger(__name__).warning(
            "EMBEDDING_API_BASE 指向 DeepSeek，请确认该厂商提供 embedding 模型 %s",
            model,
        )

    return OpenAIEmbeddings(
        model=model,
        openai_api_key=key,
        openai_api_base=base,
    )