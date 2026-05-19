"""Async SQLAlchemy engine + session factory for the multi-tenant Web UI.

The DB layer is **opt-in**. If ``PAPERGUARD_DB_URL`` is unset, the legacy
anonymous ``/scan`` endpoints still work; only the ``/app/*`` multi-tenant
routes need the database. This keeps single-user installs zero-config.

Default URL: ``sqlite+aiosqlite:///paperguard.db`` (created in CWD on first
``init_models()`` call). Production can point at PostgreSQL by exporting
``PAPERGUARD_DB_URL=postgresql+asyncpg://...`` and installing ``asyncpg``.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

DEFAULT_DB_URL = "sqlite+aiosqlite:///paperguard.db"


class Base(DeclarativeBase):
    """SQLAlchemy 2.x declarative base for all ORM models."""


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_db_url() -> str:
    """Resolve the database URL from env or fall back to local SQLite."""
    return os.environ.get("PAPERGUARD_DB_URL", DEFAULT_DB_URL)


def get_engine() -> AsyncEngine:
    """Return (and lazily create) the process-wide async engine."""
    global _engine, _sessionmaker
    if _engine is None:
        url = get_db_url()
        # echo only if explicitly requested; keep logs quiet by default
        echo = os.environ.get("PAPERGUARD_DB_ECHO", "").lower() in {"1", "true", "yes"}
        kwargs: dict[str, Any] = {"echo": echo, "future": True}
        # SQLite needs check_same_thread=False for async use
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_async_engine(url, **kwargs)
        _sessionmaker = async_sessionmaker(
            _engine, expire_on_commit=False, class_=AsyncSession
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the session factory (creating engine on first call)."""
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def init_models() -> None:
    """Create all tables. Idempotent. Called from app startup or tests."""
    engine = get_engine()
    # Import models so they register on Base.metadata before create_all.
    from paperguard.webui import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """Close the engine. Called from app shutdown or test teardown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an ``AsyncSession``."""
    sm = get_sessionmaker()
    async with sm() as session:
        yield session
