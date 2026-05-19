"""Password hashing + signed-cookie session for the multi-tenant Web UI.

We deliberately avoid both ``passlib`` (unmaintained; broken against
``bcrypt>=4``) and JWT (overkill for first-party-only sessions). Instead:

- **Passwords**: ``bcrypt`` directly. 12 rounds default. Inputs are truncated
  to 72 bytes (bcrypt's hard limit) — clearly documented to callers.
- **Sessions**: ``itsdangerous.URLSafeTimedSerializer`` signing a small
  ``{"uid": int}`` dict. Stored in an HttpOnly, SameSite=Lax cookie.
  Max age default: 14 days.

The signing key comes from ``PAPERGUARD_SECRET_KEY``. If unset, a process-
local random key is generated and logged once. That is fine for dev and
single-process deployments; production multi-worker setups must set the
env var explicitly so all workers share the same key.
"""
from __future__ import annotations

import os
import secrets
import warnings
from dataclasses import dataclass
from typing import Any, cast

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE_NAME = "paperguard_session"
SESSION_MAX_AGE_SECONDS = 14 * 24 * 60 * 60  # 14 days
BCRYPT_ROUNDS = 12
_PASSWORD_MAX_BYTES = 72  # bcrypt hard limit

_secret_cache: str | None = None


def _truncate_password(password: str) -> bytes:
    """Encode to UTF-8 and truncate to 72 bytes (bcrypt's hard limit)."""
    return password.encode("utf-8")[:_PASSWORD_MAX_BYTES]


def hash_password(password: str) -> str:
    """Hash a plaintext password. Empty/None rejected."""
    if not password:
        raise ValueError("Password must not be empty")
    salted = bcrypt.hashpw(_truncate_password(password), bcrypt.gensalt(BCRYPT_ROUNDS))
    return salted.decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time compare. Returns False on any malformed hash."""
    if not password or not hashed:
        return False
    try:
        return bcrypt.checkpw(_truncate_password(password), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def get_secret_key() -> str:
    """Resolve signing key from env, or generate one once per process."""
    global _secret_cache
    if _secret_cache is not None:
        return _secret_cache
    env_key = os.environ.get("PAPERGUARD_SECRET_KEY", "").strip()
    if env_key:
        _secret_cache = env_key
        return _secret_cache
    # Dev fallback: generate, warn, cache for the lifetime of the process.
    _secret_cache = secrets.token_urlsafe(48)
    warnings.warn(
        "PAPERGUARD_SECRET_KEY not set; generated an ephemeral key. "
        "Sessions will not survive a restart and multi-worker deployments "
        "WILL break. Set PAPERGUARD_SECRET_KEY in production.",
        stacklevel=2,
    )
    return _secret_cache


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_secret_key(), salt="paperguard.session")


@dataclass(frozen=True)
class SessionPayload:
    user_id: int


def encode_session(user_id: int) -> str:
    """Produce a signed cookie value for ``user_id``."""
    return _serializer().dumps({"uid": user_id})


def decode_session(token: str) -> SessionPayload | None:
    """Verify + decode a signed cookie. Returns ``None`` on any failure."""
    if not token:
        return None
    try:
        raw = _serializer().loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except SignatureExpired:
        return None
    except BadSignature:
        return None
    if not isinstance(raw, dict):
        return None
    raw_dict = cast(dict[str, Any], raw)
    uid = raw_dict.get("uid")
    if not isinstance(uid, int):
        return None
    return SessionPayload(user_id=uid)


def reset_secret_cache_for_tests() -> None:
    """Test helper: clear the cached key so a new env var takes effect."""
    global _secret_cache
    _secret_cache = None


def generate_invite_code() -> str:
    """Cryptographically random URL-safe invite code (~32 chars)."""
    return secrets.token_urlsafe(24)
