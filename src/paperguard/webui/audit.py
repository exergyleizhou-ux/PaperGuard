"""Append-only audit log for the multi-tenant Web UI (2.5.0+).

Public surface
--------------
Single helper coroutine:

    await audit_event(
        session,
        kind="auth.login.success",
        user_id=42,
        ip="203.0.113.5",
        meta={"email": "alice@example.test"},
    )

Best-effort write semantics
---------------------------
``audit_event`` **never raises into the caller**. If the DB insert
fails (locked DB, schema mismatch, disk full, ...) the user-facing
operation continues unaffected. The audit absence is then a
known failure mode and operators monitor it externally via the
``PAPERGUARD_AUDIT_FILE`` JSON-lines mirror (see below).

Optional JSON-lines mirror
--------------------------
If the env var ``PAPERGUARD_AUDIT_FILE=/path/to/audit.jsonl`` is
set, every audit-DB write also appends one JSON line to the file.
Operators wire their own logshipper (`vector`, `fluent-bit`,
`promtail`, syslog rsyslog imfile) to this file. The file format
is one JSON object per line, with stable fields:

    {"ts": "2026-05-23T07:00:00+00:00",
     "kind": "auth.login.success",
     "user_id": 42,
     "subject_id": null,
     "subject_type": null,
     "ip": "203.0.113.5",
     "meta": {"email": "alice@example.test"}}

Path resolution semantics: if the directory does not exist it is
created (best-effort). If the write fails, the audit DB write
already succeeded — the file mirror is documentation-grade, not
the durable record.

Event taxonomy (v1)
-------------------
The kinds used by the existing hook sites are:

- ``auth.login.success`` / ``auth.login.failure`` /
  ``auth.login.rate_limited``
- ``auth.logout``
- ``auth.redeem.success`` / ``auth.redeem.failure`` /
  ``auth.redeem.rate_limited``
- ``report.scan.start`` / ``report.scan.complete`` /
  ``report.scan.rate_limited``
- ``project.create``
- ``admin.invite.create``

Adding more kinds is additive — both the DB schema (``kind`` is a
free string) and this helper accept any string. The taxonomy is
just convention.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from paperguard.webui.models import AuditEvent

logger = logging.getLogger(__name__)


def _audit_file_path() -> Path | None:
    """Return the configured JSON-lines audit file path, or ``None``."""
    p = os.environ.get("PAPERGUARD_AUDIT_FILE", "").strip()
    return Path(p) if p else None


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
    """Persist one audit event. Best-effort: never raises."""
    now = datetime.now(UTC)
    meta_payload = meta or {}

    # 1. DB write (best-effort). We flush AND commit because some
    # request paths (auth, rate-limited) never call session.commit()
    # themselves — the audit row would otherwise be discarded when
    # the DBSession dependency context manager exits without commit.
    # Committing here also has the side-effect of persisting any
    # earlier business writes made on the same session within this
    # request, which is the intended behaviour: audit rows and the
    # business action they describe land atomically.
    try:
        row = AuditEvent(
            created_at=now,
            kind=kind,
            user_id=user_id,
            subject_id=subject_id,
            subject_type=subject_type,
            ip=ip,
            meta_json=json.dumps(meta_payload, ensure_ascii=False),
        )
        session.add(row)
        await session.commit()
    except Exception as e:  # noqa: BLE001
        # Audit must never break the user-facing operation. Log + move on.
        logger.warning(
            "audit_event DB write failed (kind=%s, user_id=%s): %s",
            kind, user_id, e,
        )
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass

    # 2. JSON-lines mirror (best-effort, opt-in via env var).
    path = _audit_file_path()
    if path is not None:
        try:
            line = {
                "ts": now.isoformat(timespec="seconds"),
                "kind": kind,
                "user_id": user_id,
                "subject_id": subject_id,
                "subject_type": subject_type,
                "ip": ip,
                "meta": meta_payload,
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "audit_event file mirror failed (path=%s, kind=%s): %s",
                path, kind, e,
            )
