"""api.schemas — FastAPI 请求/响应的 Pydantic 数据模型

本模块职责
==========
定义 HTTP 层的「契约」：前端/调用方传什么字段、服务端回什么结构。
与 ``application.AgentApplication`` 的 Python 方法参数解耦——路由负责把模型字段
映射到 ``ask_chat`` / ``ask_rag`` 等业务调用。

在架构中的位置
==============
``routes/*`` 的 ``response_model=...`` 与函数参数类型注解都依赖本文件；
OpenAPI（Swagger UI ``/docs``）也据此自动生成文档。

为何单独成文件
==============
- 复用：同一模型可被多个路由引用
- 校验集中：``Field(min_length=...)`` 在进入业务逻辑前就拒绝非法请求
- 前端对齐：TypeScript 可对照这些字段生成类型

注意
====
``Mode`` / ``MultiMode`` 用 ``Literal`` 限制枚举值，与 CLI ``/mode`` 及
``AgentApplication`` 支持的模式保持一致；新增模式时请三处同步修改。
"""

from typing import List, Literal, Optional, Any
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 模式字面量类型
# ---------------------------------------------------------------------------
# Mode：单次对话请求可选的「产品模式」，对应 AgentApplication.ask_* 系列方法。
# MultiMode：仅当 mode="multi" 时有意义，对应 MultiAgentOrchestrator 三种协作策略。
Mode = Literal["chat", "rag", "graph-rag", "agent", "multi"]
MultiMode = Literal["sequential", "debate", "router"]


class WorkspaceFile(BaseModel):
    """本轮随请求带给 Agent 的工作区文件（路径相对 workspace_root）。"""

    path: str = Field(..., min_length=1, max_length=512)
    content: str = Field(..., max_length=500_000)


class ChatRequest(BaseModel):
    """聊天请求体 — ``POST /api/chat`` 与 ``POST /api/chat/stream`` 共用。

    模型凭证字段
    ------------
    前端设置面板填写后每次发消息带上；空则回退 .env / Settings。
    api_base 是大模型厂商地址，不是前端 VITE_API_BASE。

    工作区字段（桌面端完整版）
    ------------------------
    workspace_root:
        本地工作区绝对路径；``mode=agent`` 时注入 list/read/write 工具。
    files:
        本轮已打开文件内容；大文件勿再塞进 message。
    """

    message: str = Field(..., min_length=1, max_length=10000)
    session_id: str = Field(default="default", min_length=1, max_length=128)
    mode: Mode = "chat"
    multi_mode: MultiMode = "sequential"  # 仅 mode=multi 时有效
    agent_name: str = "assistant"  # 仅 mode=agent 时有效

    api_key: Optional[str] = Field(
        default=None,
        description="大模型API key:不传则用服务端DEEPSEEK_API_KEY",
        max_length=512,
    )
    api_base: Optional[str] = Field(
        default=None,
        description="OpenAI 兼容 Base，如 https://api.deepseek.com/v1",
        max_length=512,
    )
    model_name: Optional[str] = Field(
        default=None,
        description="模型名，如 deepseek-chat / deepseek-v4-flash",
        max_length=128,
    )

    workspace_root: Optional[str] = Field(
        default=None,
        description="桌面端工作区绝对路径；Agent 工具沙箱根",
        max_length=1024,
    )
    files: Optional[List[WorkspaceFile]] = Field(
        default=None,
        description="本轮打开的工作区文件",
    )


class ChatResponse(BaseModel):
    """非流式聊天响应 — 整段答案一次性返回。

    meta 预留给扩展信息（如 multi 时回传实际使用的 multi_mode、
    未来的检索来源列表等），避免频繁改顶层字段破坏前端兼容。
    """

    session_id: str
    mode: str
    answer: str
    meta: dict[str, Any] = Field(default_factory=dict)


class SessionMessage(BaseModel):
    """会话中的单条历史消息（简化视图）。

    与 ``session_store`` 内部可能附带的 ``timestamp`` 等字段解耦：
    HTTP 响应只暴露前端展示必需的 role/content，避免泄漏存储实现细节。
    """

    role: str
    content: str


class SessionHistoryResponse(BaseModel):
    """``GET /api/sessions/{session_id}`` 的响应：某会话的近期消息列表。"""

    session_id: str
    messages: List[SessionMessage]


class SessionListResponse(BaseModel):
    """``GET /api/sessions`` 的响应：当前后端中存在历史的会话 ID 列表。"""

    sessions: List[str]


class BuildKBRequest(BaseModel):
    """构建知识库请求 — ``POST /api/knowledge/build``。

    doc_dir 必须落在配置 ``allowed_data_roots``（默认 ``data/``）内，
    由 ``DocumentLoader.load_directory`` 扫描其中的文档文件。
    """

    doc_dir: str = Field(..., description="本地文档目录路径（须在 data/ 下），如 data/docs")


class BuildKBResponse(BaseModel):
    """知识库构建结果：返回实际写入向量库的分块数量与人类可读说明。"""

    doc_dir: str
    chunk_count: int
    message: str


class HealthResponse(BaseModel):
    """健康检查响应 — 用于探活与告知前端当前支持的对话 mode 列表。"""

    status: str
    modes: list[str]


class GraphStatsResponse(BaseModel):
    """知识图谱统计响应 — 包装 ``KnowledgeGraph.get_graph_stats()`` 的原始 dict。"""

    stats: dict[str, Any]


class ErrorResponse(BaseModel):
    """统一错误体形状（文档用）；实际异常多由 FastAPI ``HTTPException.detail`` 承载。"""

    detail: str
