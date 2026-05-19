"""Multi-tenant Web UI tests.

Each test gets its own isolated in-memory SQLite database via a unique
``PAPERGUARD_DB_URL`` (different file per test, deleted in teardown) — this
keeps SQLAlchemy's module-level engine cache from leaking state across
tests while still exercising real disk I/O.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from paperguard.webui import db as webui_db
from paperguard.webui import security as webui_security
from paperguard.webui.app import create_app


@pytest.fixture
def mt_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Per-test isolated DB + secret key + admin bootstrap env."""
    db_file = tmp_path / f"pg_{uuid.uuid4().hex}.db"
    monkeypatch.setenv("PAPERGUARD_DB_URL", f"sqlite+aiosqlite:///{db_file}")
    monkeypatch.setenv(
        "PAPERGUARD_SECRET_KEY",
        "test-secret-key-fixed-for-determinism-0123456789abcdef",
    )
    monkeypatch.setenv("PAPERGUARD_MULTITENANT", "1")
    # Force engine recreation against the new URL.
    asyncio.get_event_loop_policy()
    asyncio.new_event_loop().run_until_complete(webui_db.dispose_engine())
    webui_security.reset_secret_cache_for_tests()
    yield db_file
    # Teardown — dispose engine so the next test starts fresh.
    asyncio.new_event_loop().run_until_complete(webui_db.dispose_engine())
    webui_security.reset_secret_cache_for_tests()


@pytest.fixture
def admin_env(mt_env: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PAPERGUARD_ADMIN_EMAIL", "admin@example.test")
    monkeypatch.setenv("PAPERGUARD_ADMIN_PASSWORD", "adminpassword-123!")
    return mt_env


@pytest.fixture
def client(admin_env: Path) -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


def _login(client: TestClient, email: str, password: str) -> None:
    r = client.post(
        "/app/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert r.status_code in (303, 302), r.text
    assert "paperguard_session" in client.cookies


def _create_invite(client: TestClient, email: str, role: str = "member") -> str:
    r = client.post(
        "/app/admin/invites",
        data={"email": email, "role": role},
        follow_redirects=False,
    )
    assert r.status_code in (303, 302), r.text
    # Get the invite code from the listing page.
    listing = client.get("/app/admin/invites")
    assert listing.status_code == 200
    # Look for a /app/redeem/CODE link matching this email
    import re

    matches = re.findall(r"/app/redeem/([A-Za-z0-9_\-]+)", listing.text)
    assert matches, f"No invite link found in listing:\n{listing.text[:500]}"
    return matches[0]


# --------------------------------------------------------------------------
# Bootstrap + auth
# --------------------------------------------------------------------------


def test_admin_bootstrapped_from_env(client: TestClient) -> None:
    """Lifespan should have created the admin user."""
    r = client.post(
        "/app/login",
        data={"email": "admin@example.test", "password": "adminpassword-123!"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 302)


def test_login_rejects_bad_password(client: TestClient) -> None:
    r = client.post(
        "/app/login",
        data={"email": "admin@example.test", "password": "wrong"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert "Invalid email or password" in r.text


def test_login_rejects_unknown_email(client: TestClient) -> None:
    r = client.post(
        "/app/login",
        data={"email": "nobody@example.test", "password": "whatever123"},
        follow_redirects=False,
    )
    assert r.status_code == 401


def test_logout_clears_cookie(client: TestClient) -> None:
    _login(client, "admin@example.test", "adminpassword-123!")
    r = client.post("/app/logout", follow_redirects=False)
    assert r.status_code in (303, 302)
    # The Set-Cookie should be an expiry instruction.
    set_cookie = r.headers.get("set-cookie", "")
    assert "paperguard_session" in set_cookie


def test_index_redirects_anonymous_to_login(client: TestClient) -> None:
    # /app → /app/ (FastAPI prefix redirect) → /app/login (auth redirect)
    r = client.get("/app/", follow_redirects=False)
    assert r.status_code in (303, 302, 307)
    assert "/app/login" in r.headers.get("location", "")


# --------------------------------------------------------------------------
# Invite flow
# --------------------------------------------------------------------------


def test_admin_can_mint_and_member_can_redeem(client: TestClient) -> None:
    _login(client, "admin@example.test", "adminpassword-123!")
    code = _create_invite(client, "new-member@example.test")
    # Anonymous client redeems
    fresh = TestClient(client.app)
    r = fresh.get(f"/app/redeem/{code}")
    assert r.status_code == 200
    assert "new-member@example.test" in r.text
    r = fresh.post(
        f"/app/redeem/{code}",
        data={"display_name": "Newbie", "password": "supersecret123"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 302), r.text
    # New user can now log in
    r = fresh.post(
        "/app/login",
        data={"email": "new-member@example.test", "password": "supersecret123"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 302)


def test_non_admin_cannot_mint_invites(client: TestClient) -> None:
    # Bootstrap a member by minting + redeeming an invite, then log in as them.
    _login(client, "admin@example.test", "adminpassword-123!")
    code = _create_invite(client, "member@example.test")
    member = TestClient(client.app)
    member.post(
        f"/app/redeem/{code}",
        data={"display_name": "Member", "password": "memberpassword-123"},
        follow_redirects=False,
    )
    # Member already logged in via redemption. Try to access admin route.
    r = member.get("/app/admin/invites")
    assert r.status_code == 403
    r = member.post(
        "/app/admin/invites",
        data={"email": "x@example.test", "role": "member"},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_invite_single_use(client: TestClient) -> None:
    _login(client, "admin@example.test", "adminpassword-123!")
    code = _create_invite(client, "once@example.test")
    fresh = TestClient(client.app)
    r = fresh.post(
        f"/app/redeem/{code}",
        data={"display_name": "Once", "password": "oncepassword12"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 302)
    # Re-attempt the same code
    again = TestClient(client.app)
    r = again.get(f"/app/redeem/{code}")
    assert "already been redeemed" in r.text or "Invite already used" in r.text


def test_redeem_rejects_weak_password(client: TestClient) -> None:
    _login(client, "admin@example.test", "adminpassword-123!")
    code = _create_invite(client, "weak@example.test")
    fresh = TestClient(client.app)
    r = fresh.post(
        f"/app/redeem/{code}",
        data={"display_name": "Weak", "password": "short"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "at least 10 characters" in r.text


# --------------------------------------------------------------------------
# Project + report visibility
# --------------------------------------------------------------------------


def _bootstrap_member(client: TestClient, email: str, password: str) -> TestClient:
    code = _create_invite(client, email)
    fresh = TestClient(client.app)
    fresh.post(
        f"/app/redeem/{code}",
        data={"display_name": email.split("@")[0], "password": password},
        follow_redirects=False,
    )
    return fresh


def test_create_project_and_list(client: TestClient) -> None:
    _login(client, "admin@example.test", "adminpassword-123!")
    r = client.post(
        "/app/projects",
        data={"name": "My Trial Reanalysis", "description": "Pilot"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 302)
    loc = r.headers["location"]
    assert loc.startswith("/app/projects/")
    r = client.get("/app")
    assert "My Trial Reanalysis" in r.text


def test_project_owner_isolation(client: TestClient) -> None:
    """Alice's project must not be visible to Bob."""
    _login(client, "admin@example.test", "adminpassword-123!")
    alice = _bootstrap_member(client, "alice@example.test", "alicepassword123")
    r = alice.post(
        "/app/projects",
        data={"name": "Alice Project", "description": ""},
        follow_redirects=False,
    )
    alice_project_url = r.headers["location"]
    bob = _bootstrap_member(client, "bob@example.test", "bobpassword12345")
    r = bob.get(alice_project_url)
    assert r.status_code == 404


def test_scan_into_project_private_visibility(
    client: TestClient, fixtures_dir: Path
) -> None:
    _login(client, "admin@example.test", "adminpassword-123!")
    r = client.post(
        "/app/projects",
        data={"name": "Scans", "description": ""},
        follow_redirects=False,
    )
    project_url = r.headers["location"]
    csv = fixtures_dir / "genuine_random.csv"
    with csv.open("rb") as f:
        r = client.post(
            f"{project_url}/scan",
            files={"file": (csv.name, f, "text/csv")},
            data={"visibility": "private"},
            follow_redirects=False,
        )
    assert r.status_code in (303, 302), r.text
    report_url = r.headers["location"]
    assert report_url.startswith("/app/reports/")
    # Anonymous cannot read private report
    anon = TestClient(client.app)
    r = anon.get(report_url)
    assert r.status_code == 401


def test_public_report_readable_anonymously(
    client: TestClient, fixtures_dir: Path
) -> None:
    _login(client, "admin@example.test", "adminpassword-123!")
    r = client.post(
        "/app/projects",
        data={"name": "PubProj", "description": ""},
        follow_redirects=False,
    )
    project_url = r.headers["location"]
    csv = fixtures_dir / "genuine_random.csv"
    with csv.open("rb") as f:
        r = client.post(
            f"{project_url}/scan",
            files={"file": (csv.name, f, "text/csv")},
            data={"visibility": "public"},
            follow_redirects=False,
        )
    report_url = r.headers["location"]
    anon = TestClient(client.app)
    r = anon.get(report_url)
    assert r.status_code == 200
    assert csv.name in r.text
    # Listed under /app/shared
    r = anon.get("/app/shared")
    assert r.status_code == 200
    assert csv.name in r.text


def test_org_report_requires_login(client: TestClient, fixtures_dir: Path) -> None:
    _login(client, "admin@example.test", "adminpassword-123!")
    r = client.post(
        "/app/projects",
        data={"name": "OrgProj", "description": ""},
        follow_redirects=False,
    )
    project_url = r.headers["location"]
    csv = fixtures_dir / "genuine_random.csv"
    with csv.open("rb") as f:
        r = client.post(
            f"{project_url}/scan",
            files={"file": (csv.name, f, "text/csv")},
            data={"visibility": "org"},
            follow_redirects=False,
        )
    report_url = r.headers["location"]
    # Anonymous: 401
    anon = TestClient(client.app)
    r = anon.get(report_url)
    assert r.status_code == 401
    # Another logged-in user can read it
    bob = _bootstrap_member(client, "orguser@example.test", "orgpassword12345")
    r = bob.get(report_url)
    assert r.status_code == 200


def test_raw_json_endpoint_returns_payload(
    client: TestClient, fixtures_dir: Path
) -> None:
    _login(client, "admin@example.test", "adminpassword-123!")
    r = client.post(
        "/app/projects",
        data={"name": "JsonProj", "description": ""},
        follow_redirects=False,
    )
    project_url = r.headers["location"]
    csv = fixtures_dir / "genuine_random.csv"
    with csv.open("rb") as f:
        r = client.post(
            f"{project_url}/scan",
            files={"file": (csv.name, f, "text/csv")},
            data={"visibility": "public"},
            follow_redirects=False,
        )
    report_url = r.headers["location"]
    anon = TestClient(client.app)
    r = anon.get(f"{report_url}/raw.json")
    assert r.status_code == 200
    payload = r.json()
    assert "findings" in payload or "all_findings" in payload


def test_scan_rejects_unsupported_type(client: TestClient, tmp_path: Path) -> None:
    _login(client, "admin@example.test", "adminpassword-123!")
    r = client.post(
        "/app/projects", data={"name": "Reject"}, follow_redirects=False
    )
    project_url = r.headers["location"]
    bad = tmp_path / "evil.exe"
    bad.write_bytes(b"\x00\x01\x02")
    with bad.open("rb") as f:
        r = client.post(
            f"{project_url}/scan",
            files={"file": (bad.name, f, "application/octet-stream")},
            data={"visibility": "private"},
            follow_redirects=False,
        )
    assert r.status_code == 415


# --------------------------------------------------------------------------
# Legacy anonymous /scan still works
# --------------------------------------------------------------------------


def test_anonymous_scan_still_works(client: TestClient, fixtures_dir: Path) -> None:
    """The 1.x /scan endpoint must remain unaffected by multi-tenant mode."""
    csv = fixtures_dir / "genuine_random.csv"
    with csv.open("rb") as f:
        r = client.post(
            "/scan",
            files={"file": (csv.name, f, "text/csv")},
            data={"lang": "en"},
        )
    assert r.status_code == 200


def test_anonymous_index_still_renders(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "<form" in r.text


def test_health_endpoint(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# --------------------------------------------------------------------------
# Disabled multi-tenant
# --------------------------------------------------------------------------


def test_multitenant_disabled_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without env vars, /app/login should 404."""
    monkeypatch.delenv("PAPERGUARD_DB_URL", raising=False)
    monkeypatch.delenv("PAPERGUARD_MULTITENANT", raising=False)
    monkeypatch.delenv("PAPERGUARD_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("PAPERGUARD_ADMIN_PASSWORD", raising=False)
    with TestClient(create_app()) as c:
        r = c.get("/app/login")
        assert r.status_code == 404
        # Legacy endpoints still up
        r = c.get("/health")
        assert r.status_code == 200


# --------------------------------------------------------------------------
# Direct unit-level tests for security helpers
# --------------------------------------------------------------------------


def test_password_hash_roundtrip() -> None:
    from paperguard.webui.security import hash_password, verify_password

    h = hash_password("hello world")
    assert verify_password("hello world", h)
    assert not verify_password("hello world!", h)


def test_password_truncates_at_72_bytes() -> None:
    from paperguard.webui.security import hash_password, verify_password

    pw = "a" * 100
    h = hash_password(pw)
    # Truncated equivalents should still verify
    assert verify_password("a" * 72, h)


def test_session_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPERGUARD_SECRET_KEY", "deterministic-key-for-test-1234")
    webui_security.reset_secret_cache_for_tests()
    from paperguard.webui.security import decode_session, encode_session

    tok = encode_session(42)
    payload = decode_session(tok)
    assert payload is not None
    assert payload.user_id == 42


def test_session_rejects_tampered_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPERGUARD_SECRET_KEY", "deterministic-key-for-test-1234")
    webui_security.reset_secret_cache_for_tests()
    from paperguard.webui.security import decode_session, encode_session

    tok = encode_session(7)
    # Flip a character in the signature portion (after the last dot)
    head, _, _sig = tok.rpartition(".")
    bad = f"{head}.AAAAAAAAAAAAAAAAAAAAAAAAA"
    assert decode_session(bad) is None
