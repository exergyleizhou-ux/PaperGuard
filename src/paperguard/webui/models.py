"""ORM models for the multi-tenant Web UI.

Entity model:

- ``User``: owns ``Project`` rows. May be ``role='admin'`` (can mint invites)
  or ``role='member'`` (regular).
- ``InviteCode``: single-use redemption code an admin generates. Stores the
  intended new-user email so a stolen code cannot register under a
  different address.
- ``Project``: owned by a single ``User``. Holds a name + description.
- ``ScanReport``: a scan result attached to a ``Project``. The full
  ``AuditReport`` JSON is stored verbatim in ``payload_json``; a few hot
  fields (filename, sha256, finding counts) are denormalised onto the row
  for cheap listing. ``visibility`` controls who can read:

  - ``private``: only the owning user
  - ``org``: any logged-in user
  - ``public``: anyone, even unauthenticated

Cascades: deleting a ``User`` deletes their ``Project`` rows, which in turn
deletes their ``ScanReport`` rows. Invite codes are deleted by their
creating admin if the admin is deleted (but typically they outlive that
because admins are rarely removed).
"""
from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from paperguard.webui.db import Base

if TYPE_CHECKING:
    pass


def utcnow() -> datetime:
    """Timezone-aware now() — never store naive datetimes."""
    return datetime.now(UTC)


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class Visibility(enum.StrEnum):
    PRIVATE = "private"
    ORG = "org"
    PUBLIC = "public"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=16),
        nullable=False,
        default=UserRole.MEMBER,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    projects: Mapped[list[Project]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (Index("ix_users_email_lower", "email"),)


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=16),
        nullable=False,
        default=UserRole.MEMBER,
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    redeemed_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_invite_codes_code"),
        Index("ix_invite_codes_email", "email"),
    )

    @property
    def is_redeemed(self) -> bool:
        return self.redeemed_at is not None


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    owner: Mapped[User] = relationship(back_populates="projects")
    reports: Mapped[list[ScanReport]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="desc(ScanReport.created_at)",
    )

    __table_args__ = (Index("ix_projects_owner_id", "owner_id"),)


class ScanReport(Base):
    __tablename__ = "scan_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    visibility: Mapped[Visibility] = mapped_column(
        Enum(Visibility, native_enum=False, length=16),
        nullable=False,
        default=Visibility.PRIVATE,
    )
    n_findings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    severity_max: Mapped[str] = mapped_column(String(16), nullable=False, default="PASS")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="reports")

    __table_args__ = (
        Index("ix_scan_reports_project_id", "project_id"),
        Index("ix_scan_reports_visibility_created", "visibility", "created_at"),
    )
