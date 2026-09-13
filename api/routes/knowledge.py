"""知识库路由：同步/异步建库、文档列表、图谱统计。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.auth.deps import AuthUser, get_current_user
from api.deps import get_agent_app
from api.schemas import (
    BuildKBRequest,
    BuildKBResponse,
    DocInfo,
    DocListResponse,
    GraphStatsResponse,
    KbJobResponse,
)
from application.jobs.kb_jobs import enqueue_kb_build, get_job
from application.services.agent_application import AgentApplication
from application.tenancy import tenant_docs_dir
from shared.errors import AppError

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/build", response_model=BuildKBResponse)
async def build_knowledge_base(
    req: BuildKBRequest,
    user: AuthUser = Depends(get_current_user),
    app: AgentApplication = Depends(get_agent_app),
) -> BuildKBResponse:
    """同步建库（小语料）；大语料请用 /build/async。"""
    try:
        count = app.build_knowledge_base(req.doc_dir, tenant_id=user.tenant_id)
    except AppError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return BuildKBResponse(
        doc_dir=req.doc_dir,
        chunk_count=count,
        message=(
            f"知识库构建完成，共加载 {count} 个文档片段 "
            f"(tenant={user.tenant_id})"
        ),
    )


@router.post("/build/async", response_model=KbJobResponse)
async def build_knowledge_base_async(
    req: BuildKBRequest,
    user: AuthUser = Depends(get_current_user),
    app: AgentApplication = Depends(get_agent_app),
) -> KbJobResponse:
    """异步建库：立即返回 job_id，轮询 GET /build/{job_id}。"""
    job = await enqueue_kb_build(
        app, tenant_id=user.tenant_id, doc_dir=req.doc_dir
    )
    return KbJobResponse(
        job_id=job.id,
        tenant_id=job.tenant_id,
        doc_dir=job.doc_dir,
        status=job.status,
        progress=job.progress,
        message=job.message,
        chunk_count=job.chunk_count,
        error=job.error,
    )


@router.get("/build/{job_id}", response_model=KbJobResponse)
async def get_build_job(
    job_id: str,
    user: AuthUser = Depends(get_current_user),
) -> KbJobResponse:
    job = get_job(job_id)
    if not job or job.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="job not found")
    return KbJobResponse(
        job_id=job.id,
        tenant_id=job.tenant_id,
        doc_dir=job.doc_dir,
        status=job.status,
        progress=job.progress,
        message=job.message,
        chunk_count=job.chunk_count,
        error=job.error,
    )


@router.get("/docs", response_model=DocListResponse)
async def list_docs(
    user: AuthUser = Depends(get_current_user),
    app: AgentApplication = Depends(get_agent_app),
) -> DocListResponse:
    docs = [
        DocInfo(**d) for d in app.list_tenant_docs(user.tenant_id)
    ]
    return DocListResponse(tenant_id=user.tenant_id, docs=docs)


@router.post("/docs/upload")
async def upload_doc(
    user: AuthUser = Depends(get_current_user),
    file: UploadFile = File(...),
) -> dict:
    """上传文件到租户 docs 目录（需在 allowed_data_roots 下）。"""
    root = tenant_docs_dir(Path("."), user.tenant_id)
    # 用项目根
    from shared.path_security import get_project_root

    root = tenant_docs_dir(get_project_root(), user.tenant_id)
    root.mkdir(parents=True, exist_ok=True)
    name = Path(file.filename or "upload.bin").name
    dest = root / name
    data = await file.read()
    dest.write_bytes(data)
    return {
        "ok": True,
        "tenant_id": user.tenant_id,
        "path": name,
        "size": len(data),
    }


@router.get("/graph/stats", response_model=GraphStatsResponse)
async def get_graph_stats(
    user: AuthUser = Depends(get_current_user),
    app: AgentApplication = Depends(get_agent_app),
) -> GraphStatsResponse:
    try:
        graph = app._graph_for_tenant(user.tenant_id)
        stats = graph.get_graph_stats()
        if isinstance(stats, dict):
            stats = {
                **stats,
                "tenant_id": user.tenant_id,
                "user_id": user.user_id,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return GraphStatsResponse(stats=stats)
