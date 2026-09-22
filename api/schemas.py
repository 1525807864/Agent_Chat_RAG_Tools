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
# MultiMode：仅当 mode="multi" 时有意义，对应 LangGraph 三种协作策略。
Mode = Literal["chat", "rag", "graph-rag", "agent", "multi", "consult"]
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
    #被测网站origin；为空则不启用e2e工具
    e2e_base_url: Optional[str] = Field(
        default=None,
        max_length=512,
        description="被测网站origin；为空则不启用e2e工具",
    )
    #该站点测试文档所在租户向量库；空则不预检索
    qa_tenant_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="该站点测试文档所在租户向量库；空则不预检索",
    )


class ChatResponse(BaseModel):
    """非流式聊天响应 — 整段答案一次性返回。

    meta 预留给扩展信息（如 multi 时回传实际使用的 multi_mode、
    RAG sources、多 Agent 轨迹等），避免频繁改顶层字段破坏前端兼容。
    """

    session_id: str
    mode: str
    answer: str
    meta: dict[str, Any] = Field(default_factory=dict)


class SourceHit(BaseModel):
    """RAG 单条引用。"""

    doc_id: str
    snippet: str
    score: Optional[float] = None
    page: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionMessage(BaseModel):
    """会话中的单条历史消息（简化视图）。"""

    role: str
    content: str


class SessionHistoryResponse(BaseModel):
    """``GET /api/sessions/{session_id}`` 的响应。"""

    session_id: str
    messages: List[SessionMessage]


class SessionListResponse(BaseModel):
    """``GET /api/sessions`` 的响应。"""

    sessions: List[str]


class SolipNextQuestion(BaseModel):
    """Solip 预测的一条「用户可能的下一问」。"""

    question: str
    confidence: float = 0.5
    reason: str = ""


class SessionMemoryResponse(BaseModel):
    """``GET /api/sessions/{session_id}/memory``：摘要 + Solip 快照。"""

    session_id: str
    intent_hypothesis: str = ""
    open_loops: List[str] = Field(default_factory=list)
    next_questions: List[SolipNextQuestion] = Field(default_factory=list)
    summary: str = ""


class BuildKBRequest(BaseModel):
    """构建知识库请求 — ``POST /api/knowledge/build``。

    ``doc_dir`` 可选：不传时后端使用当前租户上传目录
    ``data/tenants/<tenant_id>/docs``。
    """

    doc_dir: Optional[str] = Field(
        default=None,
        description="已忽略：始终使用当前租户目录 data/tenants/<tenant>/docs",
    )


class BuildKBResponse(BaseModel):
    """知识库构建结果：返回实际写入向量库的分块数量与人类可读说明。"""

    doc_dir: str
    chunk_count: int
    message: str


class KbJobResponse(BaseModel):
    """异步建库任务状态。"""

    job_id: str
    tenant_id: str
    doc_dir: str
    status: str
    progress: int = 0
    message: str = ""
    chunk_count: int = 0
    error: Optional[str] = None


class DocInfo(BaseModel):
    """租户文档列表项。"""

    name: str
    size: int
    path: str


class DocListResponse(BaseModel):
    """租户文档列表。"""

    tenant_id: str
    docs: List[DocInfo] = Field(default_factory=list)


class UsageResponse(BaseModel):
    """用量快照。"""

    tenant_id: Optional[str] = None
    usage: dict[str, Any] = Field(default_factory=dict)


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
