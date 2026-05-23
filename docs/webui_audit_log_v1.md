# Audit log v1 — design

> **Status:** design only, no code yet. The 2.2.7 hardening plan listed
> audit log shipping as Decision 3 and mistakenly described it as
> already implemented. 2.3.0 dropped Decision 3 and called out that the
> audit log itself doesn't exist yet. This doc proposes how to build it.

## Why

PaperGuard's multi-tenant Web UI (2.0+) lets multiple users scan
documents, share reports, change visibility, redeem invites, and (for
admins) issue new invites. There is currently **no record** of who
did what when. For any deployment with even a small number of users
this is a known gap:

- An editor wants to know which reports were marked public this week.
- An admin wants to revoke an invite and see who used it.
- A compliance officer wants to confirm that user X scanned the
  manuscript on a specific date.
- An incident responder wants to know the IP that just locked out
  the login endpoint with brute-force attempts.

The 2.3.0 release added per-IP rate-limits but not audit trail —
the rate-limit hits aren't durably recorded; once the in-memory
counter window expires, the evidence is gone.

## Scope of v1

In scope:
1. New SQLAlchemy model `AuditEvent` in
   `src/paperguard/webui/models.py`. Recorded in the same DB as the
   user/project/report tables.
2. New `audit_event()` helper in
   `src/paperguard/webui/audit.py` — async function that writes one
   row per event.
3. Hooks at five specific call sites (see Event taxonomy below).
4. New env var `PAPERGUARD_AUDIT_FILE=/path/to/audit.jsonl` —
   if set, every audit-DB write also appends one JSON line to the
   file. Operators wire their own logshipper (`vector`,
   `fluent-bit`, `promtail`, syslog rsyslog imfile) to this file.
5. `GET /app/admin/audit?since=ISO8601&user=&kind=` — admin-only
   read endpoint returning the most recent N events as JSON.
6. Migration script that creates the `audit_event` table on
   existing 2.x deployments without data loss.

Out of scope (deferred to v2):
- A UI for browsing audit events (admins can `curl` the JSON
  endpoint or read the SQLite table directly for v1).
- Tamper-evidence (hash-chained log entries). Operators who need
  this ship the JSON-lines file to an append-only sink.
- Real-time alerting (e.g. "ping me when 3 admin events happen
  in 5 minutes"). Out of scope; build on top of the JSON-lines
  shipped log.
- Retention / pruning. v1 grows indefinitely. v2 adds a cron-style
  `paperguard webui prune-audit --older-than 365d`.

## Event taxonomy

Each `AuditEvent` carries:

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | Auto-increment |
| `created_at` | datetime UTC | DB default = `func.now()` |
| `kind` | enum (see below) | The event category |
| `user_id` | int FK→user.id, nullable | NULL when the actor is anonymous (failed login on unknown email) |
| `subject_id` | int, nullable | The thing acted on (report id / project id / invite id) |
| `subject_type` | str, nullable | `"report"` / `"project"` / `"invite"` / `"user"` / `"system"` |
| `ip` | str, nullable | Originating client IP as resolved by `security.client_ip()` (respects `PAPERGUARD_BEHIND_PROXY`) |
| `meta_json` | str (JSON), nullable | Event-specific payload, ≤ 4 KB |

The `kind` enum:

| Kind | When emitted | meta_json contents |
|---|---|---|
| `auth.login.success` | After session cookie issued in `routes_auth.login_submit` | `{"email": "<normalised>"}` |
| `auth.login.failure` | After 401 in same handler | `{"email": "<normalised>", "reason": "no_user" \| "inactive" \| "bad_password"}` |
| `auth.logout` | `routes_auth.logout` | `{}` |
| `auth.rate_limited` | Hit by 2.3.0 per-IP login limit | `{"endpoint": "login" \| "redeem", "retry_after_seconds": <float>}` |
| `auth.redeem.success` | New user created via invite | `{"email": "<normalised>", "invite_code": "<code>"}` |
| `auth.redeem.failure` | Same handler on failure | `{"reason": "no_invite" \| "already_redeemed" \| "weak_password" \| "email_taken"}` |
| `project.create` | `routes_app` project POST | `{"name": "<sanitized>"}` |
| `report.scan.start` | After rate-limit checks pass, before `_scan_single_file` | `{"sha256": "<hex>", "filename": "<basename>", "size_bytes": <int>}` |
| `report.scan.complete` | After `combine_evidence` returns | `{"sha256": "<hex>", "max_severity": "<NOTE/CONCERN/SUSPICIOUS/CRITICAL>", "n_findings": <int>, "cache_hit": <bool>}` |
| `report.visibility.change` | When operator edits visibility (future) | `{"from": "private", "to": "public"}` |
| `admin.invite.create` | `routes_app` admin invite POST | `{"email": "<normalised>", "role": "admin" \| "user"}` |
| `admin.invite.revoke` | Future admin endpoint | `{"invite_id": <int>}` |

This covers the five recurring "who did what" questions an operator
needs to answer with an audit trail. Adding more event kinds later is
additive and doesn't require schema changes.

## Write path

```python
# src/paperguard/webui/audit.py — proposed
from __future__ import annotations
import json, os
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from paperguard.webui.models import AuditEvent


async def audit_event(
    session: AsyncSession,
    *,
    kind: str,
    user_id: int | None = None,
    subject_id: int | None = None,
    subject_type: str | None = None,
    ip: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Persist one audit event. Best-effort: never raises into callers."""
    try:
        row = AuditEvent(
            kind=kind,
            user_id=user_id,
            subject_id=subject_id,
            subject_type=subject_type,
            ip=ip,
            meta_json=json.dumps(meta or {}, ensure_ascii=False),
            created_at=datetime.now(UTC),
        )
        session.add(row)
        await session.flush()
    except Exception:
        # Auditing must not break the user-facing operation.
        pass

    # Optional JSON-lines mirror to a file for logshippers.
    path_env = os.environ.get("PAPERGUARD_AUDIT_FILE", "").strip()
    if path_env:
        try:
            line = {
                "ts": datetime.now(UTC).isoformat(timespec="seconds"),
                "kind": kind,
                "user_id": user_id,
                "subject_id": subject_id,
                "subject_type": subject_type,
                "ip": ip,
                "meta": meta or {},
            }
            Path(path_env).parent.mkdir(parents=True, exist_ok=True)
            with Path(path_env).open("a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        except Exception:
            pass
```

Semantics:
- **Never raises.** If the DB write or the file append fails, the
  user-facing operation continues. Audit absence is a known failure
  mode and operators monitor it externally.
- **Single-flush.** Caller is expected to wrap audit + business
  logic in the same transaction so the audit row is part of the
  same commit as the side effect it records.
- **No fsync.** Cost would be unacceptable on hot endpoints. The
  JSON-lines file is shipped to durable storage by the logshipper.

## Schema migration

For existing 2.x deployments, `init_models()` already calls
`Base.metadata.create_all` on startup. Adding the new model is a
zero-config schema bump for fresh SQLite installs and for
PostgreSQL deployments where the app role has CREATE TABLE.
Existing rows in other tables are untouched.

For deployments where CREATE TABLE is restricted, ship an
Alembic-style migration script as `migrations/0001_audit_event.sql`
that operators can apply by hand.

## Read endpoint (admin only)

```
GET /app/admin/audit
  ?since=<ISO8601>           # optional, default = last 24h
  &until=<ISO8601>           # optional, default = now
  &user=<email|id>           # optional filter
  &kind=<prefix>             # optional, e.g. "auth.login"
  &limit=<int>               # default 200, max 1000
```

Returns JSON `{"events": [{...}, ...]}` ordered newest-first. Admin
auth required (existing `_verify_admin_role`). No write endpoints;
audit log is append-only by design.

## Tests

- `tests/test_webui_audit.py` (new file):
  - Login success → `auth.login.success` row exists.
  - Login wrong password → `auth.login.failure` with
    `reason="bad_password"`.
  - Login unknown email → `auth.login.failure` with `user_id=None`
    and `reason="no_user"`.
  - Rate-limited login → `auth.rate_limited`.
  - Scan completes → `report.scan.start` AND `report.scan.complete`
    in same session.
  - `PAPERGUARD_AUDIT_FILE` env causes JSON-lines append, one line
    per event, valid JSON.
  - DB write failure does not bubble into route handler.
  - Admin can GET `/app/admin/audit`; non-admin gets 403.

## Release scope

This is **2.4.0** — minor version because it adds a new SQLAlchemy
model + a new public read endpoint. Backwards-compatible — existing
deployments get the new table on startup; no events recorded before
upgrade are missing-by-design.

Estimated work:
- Model + helper + hooks: ~150 LOC
- Admin read endpoint: ~50 LOC
- Tests: ~200 LOC
- Docs update (`webui_multitenant.md`): ~30 lines

~1 day total. Migration concern for PostgreSQL deployments needs
the Alembic script (~30 min).

## Open decisions for the user

1. **Default JSON-lines file path** when env unset. **Recommend: do
   not write** to disk unless `PAPERGUARD_AUDIT_FILE` is explicitly
   set. The DB row is always written.
2. **IP storage at all vs hash-only.** Recommend **store raw IP**
   for v1 — incident response needs it. Operators worried about
   GDPR right-to-erasure can opt into hashing via
   `PAPERGUARD_AUDIT_IP_HASH=1` (add later).
3. **Retention default.** Recommend **no automatic pruning in v1**.
   v2 adds `paperguard webui prune-audit --older-than 365d`.

Reply with any of 1/2/3 different from these recommendations,
otherwise I implement as proposed when given the go-ahead.
