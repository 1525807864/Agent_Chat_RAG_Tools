"""桌面安装包：领域对象，不读磁盘、不依赖 FastAPI。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoredInstaller:
    """已通过校验、可以下发的安装包。

    ``path`` 只给应用层打开文件用，禁止写进 HTTP 响应。
    """

    filename: str
    media_type: str
    size_bytes: int
    path: Path


class ReleaseUnavailable(Exception):
    """安装包不能下载。``message`` 可给用户看，``internal`` 只记日志。"""

    def __init__(self, message: str, *, internal: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.internal = internal
