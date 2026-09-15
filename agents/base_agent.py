"""Agent 抽象基类。

核心三要素: LLM（大脑）+ Tools（手脚）+ SystemPrompt（角色）。
子类（如 ReActAgent）自行实现 ``think`` 与 ``run``。
"""

from abc import ABC, abstractmethod
from typing import Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool


class BaseAgent(ABC):
    """所有具体 Agent 的父类。"""

    def __init__(
        self,
        name: str,
        role: str,
        llm: BaseChatModel,
        tools: Optional[list[BaseTool]] = None,
        system_prompt: Optional[str] = None,
    ):
        self.name = name
        self.role = role
        self.llm = llm
        self.tools = tools or []
        self.system_prompt = system_prompt or f"你是 {name}, 负责 {role}"

    @abstractmethod
    async def think(self, task: str, context: Optional[dict] = None) -> str:
        """根据任务与上下文生成下一步想法或最终答案草稿。"""
        ...

    @abstractmethod
    async def run(self, task: str, context: Optional[dict] = None) -> dict:
        """执行完整任务循环，返回至少含 ``result`` 的 dict。"""
        ...
