# ============================================================================
# conftest.py（power_test）
# pytest 收集本目录前最先执行：修正 DeepEval 环境，避免 .env.local 里
# CONFIDENT_REGION=CN 导致 import deepeval 直接 ValidationError。
# ============================================================================

from __future__ import annotations

import os

# 新版 deepeval Settings 仅允许 EU / US；本机裁判评测不依赖 Confident 区域
os.environ["CONFIDENT_REGION"] = "US"
# Windows 控制台编码
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
# 单测默认 sqlite
os.environ.setdefault("AUTH_BACKEND", "sqlite")
os.environ.setdefault("MEMORY_BACKEND", "sqlite")
