"""
Authentication
==============
Stateless HMAC-signed bearer tokens for the FastAPI layer. Good enough
for an internal deployment; swap for OAuth2/OIDC in a multi-tenant
production rollout.

Token format: base64url(payload) . base64url(hmac_sha256(payload, secret))
payload is a compact JSON with subject, roles, issued-at, expiry.
"""

import base64
import hashlib
import hmac
import json
import logging
import time

from security.secrets import get_secret

logger = logging.getLogger(__name__)


class AuthError(Exception):
    pass


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(payload: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    return _b64url(sig)


def issue_token(subject: str, roles=None, ttl_seconds=3600) -> str:
    now = int(time.time())
    body = {
        "sub": subject,
        "roles": list(roles or []),
        "iat": now,
        "exp": now + int(ttl_seconds),
    }
    payload = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    secret = get_secret("AUTH_SIGNING_KEY")
    return f"{_b64url(payload)}.{_sign(payload, secret)}"


def verify_token(token: str) -> dict:
    try:
        payload_b64, sig_b64 = token.split(".", 1)
    except ValueError:
        raise AuthError("malformed token")

    payload = _b64url_decode(payload_b64)
    secret = get_secret("AUTH_SIGNING_KEY")
    expected = _sign(payload, secret)
    if not hmac.compare_digest(expected, sig_b64):
        raise AuthError("bad signature")

    body = json.loads(payload)
    if body.get("exp", 0) < int(time.time()):
        raise AuthError("token expired")
    return body
