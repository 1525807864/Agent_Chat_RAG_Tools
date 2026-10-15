"""结构化日志模块

- 控制台 + 轮转文件（默认 ``data/app.log``）
- ``configure_logging`` 幂等增强 root（兼容 uvicorn 已挂 handler）
- 各模块 ``logging.getLogger(__name__)`` / ``get_logger`` 均可落盘
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False


def configure_logging(
    level: str = "INFO",
    log_file: str | None = "data/app.log",
) -> None:
    """幂等：确保 root 有控制台与轮转文件 handler。"""
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger()
    level_num = getattr(logging, (level or "INFO").upper(), logging.INFO)
    root.setLevel(level_num)

    console_fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
    )

    has_console = any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, RotatingFileHandler)
        for h in root.handlers
    )
    if not has_console:
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.DEBUG)
        console.setFormatter(console_fmt)
        root.addHandler(console)

    if log_file:
        has_file = any(isinstance(h, RotatingFileHandler) for h in root.handlers)
        if not has_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(file_fmt)
            root.addHandler(file_handler)

    for noisy in ("httpx", "httpcore", "openai", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
    logging.getLogger("nexora").info(
        "日志已配置 level=%s file=%s handlers=%s",
        logging.getLevelName(level_num),
        log_file or "(console-only)",
        len(root.handlers),
    )


def get_logger(name: str = "nexora") -> logging.Logger:
    """获取命名 logger（必要时自动 configure）。"""
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)


def setup_logger(
    name: str = "agent_app",
    level: str = "INFO",
    log_file: str | None = "data/app.log",
    json_format: bool = False,
) -> logging.Logger:
    """兼容旧调用。"""
    _ = json_format
    configure_logging(level=level, log_file=log_file)
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


logger = setup_logger()
