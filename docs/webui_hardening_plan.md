# Web UI production hardening — decision document

> **Status:** awaiting decisions, no implementation yet.
> **Companion to:** [`webui_multitenant.md`](webui_multitenant.md) — the
> existing Web UI documentation. This doc proposes the 4 production
> hardening decisions that document leaves open ended.

The current PaperGuard multi-tenant Web UI (in
`src/paperguard/webui/`) is fully functional in development. It uses
SQLite by default, in-memory scan-result caching, in-memory
rate-limit counters, and assumes the operator terminates HTTPS at an
external reverse proxy. This document proposes concrete production
choices for four things the existing roadmap defers:

1. Cache backend (scan results + rate-limit counters)
2. HTTPS termination strategy
3. Audit log shipping
4. Rate-limit policy granularity

Pick one option per decision; we then implement them in a single
2.3.0 release with backwards-compatible env-var flags so dev keeps
working unchanged.

---

## Decision 1 — Cache backend

The Web UI today caches two things in-memory:
- **Scan-result cache** (5-min TTL, SHA-keyed; introduced 2.1.16).
- **Rate-limit counters** (per-IP and per-user buckets; 2.1.15).

In-memory works in single-process dev. Production with `--workers N`
gives each worker its own cache → wasted scans, weaker rate-limit
enforcement. The options are:

| Backend | Setup cost | Per-request overhead | Persists across restart | Cross-worker correct | When it makes sense |
|---|---|---|---|---|---|
| **A. Status quo (in-memory)** | none | ~10 µs | no | no | Single-worker deployments, dev, HF Space (already single-process) |
| **B. SQLite (single file)** | none — already a dep | ~1 ms | yes | yes (via WAL + cross-process locking) | Single-VM deployments, no extra service needed, modest traffic |
| **C. Redis** | new service dependency | ~0.5 ms | depends on persistence settings | yes | Multi-VM, real production, ≥ 10 req/s sustained |

**Recommendation: B (SQLite)** unless you genuinely need horizontal
scaling. SQLite gets you 90 % of Redis's correctness with zero new
service. It also matches PaperGuard's "no required external
dependencies" stance — you can `pip install paperguard` and run the
Web UI; you don't have to also run `docker-compose up redis`.
Upgrading from B → C later is a 1-line env-var change at the cache
layer (`PAPERGUARD_CACHE_BACKEND=redis`).

**Implementation sketch for B:** Add `src/paperguard/webui/cache.py`
with a `Cache` protocol (`get`, `set`, `delete`, `incr`,
`expire_at`) and two implementations: `MemoryCache` (default;
current behavior) and `SQLiteCache` (writes to
`$PAPERGUARD_CACHE_DB` or the same DB as auth, configurable). Swap
the in-memory dicts in `scan_cache.py` and `ratelimit.py` for the
`Cache` instance. Tests: add a `@pytest.mark.parametrize` over both
backends so we never regress.

**Decision — pick one:** A / **B** / C

---

## Decision 2 — HTTPS termination

| Strategy | Setup cost | Operator burden | Cert renewal | When it makes sense |
|---|---|---|---|---|
| **A. External reverse proxy** (Caddy / nginx / Traefik / Cloudflare) | operator runs proxy | medium | proxy handles ACME | All real deployments |
| **B. Built-in TLS** (Hypercorn `--certfile`/`--keyfile`) | self-managed certs | high — manual ACME | operator script | Bare-metal "no proxy" deployments only |

**Recommendation: A (external proxy)** — same as the existing
roadmap. Reasoning: every real deployment ends up wanting a proxy
anyway (HTTP/2, gzip, static-file caching, IP allowlists), so
shipping a built-in TLS option is misleading without those features
and we'd have to document "use a real proxy in production" right
next to it. Better to commit fully.

**Implementation work for A:** Just add an env-var
`PAPERGUARD_BEHIND_PROXY=1` that sets `secure=True` on session
cookies + reads `X-Forwarded-For` / `X-Forwarded-Proto` correctly
(currently the cookie's `secure` flag is hardcoded `False` in
`routes_auth.py`, which the existing webui_multitenant.md flags as
a 2.1 follow-up). Also document the proxy headers in
webui_multitenant.md "Production checklist" section.

**Decision — pick one:** **A** / B

---

## Decision 3 — Audit log shipping

The Web UI today writes audit events to a local SQLite table
(`audit_log` in the auth DB) — every login, scan submission,
report viewed, settings change. The table is queryable via the
ORM but there's no shipping or external-log integration.

| Strategy | Setup cost | Operator skill required | Tamper-evidence | When it makes sense |
|---|---|---|---|---|
| **A. Status quo (local SQLite table)** | none | none | low (DB is editable) | Dev, single-VM trusted-operator deployments |
| **B. Append to a local log file** with JSON-lines format | none | log-rotation setup | low | Operators who run their own logshipper (`vector`, `fluent-bit`) |
| **C. syslog handler** | configure syslog target | medium | medium (rsyslog tamper-evident option) | Operators with existing syslog/SIEM (ELK, Splunk) |
| **D. OTLP/OpenTelemetry exporter** | configure OTel collector | high | high (with tamper-evident OTel backend) | Cloud-native operators with Datadog/Honeycomb/Tempo |

**Recommendation: A + B (status quo + opt-in JSON-lines export)** —
A stays default so dev is unchanged. Add B as
`PAPERGUARD_AUDIT_FILE=/var/log/paperguard/audit.jsonl` env var; if
set, every audit DB write also appends one JSON line. Operators
who want C or D wire their logshipper to the JSON file (this is
already the standard pattern for `vector`, `fluent-bit`,
`promtail`).

This keeps PaperGuard out of the "which logging framework do you
use?" trap and gives operators a stable JSON-lines contract to
build on.

**Implementation work:** ~30 lines in
`src/paperguard/webui/audit.py` (which already exists; just add a
file-sink option to the existing `write_event()` function).

**Decision — pick one:** **A + B** / A + C / A + D / A only

---

## Decision 4 — Rate-limit policy

Current state (2.1.15): per-IP token bucket on `/scan`, 10 requests
per minute, in-memory. No per-user limit. No per-endpoint
granularity (uploading a 25 MB PDF and hitting `/api/status` count
the same).

| Policy | Implementation cost | Operator tunability | When it makes sense |
|---|---|---|---|
| **A. Status quo** (per-IP, single global rate) | none | env-var rate only | Public unauthenticated demos |
| **B. Per-IP + per-user** (separate buckets) | low | per-bucket rate via env | Mixed public + logged-in deployments |
| **C. Per-endpoint cost** (scan = 10 credits, status = 1 credit) | medium | YAML config file | Heavily-loaded operators wanting fairness |

**Recommendation: B (per-IP + per-user)** — moves us from "DDoS
basics" to "multi-tenant SaaS basics" without going overboard. C is
nice but YAML config files are a maintenance burden and the
user-facing benefit is small unless someone's actually getting
DDoSed.

**Implementation work:** ~40 lines in `ratelimit.py`. Two buckets
keyed on `request.client.host` and `request.session.user_id`
respectively; reject if either is over its limit. Env vars
`PAPERGUARD_RATE_LIMIT_IP=10/minute` and
`PAPERGUARD_RATE_LIMIT_USER=60/minute` (per-user rate higher
because they've authed).

**Decision — pick one:** A / **B** / C

---

## Combined release plan

If all four recommendations are accepted, this becomes **2.3.0** with
the following scope:

1. New module `src/paperguard/webui/cache.py` — `Cache` protocol +
   `MemoryCache` (default) + `SQLiteCache` (opt-in via
   `PAPERGUARD_CACHE_BACKEND=sqlite`).
2. Swap `scan_cache.py` + `ratelimit.py` to use the `Cache`
   protocol instead of module-level dicts.
3. New env-var `PAPERGUARD_BEHIND_PROXY=1` → secure-cookie + proxy
   headers in `routes_auth.py`.
4. New env-var `PAPERGUARD_AUDIT_FILE=/path` → JSON-lines audit
   sink in `audit.py`.
5. New env-vars `PAPERGUARD_RATE_LIMIT_IP` and
   `PAPERGUARD_RATE_LIMIT_USER` → per-bucket rate-limit policy.
6. Tests: parametrized backend tests, audit-sink integration test,
   rate-limit per-bucket test.
7. Docs: update `webui_multitenant.md` Production checklist
   (existing TODOs become "done"), add `webui_hardening.md` as the
   reference (this doc, restructured into reference form).

Estimated work: **~1 day implementation + 2 hours tests + 1 hour
docs**. Everything backwards-compatible — existing dev workflows
keep working without setting any new env vars.

---

## How to respond

Reply with the four picks in order, e.g.:

> Decisions: 1=B, 2=A, 3=A+B, 4=B → go for 2.3.0

…and I'll implement. If you want to change any recommendation,
just say which option letter instead.
