"""从Settings拼PyMySQL / aiomysql连接参数。密码只从环境读，不要写进代码"""
from __future__ import annotations
from config.settings import get_settings
def mysql_kwargs() -> dict:
    """同步PyMySQL、异步aiomysql都能用的关键字参数"""
    s = get_settings()
    return {
        "host": s.mysql_host,
        "port": int(s.mysql_port),
        "user": s.mysql_user,
        "password": s.mysql_password,
        "database": s.mysql_database,
        "charset": "utf8mb4",
        # 自动提交由调用方 conn.commit()；这里关掉以免和显式事务打架
        "autocommit": False,
    }