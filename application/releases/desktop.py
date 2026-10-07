"""桌面安装包用例：开关、描述、取出可下载文件。路由不直接碰磁盘。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from domain.desktop_release import ReleaseUnavailable, StoredInstaller

logger = logging.getLogger(__name__)


class ReleaseRepository(Protocol):
    """安装包从哪里来。文件系统实现在 infrastructure。"""

    def load_windows_installer(self) -> StoredInstaller:
        """返回已校验的安装包；没有或非法时抛 ReleaseUnavailable。"""


@dataclass(frozen=True)
class DesktopDownloadMeta:
    """给登录页用的公开信息，不含本机路径。"""

    available: bool
    filename: str
    size_bytes: int
    platform: str
    detail: str


class DesktopReleaseService:
    """是否开放下载，以及拿出哪一个安装包。"""

    def __init__(self, repository: ReleaseRepository, *, enabled: bool) -> None:
        self._repository = repository
        self._enabled = enabled

    def metadata(self) -> DesktopDownloadMeta:
        """不抛异常。页面用 available 决定按钮能不能点。"""
        if not self._enabled:
            return DesktopDownloadMeta(
                available=False,
                filename="",
                size_bytes=0,
                platform="windows",
                detail="未开放下载",
            )
        try:
            package = self._repository.load_windows_installer()
        except ReleaseUnavailable as exc:
            if exc.internal:
                logger.warning("desktop release unavailable: %s", exc.internal)
            return DesktopDownloadMeta(
                available=False,
                filename="",
                size_bytes=0,
                platform="windows",
                detail=exc.message,
            )
        return DesktopDownloadMeta(
            available=True,
            filename=package.filename,
            size_bytes=package.size_bytes,
            platform="windows",
            detail="",
        )

    def require_package(self) -> StoredInstaller:
        """下载接口调用。关闭或文件不可用时抛 ReleaseUnavailable。"""
        if not self._enabled:
            raise ReleaseUnavailable("未开放下载")
        return self._repository.load_windows_installer()


def build_desktop_release_service(
    *,
    directory: Path,
    filename: str,
    max_bytes: int,
    enabled: bool,
) -> DesktopReleaseService:
    """组装用例。放在应用层，避免路由 import 具体存储实现以外的构造细节散落。"""
    from infrastructure.releases.filesystem import FilesystemReleaseRepository

    repository = FilesystemReleaseRepository(
        directory,
        filename,
        max_bytes=max_bytes,
    )
    return DesktopReleaseService(repository, enabled=enabled)
