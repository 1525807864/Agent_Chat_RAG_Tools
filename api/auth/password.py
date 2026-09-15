"""Argon2id 密码哈希。登录走 verify，不明文存库、不在日志里打密码。"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# OWASP 交互式推荐量级：2 次迭代、约 19MiB、单线程。2C2G 上登录可接受。
_HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


def hash_password(plain: str) -> str:
    """把明文密码变成 Argon2id 哈希字符串（含盐，可直接入库）。"""
    return _HASHER.hash(plain)


def verify_password(plain: str, password_hash: str) -> bool:
    """恒定时间校验；哈希格式损坏也返回 False，避免把异常细节回给客户端。"""
    try:
        return bool(_HASHER.verify(password_hash, plain))
    except (VerifyMismatchError, InvalidHashError, TypeError, ValueError):
        return False
