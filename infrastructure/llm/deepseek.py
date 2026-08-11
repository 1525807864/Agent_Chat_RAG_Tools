"""DeepSeek ChatModel — 生产路径使用的唯一 LLM 适配器。

历史类 ``DeepSeekLLM`` / ``DeepSeekChatLLM`` 已废弃（见 ``examples/`` 说明），
业务统一通过本模块的 ``DeepSeekChatModel``（BaseChatModel）接入 LCEL / Agent。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from openai import OpenAI
from pydantic import ConfigDict

from config.settings import (
    DEEPSEEK_API_BASE,
    DEEPSEEK_API_KEY,
    MODEL_MAX_TOKENS,
    MODEL_NAME,
    MODEL_TEMPERATURE,
)

logger = logging.getLogger(__name__)


def _convert_message_to_dict(message: BaseMessage) -> Dict[str, Any]:
    """LangChain Message → OpenAI/DeepSeek Chat Completions dict。"""
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": message.content}
    if isinstance(message, AIMessage):
        return {"role": "assistant", "content": message.content}
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": message.content}
    return {"role": "user", "content": str(message.content)}


class DeepSeekChatModel(BaseChatModel):
    """DeepSeek ChatModel — 实现 BaseChatModel，供 LCEL / Agent 使用。"""

    model_name: str = MODEL_NAME
    temperature: float = MODEL_TEMPERATURE
    max_tokens: int = MODEL_MAX_TOKENS
    api_key: str = ""
    api_base: str = ""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    @property
    def _llm_type(self) -> str:
        return "deepseek-chat"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        api_key = self.api_key or DEEPSEEK_API_KEY
        api_base = self.api_base or DEEPSEEK_API_BASE

        if not api_key:
            # 文案写清楚：可能是请求没带 Key，也可能是服务端 .env 没配
            raise ValueError(
                "未配置 API Key：请在前端设置中填写，或在服务端 .env 设置 DEEPSEEK_API_KEY"
            )

        client = OpenAI(api_key=api_key, base_url=api_base)
        formatted_messages = [_convert_message_to_dict(msg) for msg in messages]
        # 只打模型名与消息条数，绝不打印 api_key
        logger.info(
            "DeepSeek 调用: model=%s messages=%s",
            self.model_name,
            len(formatted_messages),
        )

        response = client.chat.completions.create(
            model=self.model_name,
            messages=formatted_messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stop=stop,
        )

        content = response.choices[0].message.content
        message = AIMessage(content=content)
        return ChatResult(generations=[ChatGeneration(message=message)])
