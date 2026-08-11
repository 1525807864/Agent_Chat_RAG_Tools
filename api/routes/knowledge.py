"""api.routes.knowledge — 知识库与知识图谱相关 HTTP 路由。

- ``POST /api/knowledge/build``：构建向量库 + 抽取图谱三元组并落盘
- ``GET /api/knowledge/graph/stats``：图谱统计（含 persist_path）

``doc_dir`` 受应用层路径白名单约束（默认仅 ``data/`` 下）。
"""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_agent_app
from api.schemas import BuildKBRequest, BuildKBResponse, GraphStatsResponse
from application.services.agent_application import AgentApplication
from shared.errors import AppError

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/build", response_model=BuildKBResponse)
async def build_knowledge_base(
    req: BuildKBRequest,
    app: AgentApplication = Depends(get_agent_app),
) -> BuildKBResponse:
    """根据本地文档目录构建向量知识库，并抽取图谱三元组（JSON 持久化）。"""
    try:
        count = app.build_knowledge_base(req.doc_dir)
    except AppError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return BuildKBResponse(
        doc_dir=req.doc_dir,
        chunk_count=count,
        message=f"知识库构建完成，共加载 {count} 个文档片段",
    )


@router.get("/graph/stats", response_model=GraphStatsResponse)
async def get_graph_stats(
    app: AgentApplication = Depends(get_agent_app),
) -> GraphStatsResponse:
    """返回知识图谱统计（节点/边/密度/持久化路径）。"""
    try:
        stats = app.get_graph_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return GraphStatsResponse(stats=stats)
