"""Idempotently create an admin user from environment variables on startup.

Activated by setting BOTH:

- ``PAPERGUARD_ADMIN_EMAIL`` — required admin email
- ``PAPERGUARD_ADMIN_PASSWORD`` — required admin password (plaintext;
  hashed before storage)

If either is missing, bootstrap is a no-op. If an active user with that
email already exists, bootstrap is a no-op. If a user with that email
exists but is a member, they are **not** auto-promoted — that is an
explicit admin action.

Designed for first-run bootstrap, container deployments, and ephemeral
test fixtures. Safe to call on every startup.
"""
from __future__ import annotations

import logging
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from paperguard.webui.models import User, UserRole
from paperguard.webui.security import hash_password

logger = logging.getLogger(__name__)


async def bootstrap_admin_from_env(session: AsyncSession) -> User | None:
    """Create the configured admin user if none exists. Idempotent."""
    email = os.environ.get("PAPERGUARD_ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("PAPERGUARD_ADMIN_PASSWORD", "")
    if not email or not password:
        return None

    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        # Don't change role or password automatically.
        return existing

    admin = User(
        email=email,
        display_name=email.split("@", 1)[0],
        password_hash=hash_password(password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    session.add(admin)
    await session.commit()
    await session.refresh(admin)
    logger.info("Bootstrapped admin user: %s", email)
    return admin
