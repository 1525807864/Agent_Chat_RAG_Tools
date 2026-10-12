"""全站统一时钟：Asia/Shanghai（北京时间）。

业务写入、展示、按日汇总都用这里，禁止各模块私自 datetime.utcnow / timezone.utc。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo("Asia/Shanghai")


def now_beijing() -> datetime:
    """带时区的当前北京时间。"""
    return datetime.now(BEIJING)


def now_iso() -> str:
    """ISO8601，含 +08:00，便于排序与前端解析。"""
    return now_beijing().isoformat(timespec="milliseconds")


def now_mysql() -> str:
    """写入 MySQL DATETIME(6) 的字符串（无时区后缀，语义为北京时间）。"""
    return now_beijing().strftime("%Y-%m-%d %H:%M:%S.%f")


def now_day() -> str:
    """北京时间自然日 YYYY-MM-DD（计费日汇总等）。"""
    return now_beijing().strftime("%Y-%m-%d")


def now_compact() -> str:
    """文件名用紧凑时间戳，如 20261009T034600。"""
    return now_beijing().strftime("%Y%m%dT%H%M%S")


def now_epoch() -> float:
    """Unix 时间戳（与时区无关，但取值时刻按北京时钟）。"""
    return now_beijing().timestamp()
