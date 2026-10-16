"""
JWT 鉴权 + 角色（最小实现，不依赖第三方库，纯标准库 HMAC-SHA256）。

角色映射（来自 tenant.plan）：
  free / pro / enterprise
  enterprise 可私有部署，配额最高
"""
import json
import time
import base64
import hmac
import hashlib
import os

SECRET = os.environ.get("JZ_SAAS_JWT_SECRET", "dev-secret-change-me")
TTL = int(os.environ.get("JZ_SAAS_JWT_TTL", 3600))


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_token(tenant_id: str, role: str, plan: str = "free", claims=None) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(
        json.dumps(
            {
                "tenant_id": tenant_id,
                "role": role,
                "plan": plan,
                "iat": int(time.time()),
                "exp": int(time.time()) + TTL,
                **(claims or {}),
            },
            ensure_ascii=False,
        ).encode()
    )
    sig = _b64url(hmac.new(SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def verify_token(token: str):
    """返回 (claims, err)。err=None 表示通过。"""
    if not token or token.count(".") != 2:
        return None, "malformed_token"
    header, payload, sig = token.split(".")
    expect = _b64url(
        hmac.new(SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(sig, expect):
        return None, "invalid_signature"
    try:
        claims = json.loads(_b64url_decode(payload))
    except Exception:
        return None, "bad_payload"
    if int(claims.get("exp", 0)) < int(time.time()):
        return None, "token_expired"
    return claims, None
