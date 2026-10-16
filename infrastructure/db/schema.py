"""幂等建齐 P0/P1/P2 业务表；MySQL 不可用时静默跳过。"""

from __future__ import annotations

import logging
from pathlib import Path

_log = logging.getLogger(__name__)


def _connect():
    import pymysql
    from pymysql.cursors import DictCursor

    from api.auth.mysql_conn import mysql_kwargs

    return pymysql.connect(**mysql_kwargs(), cursorclass=DictCursor)


def mysql_reachable() -> bool:
    """探测 MySQL 是否可用（本机无 Docker 时返回 False）。"""
    try:
        conn = _connect()
        conn.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def ensure_all_schemas() -> bool:
    """执行 sql/p0|p1|p2|p3_schema.sql；成功返回 True。"""
    root = Path(__file__).resolve().parents[2]
    files = [
        root / "sql" / "p0_schema.sql",
        root / "sql" / "p1_schema.sql",
        root / "sql" / "p2_schema.sql",
        root / "sql" / "p3_schema.sql",
        root / "sql" / "p4_ops_targets.sql",
        root / "sql" / "p5_access_jobs.sql",
    ]
    try:
        conn = _connect()
    except Exception as e:  # noqa: BLE001
        _log.warning("MySQL 不可用，跳过 ensure_all_schemas: %s", e)
        return False

    try:
        applied: list[str] = []
        missing: list[str] = []
        with conn.cursor() as cur:
            for path in files:
                if not path.is_file():
                    missing.append(path.name)
                    continue
                sql = path.read_text(encoding="utf-8")
                # 按分号拆语句；跳过空行与纯注释块
                for stmt in sql.split(";"):
                    body = "\n".join(
                        ln
                        for ln in stmt.splitlines()
                        if ln.strip() and not ln.strip().startswith("--")
                    ).strip()
                    if body:
                        cur.execute(body)
                applied.append(path.name)
        conn.commit()
        if missing:
            _log.warning("MySQL schema 文件缺失（镜像未 COPY sql/？）: %s", missing)
        _log.info("MySQL schema 已就绪 applied=%s", applied)
        return True
    except Exception as e:  # noqa: BLE001
        _log.warning("ensure_all_schemas 失败: %s", e)
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False
    finally:
        conn.close()
