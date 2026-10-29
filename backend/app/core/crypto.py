"""凭据加密：AES-256-GCM 对称加密，密钥来自 CREDENTIAL_SECRET 环境变量。

存储格式：base64(iv).base64(tag).base64(ciphertext)
"""
import base64
import os
import hashlib

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


def _key() -> bytes:
    # 将任意长度密钥派生为 32 字节
    return hashlib.sha256(settings.CREDENTIAL_SECRET.encode()).digest()


def encrypt(plain: str) -> str:
    if not plain:
        return ""
    iv = os.urandom(12)
    aesgcm = AESGCM(_key())
    ct = aesgcm.encrypt(iv, plain.encode(), None)
    tag = ct[-16:]
    cipher = ct[:-16]
    return ".".join([base64.b64encode(x).decode() for x in (iv, tag, cipher)])


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        iv, tag, cipher = [base64.b64decode(x) for x in token.split(".")]
        aesgcm = AESGCM(_key())
        plain = aesgcm.decrypt(iv, cipher + tag, None)
        return plain.decode()
    except Exception:
        return ""
