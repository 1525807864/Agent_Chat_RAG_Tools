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
#允许上传的后缀(与DocumentLoader.SUPPORTED_SUFFIXES对齐)
ALLOWED_UPLOAD_SUFFIXES = {
    ".pdf", ".txt", ".md", ".html", ".csv", ".json", ".docx", ".xlsx",
}
#单文件上限:20MB,防止内存被撑爆
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

@router.post("/build", response_model=BuildKBResponse)
async def build_knowledge_base(
    req: BuildKBRequest,
    user: AuthUser = Depends(get_current_user),
    app: AgentApplication = Depends(get_agent_app),
) -> BuildKBResponse:
    """同步建库（小语料）；大语料请用 /build/async。"""
    from application.tenancy import tenant_docs_dir  #租户docs路径工具
    from shared.path_security import get_project_root #项目根

    # 忽略客户端 doc_dir，避免跨租户读 data/ 下其它目录
    docs_root = tenant_docs_dir(get_project_root(), user.tenant_id)
    docs_root.mkdir(parents=True, exist_ok=True)
    try:
        raw_dir = str(docs_root.relative_to(get_project_root())).replace("\\", "/")
    except ValueError:
        raw_dir = str(docs_root)
    try:
        count = app.build_knowledge_base(raw_dir,tenant_id=user.tenant_id)
    except AppError:
        raise #业务错误原样抛给异常处理器
    except Exception as e:
        raise HTTPException(status_code=500,detail=str(e)) from e
    
    #空库：给人类可读提示 
    if count == 0:
        message = (
            f"目录存在但未解析到任何文档块(tenant={user.tenant_id})。"
            f"请先上传 pdf/docx/xlsx/txt/md 等文件后再构建。"
        )
    else:
        message = (
            f"知识库构建完成，共加载 {count} 个文档片段 "
            f"(tenant={user.tenant_id})"
        )
    return BuildKBResponse(
        doc_dir=raw_dir,
        chunk_count=count,
        message=message,
    )

@router.post("/build/async", response_model=KbJobResponse)
async def build_knowledge_base_async(
    req: BuildKBRequest,
    user: AuthUser = Depends(get_current_user),
    app: AgentApplication = Depends(get_agent_app),
) -> KbJobResponse:
    """异步建库：立即返回 job_id，轮询 GET /build/{job_id}。"""
    from shared.path_security import get_project_root

    # 忽略客户端 doc_dir，只扫当前租户上传目录
    docs_root = tenant_docs_dir(get_project_root(), user.tenant_id)
    docs_root.mkdir(parents=True, exist_ok=True)
    try:
        raw_dir = str(docs_root.relative_to(get_project_root())).replace("\\", "/")
    except ValueError:
        raw_dir = str(docs_root)

    job = await enqueue_kb_build(
        app, tenant_id=user.tenant_id, doc_dir=raw_dir
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
    file: UploadFile = File(...),  # multipart 字段名必须叫 file
) -> dict:
    """上传单个文档到当前租户的 docs 目录。"""
    from shared.path_security import get_project_root
    # 原始文件名 → 只保留 basename，防止 ../../etc/passwd
    name = Path(file.filename or "upload.bin").name
    suffix = Path(name).suffix.lower()
    # 扩展名白名单
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {suffix}，允许: {sorted(ALLOWED_UPLOAD_SUFFIXES)}",
        )
    # 读入内存（演示够用；大文件可改成流式写盘）
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大，上限 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
        )
    if not data:
        raise HTTPException(status_code=400, detail="空文件，拒绝上传")
    # 目标目录：data/tenants/<tenant>/docs
    root = tenant_docs_dir(get_project_root(), user.tenant_id)
    root.mkdir(parents=True, exist_ok=True)
    dest = root / name
    dest.write_bytes(data)  # 覆盖同名文件
    return {
        "ok": True,
        "tenant_id": user.tenant_id,
        "path": name,  # 相对租户 docs 的文件名
        "size": len(data),
        "suffix": suffix,
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
