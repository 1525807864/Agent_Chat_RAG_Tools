"""结构化日志模块

知识点:
- StreamHandler → 控制台输出
- RotatingFileHandler → 防止日志文件无限膨胀 (maxBytes + backupCount)
- getattr(logging, level) → 字符串转 logging 常量
"""

import logging
import sys
from pathlib import Path


def setup_logger(
    name: str = "agent_app",
    level: str = "INFO",
    log_file: str | None = "data/app.log",
    json_format: bool = False,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    # ---- 控制台 handler ----
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # ---- 文件 handler (带轮转) ----
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setLevel(logging.INFO)
        file_fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
        )
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)

    return logger


logger = setup_logger()
