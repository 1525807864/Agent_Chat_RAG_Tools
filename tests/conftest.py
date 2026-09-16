"""单测默认走 SQLite 用户表，避免本机没有 MySQL 时登录用例连不上库。"""

from __future__ import annotations

import os

# 强制单测走 SQLite，避免本机/CI 环境里 AUTH_BACKEND=mysql 导致连不上库。
os.environ["AUTH_BACKEND"] = "sqlite"
