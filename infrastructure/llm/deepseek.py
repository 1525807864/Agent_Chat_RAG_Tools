"""DeepSeek ChatModel — 生产路径使用的唯一 LLM 适配器。

业务统一通过本模块的 ``DeepSeekChatModel``（BaseChatModel）接入 LCEL / Agent。
支持同步 ``_generate`` 与流式 ``_stream`` / ``_astream``；回包带 token usage。
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

from langchain_core.callbacks.manager import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from openai import AsyncOpenAI, OpenAI
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
    content = message.content
    if not isinstance(content, str):
        content = "" if content is None else str(content)
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": content}
    if isinstance(message, AIMessage):
        return {"role": "assistant", "content": content}
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": content}
    return {"role": "user", "content": content}


def _usage_fields(usage: Any) -> tuple[int, int]:
    """从厂商 usage 对象取出 prompt / completion tokens。"""
    if usage is None:
        return 0, 0
    return (
        int(getattr(usage, "prompt_tokens", 0) or 0),
        int(getattr(usage, "completion_tokens", 0) or 0),
    )


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

    def _client_kwargs(self) -> tuple[str, str]:
        api_key = self.api_key or DEEPSEEK_API_KEY
        api_base = self.api_base or DEEPSEEK_API_BASE
        if not api_key:
            raise ValueError(
                "未配置 API Key：请在前端设置中填写，或在服务端 .env 设置 DEEPSEEK_API_KEY"
            )
        return api_key, api_base

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        api_key, api_base = self._client_kwargs()
        client = OpenAI(api_key=api_key, base_url=api_base, timeout=120.0)
        formatted_messages = [_convert_message_to_dict(msg) for msg in messages]
        logger.info(
            "DeepSeek 调用开始: model=%s base=%s messages=%s max_tokens=%s",
            self.model_name,
            api_base,
            len(formatted_messages),
            self.max_tokens,
        )

        try:
            response = client.chat.completions.create(
                model=self.model_name,
                messages=formatted_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stop=stop,
            )
        except Exception:
            logger.exception(
                "DeepSeek API 调用失败 model=%s messages=%s",
                self.model_name,
                len(formatted_messages),
            )
            raise

        prompt_tokens, completion_tokens = _usage_fields(
            getattr(response, "usage", None)
        )

        raw = response.choices[0].message.content
        content = raw if isinstance(raw, str) else ("" if raw is None else str(raw))
        if not content.strip():
            logger.warning(
                "DeepSeek 返回空 content: model=%s finish_reason=%s",
                self.model_name,
                getattr(response.choices[0], "finish_reason", None),
            )
            raise ValueError(
                "模型返回空内容，请重试或检查模型名 / API Key / 额度"
            )
        logger.info(
            "DeepSeek 调用成功: model=%s prompt_tokens=%s completion_tokens=%s content_len=%s",
            self.model_name,
            prompt_tokens,
            completion_tokens,
            len(content),
        )
        message = AIMessage(
            content=content,
            usage_metadata={
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            response_metadata={
                "token_usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
                "model_name": self.model_name,
            },
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        api_key, api_base = self._client_kwargs()
        client = OpenAI(api_key=api_key, base_url=api_base, timeout=120.0)
        formatted = [_convert_message_to_dict(m) for m in messages]
        create_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": formatted,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stop": stop,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        try:
            stream = client.chat.completions.create(**create_kwargs)
        except Exception:
            create_kwargs.pop("stream_options", None)
            stream = client.chat.completions.create(**create_kwargs)
        for event in stream:
            usage = getattr(event, "usage", None)
            if usage is not None:
                prompt_tokens, completion_tokens = _usage_fields(usage)
                yield ChatGenerationChunk(
                    message=AIMessageChunk(
                        content="",
                        usage_metadata={
                            "input_tokens": prompt_tokens,
                            "output_tokens": completion_tokens,
                            "total_tokens": prompt_tokens + completion_tokens,
                        },
                    )
                )
                continue
            if not event.choices:
                continue
            delta = event.choices[0].delta
            text = getattr(delta, "content", None) or ""
            if not text:
                continue # 如果delta没有content，则跳过
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=text))
            if run_manager:
                run_manager.on_llm_new_token(text)
            yield chunk

    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        api_key, api_base = self._client_kwargs()
        client = AsyncOpenAI(api_key=api_key, base_url=api_base, timeout=120.0)
        formatted = [_convert_message_to_dict(m) for m in messages]
        create_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": formatted,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stop": stop,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        try:
            stream = await client.chat.completions.create(**create_kwargs)
        except Exception:
            create_kwargs.pop("stream_options", None)
            stream = await client.chat.completions.create(**create_kwargs)
        async for event in stream:
            usage = getattr(event, "usage", None)
            if usage is not None:
                prompt_tokens, completion_tokens = _usage_fields(usage)
                yield ChatGenerationChunk(
                    message=AIMessageChunk(
                        content="",
                        usage_metadata={
                            "input_tokens": prompt_tokens,
                            "output_tokens": completion_tokens,
                            "total_tokens": prompt_tokens + completion_tokens,
                        },
                    )
                )
                continue
            if not event.choices:
                continue
            delta = event.choices[0].delta
            text = getattr(delta, "content", None) or ""
            if not text:
                continue
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=text))
            if run_manager:
                await run_manager.on_llm_new_token(text)
            yield chunk
