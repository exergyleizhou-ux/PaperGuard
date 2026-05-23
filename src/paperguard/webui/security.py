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


# ---------------------------------------------------------------------------
# Proxy / IP helpers (new in 2.3.0)
# ---------------------------------------------------------------------------


def behind_proxy() -> bool:
    """Whether the app trusts upstream proxy headers + emits secure cookies.

    Controlled by the ``PAPERGUARD_BEHIND_PROXY`` env var. Set to ``1`` /
    ``true`` / ``yes`` when terminating TLS at an external reverse proxy
    (Caddy / nginx / Traefik / Cloudflare). Effects:

    1. Session cookies are minted with ``secure=True`` (HTTPS only).
    2. ``client_ip()`` trusts the first hop of ``X-Forwarded-For``.

    **Only enable this when the app actually sits behind a trusted
    proxy.** Enabling it on a directly-exposed app lets clients forge
    their own IP via ``X-Forwarded-For``, which silently breaks IP-based
    rate-limiting.
    """
    return os.environ.get("PAPERGUARD_BEHIND_PROXY", "").strip().lower() in {
        "1", "true", "yes"
    }


def client_ip(request: object) -> str:
    """Return the originating client IP.

    - Behind proxy (``PAPERGUARD_BEHIND_PROXY=1``): first hop of
      ``X-Forwarded-For`` if present, else ``request.client.host``.
    - Otherwise: ``request.client.host`` directly.

    Falls back to ``"unknown"`` if the request has no client tuple
    (e.g. unit tests that hand-build a ``Request``).
    """
    if behind_proxy():
        # Starlette's Request exposes headers as case-insensitive dict.
        headers_obj = getattr(request, "headers", None)
        xff_raw: object | None = (
            headers_obj.get("x-forwarded-for")
            if headers_obj is not None and hasattr(headers_obj, "get")
            else None
        )
        if isinstance(xff_raw, str) and xff_raw:
            # Comma-separated; first entry is the originating client.
            first = xff_raw.split(",", 1)[0].strip()
            if first:
                return first
    client = getattr(request, "client", None)
    if client is None:
        return "unknown"
    host = getattr(client, "host", None)
    if isinstance(host, str) and host:
        return host
    return "unknown"
