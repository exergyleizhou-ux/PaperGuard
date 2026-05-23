"""Audit-log v1 tests (2.5.0).

Verifies that every documented hook actually writes an ``AuditEvent``
row, that the JSON-lines mirror works when the env var is set, that
the admin /app/admin/audit endpoint filters correctly, and that
non-admins cannot read the log.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from paperguard.webui import db as webui_db
from paperguard.webui import security as webui_security
from paperguard.webui.app import create_app
from paperguard.webui.models import AuditEvent


@pytest.fixture
def mt_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    db_file = tmp_path / f"pg_{uuid.uuid4().hex}.db"
    monkeypatch.setenv("PAPERGUARD_DB_URL", f"sqlite+aiosqlite:///{db_file}")
    monkeypatch.setenv(
        "PAPERGUARD_SECRET_KEY",
        "test-secret-key-fixed-for-determinism-0123456789abcdef",
    )
    monkeypatch.setenv("PAPERGUARD_MULTITENANT", "1")
    asyncio.new_event_loop().run_until_complete(webui_db.dispose_engine())
    webui_security.reset_secret_cache_for_tests()
    yield db_file
    asyncio.new_event_loop().run_until_complete(webui_db.dispose_engine())
    webui_security.reset_secret_cache_for_tests()


@pytest.fixture
def admin_env(mt_env: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PAPERGUARD_ADMIN_EMAIL", "admin@example.test")
    monkeypatch.setenv("PAPERGUARD_ADMIN_PASSWORD", "adminpassword-123!")
    return mt_env


@pytest.fixture
def client(admin_env: Path) -> Iterator[TestClient]:
    from paperguard.webui.ratelimit import reset_rate_limiter_for_tests

    reset_rate_limiter_for_tests()
    with TestClient(create_app()) as c:
        yield c


def _login(client: TestClient, email: str, password: str) -> None:
    client.post(
        "/app/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


async def _audit_rows(kind_prefix: str | None = None) -> list[AuditEvent]:
    """Helper to read rows out of the test DB."""
    sm = webui_db.get_sessionmaker()
    async with sm() as session:
        assert isinstance(session, AsyncSession)
        stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc())
        if kind_prefix is not None:
            stmt = stmt.where(AuditEvent.kind.startswith(kind_prefix))
        return list((await session.scalars(stmt)).all())


def _audit_rows_sync(kind_prefix: str | None = None) -> list[AuditEvent]:
    return asyncio.new_event_loop().run_until_complete(_audit_rows(kind_prefix))


def test_login_success_emits_audit_event(client: TestClient) -> None:
    r = client.post(
        "/app/login",
        data={"email": "admin@example.test", "password": "adminpassword-123!"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    rows = _audit_rows_sync("auth.login.success")
    assert len(rows) == 1
    f = rows[0]
    assert f.user_id is not None
    assert f.ip == "testclient"
    meta = json.loads(f.meta_json)
    assert meta["email"] == "admin@example.test"


def test_login_failure_emits_no_user_audit(client: TestClient) -> None:
    client.post(
        "/app/login",
        data={"email": "ghost@example.test", "password": "whatever123"},
        follow_redirects=False,
    )
    rows = _audit_rows_sync("auth.login.failure")
    assert len(rows) == 1
    f = rows[0]
    assert f.user_id is None
    assert json.loads(f.meta_json)["reason"] == "no_user"


def test_login_failure_emits_bad_password_audit(client: TestClient) -> None:
    client.post(
        "/app/login",
        data={"email": "admin@example.test", "password": "wrong-pw"},
        follow_redirects=False,
    )
    rows = _audit_rows_sync("auth.login.failure")
    assert len(rows) == 1
    f = rows[0]
    # user_id present because the email matched a real user.
    assert f.user_id is not None
    assert json.loads(f.meta_json)["reason"] == "bad_password"


def test_logout_emits_audit_event(client: TestClient) -> None:
    _login(client, "admin@example.test", "adminpassword-123!")
    r = client.post("/app/logout", follow_redirects=False)
    assert r.status_code in (302, 303)
    rows = _audit_rows_sync("auth.logout")
    assert len(rows) == 1
    assert rows[0].user_id is not None


def test_login_rate_limited_emits_audit(client: TestClient) -> None:
    # 11th attempt hits the 2.3.0 per-IP limit.
    for i in range(10):
        client.post(
            "/app/login",
            data={"email": "admin@example.test", "password": f"wrong-{i}"},
            follow_redirects=False,
        )
    r = client.post(
        "/app/login",
        data={"email": "admin@example.test", "password": "still-wrong"},
        follow_redirects=False,
    )
    assert r.status_code == 429
    rl_rows = _audit_rows_sync("auth.login.rate_limited")
    assert len(rl_rows) == 1
    # The 10 wrong-password attempts also each emitted login.failure.
    fail_rows = _audit_rows_sync("auth.login.failure")
    assert len(fail_rows) == 10


def test_project_create_emits_audit(client: TestClient) -> None:
    _login(client, "admin@example.test", "adminpassword-123!")
    r = client.post(
        "/app/projects",
        data={"name": "test-project", "description": "demo"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    rows = _audit_rows_sync("project.create")
    assert len(rows) == 1
    f = rows[0]
    assert f.subject_type == "project"
    assert f.subject_id is not None
    assert json.loads(f.meta_json)["name"] == "test-project"


def test_admin_invite_create_emits_audit(client: TestClient) -> None:
    _login(client, "admin@example.test", "adminpassword-123!")
    r = client.post(
        "/app/admin/invites",
        data={"email": "newbie@example.test", "role": "member"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    rows = _audit_rows_sync("admin.invite.create")
    assert len(rows) == 1
    f = rows[0]
    assert f.subject_type == "invite"
    meta = json.loads(f.meta_json)
    assert meta["email"] == "newbie@example.test"
    assert meta["role"] == "member"


def test_audit_endpoint_admin_only(client: TestClient) -> None:
    """Non-admins must NOT be able to read /app/admin/audit."""
    # Unauthenticated request.
    r_anon = client.get("/app/admin/audit", follow_redirects=False)
    # Auth dependency redirects unauthenticated callers to /app/login.
    assert r_anon.status_code in (302, 303, 401, 403)


def test_audit_endpoint_admin_can_read(client: TestClient) -> None:
    _login(client, "admin@example.test", "adminpassword-123!")
    # generate a couple of events
    client.post(
        "/app/projects",
        data={"name": "for-audit-test"},
        follow_redirects=False,
    )
    r = client.get("/app/admin/audit?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert "events" in body
    assert body["count"] >= 1
    kinds = {e["kind"] for e in body["events"]}
    assert "project.create" in kinds or "auth.login.success" in kinds


def test_audit_endpoint_kind_filter(client: TestClient) -> None:
    _login(client, "admin@example.test", "adminpassword-123!")
    r = client.get("/app/admin/audit?kind=auth.login&limit=10")
    assert r.status_code == 200
    for ev in r.json()["events"]:
        assert ev["kind"].startswith("auth.login")


def test_audit_file_mirror_writes_jsonl(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PAPERGUARD_AUDIT_FILE causes append-style JSON-lines mirror."""
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("PAPERGUARD_AUDIT_FILE", str(audit_path))
    client.post(
        "/app/login",
        data={"email": "admin@example.test", "password": "adminpassword-123!"},
        follow_redirects=False,
    )
    assert audit_path.exists(), f"{audit_path} not created"
    lines = [
        line for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert lines, "JSON-lines audit file is empty"
    parsed = [json.loads(line) for line in lines]
    kinds = {p["kind"] for p in parsed}
    assert "auth.login.success" in kinds
    # Every line must be valid JSON with stable keys.
    for p in parsed:
        for key in ("ts", "kind", "ip", "meta"):
            assert key in p, f"missing key {key}: {p}"


def test_audit_event_swallows_db_failures(admin_env: Path) -> None:
    """audit_event() must never raise into the caller on DB failure.

    Direct unit test (no HTTP) — calls audit_event with a session
    rigged to raise on commit, verifies the helper catches the
    exception and never propagates it.
    """
    from paperguard.webui.audit import audit_event

    async def _run() -> None:
        sm = webui_db.get_sessionmaker()
        async with sm() as session:
            # Patch session.commit to raise.
            original_commit = session.commit

            async def _bad_commit() -> None:
                raise RuntimeError("simulated commit failure")

            session.commit = _bad_commit  # type: ignore[assignment]
            try:
                # If audit_event lets exceptions through, this await
                # raises and the test fails.
                await audit_event(
                    session,
                    kind="auth.login.success",
                    user_id=1,
                    ip="127.0.0.1",
                    meta={"email": "x@example.test"},
                )
            finally:
                session.commit = original_commit  # type: ignore[assignment]

    # If the helper raises, this line never runs — pytest reports
    # the exception and the test fails.
    asyncio.new_event_loop().run_until_complete(_run())
