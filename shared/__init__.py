"""共享内核：配置、日志、统一错误码、路径安全。

依赖方向：被 domain / application / infrastructure / interfaces 引用；
本包不依赖业务用例或具体基础设施实现。
"""

from shared.errors import AppError, ErrorCode
from shared.path_security import PathSecurityError, resolve_safe_path

__all__ = [
    "AppError",
    "ErrorCode",
    "PathSecurityError",
    "resolve_safe_path",
]
