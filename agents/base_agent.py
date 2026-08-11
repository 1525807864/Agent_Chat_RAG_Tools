"""Agent 抽象基类

知识点:
1. 为什么需要基类? → 统一接口、可扩展、可测试
2. Agent 核心三要素: LLM (大脑) + Tools (手脚) + SystemPrompt (角色)
3. AgentMessage: 多 Agent 通信协议, 结构化消息 (sender/receiver/type/content)
"""

from abc import ABC, abstractmethod
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool


class AgentMessage:
    """Agent 间通信消息 — 多 Agent 协作时的轻量结构化信封。

    msg_type 约定（约定而非强制枚举）:
    ``task`` | ``result`` | ``question`` | ``info``，便于编排器/日志区分用途。
    """

    def __init__(
        self,
        sender: str,
        receiver: str,
        msg_type: str,  # "task" | "result" | "question" | "info"
        content: str,
        metadata: Optional[dict] = None,
    ):
        self.sender = sender
        self.receiver = receiver
        self.msg_type = msg_type
        self.content = content
        # metadata 可放 task_id、优先级等扩展字段，不进入 prompt 也可供编排器使用。
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        """序列化为普通 dict，便于 JSON 日志或跨进程传递。"""
        return {
            "sender": self.sender,
            "receiver": self.receiver,
            "type": self.msg_type,
            "content": self.content,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        # 截断 content，避免在调试打印时刷屏。
        return f"[{self.sender} -> {self.receiver}] ({self.msg_type}) {self.content[:50]}"


class BaseAgent(ABC):
    """Agent 抽象基类 — 所有具体 Agent（如 ReActAgent）的父类。

    子类必须实现 ``think`` / ``act``；默认 ``run`` 提供「最多 15 轮」的简易循环。
    更精细的 ReAct 解析与工具选择通常在子类中覆盖 ``run`` 或强化 think/act。
    """

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
        # 本 Agent 发出/相关的消息缓存；编排器 broadcast 时会写入。
        self.message_history: list[AgentMessage] = []

    @abstractmethod
    async def think(self, task: str, context: Optional[dict] = None) -> str:
        """思考/推理阶段：根据任务与上下文生成下一步想法或最终答案草稿。

        返回空字符串表示「无需继续」；具体语义由子类约定。
        """
        ...

    @abstractmethod
    async def act(self, thought: str) -> str:
        """行动阶段：解析 thought 中的工具调用意图并执行，返回 Observation 文本。

        若无需调用工具（已可给出 Final Answer），应返回空字符串，
        以便默认 ``run`` 把 thought 当作最终结果退出循环。
        """
        ...

    async def run(self, task: str, context: Optional[dict] = None) -> dict:
        """执行 Agent 的完整简易 ReAct 循环（基类默认实现）。

        参数
        ----
        task: 本轮要完成的任务描述。
        context: 可选上下文（如上一 Agent 的输出、上一次工具结果）。

        返回值
        ------
        dict，至少包含 agent/role/result/tool_calls。
        注意：基类返回值未包含 iterations 字段；子类可扩展。

        边界
        ----
        硬编码最多 15 轮，防止 LLM 反复调工具烧光配额。
        """
        result = ""
        tool_calls_log = []

        for iteration in range(15):  # 硬边界: 最多 15 轮
            thought = await self.think(task, context)
            if not thought:
                break

            action_result = await self.act(thought)
            if action_result:
                tool_calls_log.append({"iteration": iteration, "result": action_result})
                # 把工具结果并入 context，供下一轮 think 使用。
                context = (context or {}) | {"last_tool_result": action_result}
            else:
                # act 返回空 → 认为 thought 已是最终答案（或无需工具）。
                result = thought
                break

        return {
            "agent": self.name,
            "role": self.role,
            "result": result or "未能完成任务",
            "tool_calls": tool_calls_log,
        }

    def send_message(self, receiver: str, msg_type: str, content: str) -> AgentMessage:
        """构造一条发出消息并记入本 Agent 的 message_history，供编排/调试。"""
        msg = AgentMessage(self.name, receiver, msg_type, content)
        self.message_history.append(msg)
        return msg

    def receive_messages(self, sender: str | None = None) -> list[AgentMessage]:
        """读取本地消息历史；可按 sender 过滤。返回副本，避免调用方原地修改内部列表。"""
        if sender:
            return [m for m in self.message_history if m.sender == sender]
        return self.message_history.copy()
