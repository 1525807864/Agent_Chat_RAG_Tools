"""从配置目录读取 Windows 安装包。只接受白名单文件名，拒绝路径穿越。"""

from __future__ import annotations

import re
from pathlib import Path

from domain.desktop_release import ReleaseUnavailable, StoredInstaller

# 只允许单层文件名，禁止 / \ 和 ..
_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.exe$")
_MEDIA_TYPE = "application/octet-stream"


class FilesystemReleaseRepository:
    """安装包仓库：一个目录 + 一个固定文件名。"""

    def __init__(self, directory: Path, filename: str, *, max_bytes: int) -> None:
        self._directory = directory
        self._filename = (filename or "").strip()
        self._max_bytes = max_bytes

    def load_windows_installer(self) -> StoredInstaller:
        """定位安装包。失败时不把本机绝对路径放进 ``message``。"""
        name = self._filename
        if not _FILENAME_RE.fullmatch(name):
            raise ReleaseUnavailable(
                "安装包配置无效",
                internal=f"rejected filename={name!r}",
            )
        if self._max_bytes < 1:
            raise ReleaseUnavailable(
                "安装包配置无效",
                internal=f"max_bytes={self._max_bytes}",
            )

        root = self._directory
        try:
            root_resolved = root.resolve(strict=False)
        except OSError as exc:
            raise ReleaseUnavailable(
                "安装包尚未发布",
                internal=f"resolve dir failed: {exc}",
            ) from exc

        # 先拼路径再 resolve，符号链接若指向目录外会被 relative_to 拦住
        candidate = (root_resolved / name).resolve(strict=False)
        try:
            candidate.relative_to(root_resolved)
        except ValueError as exc:
            raise ReleaseUnavailable(
                "安装包配置无效",
                internal=f"path escaped release dir: {candidate}",
            ) from exc

        if not candidate.is_file():
            raise ReleaseUnavailable(
                "安装包尚未发布",
                internal=f"missing file under release dir name={name}",
            )

        try:
            size = candidate.stat().st_size
        except OSError as exc:
            raise ReleaseUnavailable(
                "安装包尚未发布",
                internal=f"stat failed name={name}: {exc}",
            ) from exc

        if size <= 0:
            raise ReleaseUnavailable(
                "安装包不可用",
                internal=f"empty file name={name}",
            )
        if size > self._max_bytes:
            raise ReleaseUnavailable(
                "安装包不可用",
                internal=f"file too large name={name} bytes={size} max={self._max_bytes}",
            )

        return StoredInstaller(
            filename=name,
            media_type=_MEDIA_TYPE,
            size_bytes=size,
            path=candidate,
        )
