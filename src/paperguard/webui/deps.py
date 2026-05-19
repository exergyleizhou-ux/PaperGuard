"""FastAPI dependencies for the multi-tenant Web UI."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from paperguard.webui.db import get_sessionmaker
from paperguard.webui.models import User, UserRole
from paperguard.webui.security import decode_session


async def db_session() -> AsyncIterator[AsyncSession]:
    """Yield an ``AsyncSession`` bound to the configured engine."""
    sm = get_sessionmaker()
    async with sm() as session:
        yield session


DBSession = Annotated[AsyncSession, Depends(db_session)]


async def current_user_optional(
    session: DBSession,
    paperguard_session: Annotated[str | None, Cookie()] = None,
) -> User | None:
    """Return the current user or ``None`` if the visitor is anonymous."""
    if not paperguard_session:
        return None
    payload = decode_session(paperguard_session)
    if payload is None:
        return None
    user = await session.get(User, payload.user_id)
    if user is None or not user.is_active:
        return None
    return user


CurrentUserOptional = Annotated[User | None, Depends(current_user_optional)]


async def current_user(user: CurrentUserOptional) -> User:
    """Require an authenticated active user."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def require_admin(user: CurrentUser) -> User:
    """Require admin role on top of authentication."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user


CurrentAdmin = Annotated[User, Depends(require_admin)]
