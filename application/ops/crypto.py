"""
Ops凭证加解密
- 库内只存密文
- api响应永不返回明文
- 密钥来自 OPS_CREDENTIALS_KEY；空则用 JWT_SECRET 做 SHA256→urlsafe_base64 派生
"""
from __future__ import annotations 
import base64
import hashlib 
from cryptography.fernet import Fernet,InvalidToken 
from config.settings import get_settings  

def _fernet()->Fernet:
    """构造 Fernet 实例"""
    raw = (get_settings().ops_credentials_key or "").strip()
    if not raw:
        # 无 OPS_CREDENTIALS_KEY 时，用 JWT_SECRET 做 SHA256→urlsafe_base64 派生
        raw = (get_settings().jwt_secret or "nexora-dev-only-ops-key").strip()
    if len(raw) == 44:
        try:
            return Fernet(raw.encode("utf-8"))
        except Exception:
            pass 
    # 任意口令
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key) 

def encrypt_secret(plain: str | None)->str | None:
    """明文->密文字符串；空/None -> None"""
    text = (plain or "").strip()
    if not text:
        return None 
    token = _fernet().encrypt(text.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(blob: str | None) -> str | None:
    """密文 → 明文；空/坏密文 → None（调用方当未配置）。"""
    text = (blob or "").strip()
    if not text:
        return None
    try:
        return _fernet().decrypt(text.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None