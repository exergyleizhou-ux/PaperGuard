# Multi-Tenant Web UI (PaperGuard 2.0)

PaperGuard's Web UI ships in two layered modes:

| Mode | Surface | Activation |
|---|---|---|
| **Anonymous** (1.x default) | `/`, `/scan`, `/scan.json`, `/detectors`, `/health` | Always on |
| **Multi-tenant** (2.0+) | `/app/*` — login, projects, persistent reports, sharing, admin invites | Opt-in via env vars |

The anonymous mode is unchanged from 1.x. If you don't want user accounts,
you can deploy 2.0 exactly like 1.0 — every existing CLI command, every
existing endpoint, every existing API token still works.

This document covers the **multi-tenant** surface.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  FastAPI app (lifespan = init DB + bootstrap admin)         │
│                                                              │
│  Anonymous routes (unchanged from 1.x):                      │
│    GET  /            POST /scan            POST /scan.json   │
│    GET  /detectors   GET  /health                            │
│                                                              │
│  Multi-tenant routes (new):                                  │
│    Auth:     /app/login  /app/logout  /app/redeem/{code}     │
│    User:     /app  /app/projects  /app/projects/{id}         │
│              /app/projects/{id}/scan                         │
│              /app/reports/{id}  /app/reports/{id}/raw.json   │
│    Sharing: /app/shared                                      │
│    Admin:   /app/admin/invites                               │
└──────────────────────────────────────────────────────────────┘
        ▼
┌──────────────────────────────────────────────────────────────┐
│  SQLAlchemy async ORM                                        │
│  Tables: users, invite_codes, projects, scan_reports         │
└──────────────────────────────────────────────────────────────┘
        ▼
┌──────────────────────────────────────────────────────────────┐
│  Default: SQLite (paperguard.db)                             │
│  Production: any async-capable engine (PostgreSQL, MySQL,…) │
└──────────────────────────────────────────────────────────────┘
```

### Entities

- **User** — email, hashed password (bcrypt), role (`admin` | `member`),
  active flag. Roles are explicit: a member can never auto-promote.
- **InviteCode** — single-use redemption code an admin mints for a specific
  email. Stores the intended email so a stolen code cannot register a
  different address.
- **Project** — owned by exactly one user. Free-form name + description.
- **ScanReport** — a stored scan attached to a project. Persists the full
  `AuditReport` JSON plus denormalised severity / finding-count columns
  for cheap listing. Each report carries a **visibility**:
  - `private` — only the owning user can read
  - `org` — any signed-in user can read (project-internal sharing)
  - `public` — anyone, even unauthenticated, can read

### Auth model

Sessions are HttpOnly, `SameSite=Lax` cookies containing an
`itsdangerous`-signed `{"uid": int}` blob. The cookie name is
`paperguard_session`; default TTL is 14 days. The signing key comes from
the `PAPERGUARD_SECRET_KEY` env var.

No JWTs. No OAuth. The first-party-only design keeps the entire dependency
footprint to `sqlalchemy + aiosqlite + bcrypt + itsdangerous` plus the
existing FastAPI stack.

### Registration model

**Invite-only.** There is no `/app/register` page. Admins mint single-use
invite codes for specific email addresses; the invitee opens the
redemption link, sets a display name + password (≥ 10 chars), and is
auto-signed-in. This matches the "internal team" deployment target.

---

## Activation

Multi-tenant mode activates if either of these is set:

- `PAPERGUARD_DB_URL` — DB URL (e.g. `sqlite+aiosqlite:///paperguard.db`,
  `postgresql+asyncpg://user:pass@host/db`)
- `PAPERGUARD_MULTITENANT=1` — explicit toggle (uses default SQLite path)

If neither is set, `/app/*` routes are **not mounted** — requests to
them return 404. This is intentional: single-user installs need zero
extra config.

### Required env vars

| Var | Required? | Purpose |
|---|---|---|
| `PAPERGUARD_DB_URL` | One of these activates multi-tenant | SQLAlchemy async URL |
| `PAPERGUARD_MULTITENANT` | One of these activates multi-tenant | `1` / `true` to use default SQLite |
| `PAPERGUARD_SECRET_KEY` | Production: yes. Dev: optional. | Session-cookie signing key |
| `PAPERGUARD_ADMIN_EMAIL` | First run: yes | Bootstrap admin email |
| `PAPERGUARD_ADMIN_PASSWORD` | First run: yes | Bootstrap admin plaintext password (hashed on store) |
| `PAPERGUARD_API_TOKEN` | Optional | Token-guards legacy `/scan`, `/scan.json` |
| `PAPERGUARD_DB_ECHO` | Optional | `1` to log SQL |

`PAPERGUARD_SECRET_KEY` is the most important production setting. If
unset, an **ephemeral** key is generated and a warning is emitted —
sessions will not survive a process restart, and multi-worker deployments
will reject each other's sessions. **Always set it in production.**

### Minimal first-run

```bash
export PAPERGUARD_MULTITENANT=1
export PAPERGUARD_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
export PAPERGUARD_ADMIN_EMAIL="admin@your-org.example"
export PAPERGUARD_ADMIN_PASSWORD="$(python -c 'import secrets;print(secrets.token_urlsafe(24))')"

paperguard webui
# or: paperguard server --workers 4   # production daemon
```

On first start the lifespan handler:
1. Creates all tables (idempotent).
2. If an admin user with `PAPERGUARD_ADMIN_EMAIL` does **not** exist,
   creates one with role `admin`. If it does exist, no-op (it never
   overrides the existing password).

Sign in at `http://localhost:8000/app/login`.

### PostgreSQL

```bash
pip install "paperguard[webui]" asyncpg
export PAPERGUARD_DB_URL="postgresql+asyncpg://pg:pw@db.host:5432/paperguard"
export PAPERGUARD_SECRET_KEY="…"
export PAPERGUARD_ADMIN_EMAIL="…"
export PAPERGUARD_ADMIN_PASSWORD="…"
paperguard server --workers 4
```

---

## Invite flow

1. **Admin** signs in at `/app/login`.
2. **Admin** opens `/app/admin/invites`, fills in the invitee email and
   role, submits. The page shows a `…/app/redeem/{code}` link.
3. **Admin** sends that link to the invitee (out of band — Slack, email,
   wherever). The link is single-use.
4. **Invitee** opens the link, fills in display name + password
   (≥ 10 chars), submits. Their account is created with the role the
   admin chose, and they are auto-signed-in.
5. The invite is marked redeemed (`redeemed_at`, `redeemed_user_id`) and
   can never be used again.

### Security properties

- Invite codes are 32-char URL-safe random (≈ 144 bits of entropy).
- A redeemed invite cannot be re-used even by the same email.
- The redemption form rejects passwords < 10 chars (server-side, not
  just HTML constraint).
- Password storage: bcrypt with 12 rounds. Passwords > 72 bytes are
  truncated (bcrypt's hard limit) — clearly documented; if your password
  policy depends on length beyond 72 bytes it's already broken.

---

## Visibility semantics

When a user uploads a scan into a project they choose a visibility:

| Visibility | Who can read |
|---|---|
| `private` | Only the owning user |
| `org` | Any authenticated user |
| `public` | Anyone, even unauthenticated; listed on `/app/shared` |

Visibility is a property of each `ScanReport`, **not** the parent
`Project`. The project listing pages always require ownership; what
varies is who can read individual reports.

There is currently no UI for changing visibility after upload. The
underlying ORM supports it — that's a 2.1 follow-up.

---

## Production checklist

- [ ] `PAPERGUARD_SECRET_KEY` set to a 48+ byte random string.
- [ ] `PAPERGUARD_DB_URL` points at PostgreSQL with daily backups.
- [ ] Terminate HTTPS at a reverse proxy. Set `secure=True` on session
      cookies by editing `routes_auth.py` (a 2.1 task: surface this via
      an env var).
- [ ] Rotate the admin bootstrap password after first login.
- [ ] `PAPERGUARD_API_TOKEN` set if you keep the anonymous `/scan`
      endpoints exposed; otherwise consider running with multi-tenant
      only behind a private LAN.
- [ ] Persistent volume for the SQLite path if you stay on SQLite.

---

## Roadmap

The 2.0 cut intentionally stays minimal. Open items for 2.x:

- Password reset flow (currently admin must delete + reinvite).
- Project-level membership (more than one owner / read-share).
- Visibility editing on existing reports.
- Audit log endpoint surfaced in the UI.
- HTTPS-only cookie toggle via env.
- OAuth/SAML SSO integration.

PRs welcome.
