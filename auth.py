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

# 生产模式（JZ_SAAS_ENV=prod）下 secret 缺失即拒绝启动，避免全租户共用 dev 密钥。
_ENV = os.environ.get("JZ_SAAS_ENV", "dev")
_DEFAULT_SECRET = "dev-secret-change-me"
_SECRET = os.environ.get("JZ_SAAS_JWT_SECRET", "")
if not _SECRET:
    if _ENV == "prod":
        raise RuntimeError(
            "JZ_SAAS_JWT_SECRET must be set in production (JZ_SAAS_ENV=prod); "
            "refusing to start with the default dev secret."
        )
    _SECRET = _DEFAULT_SECRET
    import warnings

    warnings.warn(
        "JZ_SAAS_JWT_SECRET not set, using insecure dev secret. "
        "Set it in production and set JZ_SAAS_ENV=prod."
    )
SECRET = _SECRET
TTL = int(os.environ.get("JZ_SAAS_JWT_TTL", 3600))
# exp 校验时钟漂移容差（秒）：跨机部署 / NTP 偏差下避免误拒刚签发 token。
EXP_SKEW = int(os.environ.get("JZ_SAAS_JWT_SKEW", 60))


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
    now = int(time.time())
    # exp 带时钟漂移容差，避免跨机 NTP 偏差误拒刚签发 token
    if int(claims.get("exp", 0)) < now - EXP_SKEW:
        return None, "token_expired"
    # 拒绝 iat 在未来（时钟异常 / 伪造 token），超过容差视为非法
    iat = int(claims.get("iat", now))
    if iat > now + EXP_SKEW:
        return None, "iat_in_future"
    return claims, None
