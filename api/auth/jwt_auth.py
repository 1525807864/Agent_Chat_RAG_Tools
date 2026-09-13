"""JWT 鉴权"""
from __future__ import annotations

import time 
from typing import Any,Optional
#jwt库
import jwt
from config.settings import get_settings

def create_access_token(
    *,
    subject:str, #用户名/email/手机号
    tenant_id:str, #租户ID，默认default
    extra:Optional[dict[str,Any]] = None, #额外声明
)->str:
    """
    签发access token
    返回示例::
         "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...."
    """
    #读取当前配置(.env/环境变量)
    settings = get_settings()
    #当前UTC秒级时间戳
    now = int(time.time())
    #过期时间=当前+配置的分钟数
    exp = now + int(settings.jwt_expire_minutes) * 60
    # jwt payload 
    payload = {
        "sub":subject,
        "tenant_id":tenant_id,
        "iat":now,
        "exp":exp,
    }
    #合并额外字段(不要覆盖sub/exp)
    if extra:
        payload.update(extra)
    #用密钥签名，返回字符串token
    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    #返回token字符串
    if isinstance(token,bytes):
        return token.decode("utf-8")
    return token

def decode_access_token(
    token:str,
)->dict[str,Any]:
    """
    解码access token，返回payload字典
    返回示例::
        {
            "sub": "user@example.com",
            "tenant_id": "default",
            "iat": 1715769600,
            "exp": 1715773200,
        }
    """
    #读取当前配置(.env/环境变量)
    settings = get_settings()
    #用密钥解码，返回payload字典
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )