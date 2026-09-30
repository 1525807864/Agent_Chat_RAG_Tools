"""MySQL 业务表访问（会话外的审计 / 路由 / 因子 / Job / 记忆索引）。"""

from infrastructure.db.schema import ensure_all_schemas

__all__ = ["ensure_all_schemas"]
