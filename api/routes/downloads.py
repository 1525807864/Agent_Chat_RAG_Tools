"""桌面客户端下载。不需要登录：用户还没账号时就要能下载。"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.auth.client_ip import client_ip
from application.releases.desktop import DesktopReleaseService, build_desktop_release_service
from config.settings import get_settings
from domain.desktop_release import ReleaseUnavailable
from safety.http_rate_limit import allow_request
from shared.path_security import get_project_root

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


class DesktopDownloadMetaResponse(BaseModel):
    """登录页查询安装包是否可下。detail 只在不可用时给人看。"""

    available: bool
    filename: str = ""
    size_bytes: int = 0
    platform: str = "windows"
    detail: str = ""


def get_desktop_release_service() -> DesktopReleaseService:
    """按当前配置组装用例。每次请求新建，避免改 .env 后还拿着旧目录。"""
    settings = get_settings()
    raw_dir = Path(settings.desktop_release_dir)
    directory = raw_dir if raw_dir.is_absolute() else get_project_root() / raw_dir
    return build_desktop_release_service(
        directory=directory,
        filename=settings.desktop_release_name,
        max_bytes=settings.desktop_release_max_bytes,
        enabled=settings.desktop_download_enabled,
    )


def _unavailable(exc: ReleaseUnavailable) -> HTTPException:
    """对外只返回 message。绝对路径留在日志。"""
    if exc.internal:
        logger.warning("desktop download unavailable: %s", exc.internal)
    return HTTPException(status_code=404, detail=exc.message)


@router.get("/desktop/meta", response_model=DesktopDownloadMetaResponse)
async def desktop_download_meta(request: Request) -> DesktopDownloadMetaResponse:
    """安装包是否存在。登录页用它禁用按钮，避免点下去得到一页 JSON。"""
    settings = get_settings()
    ip = client_ip(request)
    if not await allow_request(f"download-meta:{ip}", settings.desktop_download_rate_limit, 60):
        raise HTTPException(status_code=429, detail="请求过多，请稍后再试")

    meta = get_desktop_release_service().metadata()
    return DesktopDownloadMetaResponse(
        available=meta.available,
        filename=meta.filename,
        size_bytes=meta.size_bytes,
        platform=meta.platform,
        detail=meta.detail,
    )


@router.get("/desktop")
async def download_desktop_installer(request: Request) -> FileResponse:
    """下发 Windows 安装包。文件名由服务端决定，不接受客户端路径。"""
    settings = get_settings()
    ip = client_ip(request)
    if not await allow_request(f"download:{ip}", settings.desktop_download_rate_limit, 60):
        raise HTTPException(status_code=429, detail="下载过于频繁，请稍后再试")

    service = get_desktop_release_service()
    try:
        package = service.require_package()
    except ReleaseUnavailable as exc:
        raise _unavailable(exc) from exc

    # 校验之后、打开之前文件可能被换掉，再确认一次仍是普通文件
    if not package.path.is_file():
        logger.warning("desktop download disappeared name=%s", package.filename)
        raise HTTPException(status_code=404, detail="安装包尚未发布")

    logger.info(
        "desktop download start name=%s bytes=%s",
        package.filename,
        package.size_bytes,
    )
    return FileResponse(
        path=package.path,
        media_type=package.media_type,
        filename=package.filename,
        content_disposition_type="attachment",
    )
