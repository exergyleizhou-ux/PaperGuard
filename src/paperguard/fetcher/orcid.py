"""ORCID public API — author disambiguation helper.

Public API (no auth token). Rate limit: ~1 req/sec.
https://info.orcid.org/documentation/api-tutorials/
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

_BASE = "https://pub.orcid.org/v3.0"
_HEADERS = {"Accept": "application/json"}
_MAX_CANDIDATES = 10


@dataclass(frozen=True)
class OrcidCandidate:
    orcid_id: str
    name: str
    affiliations: list[str] = field(default_factory=list)
    works_count: int = 0


def _build_query(name: str, affiliation: str | None) -> str:
    parts = name.strip().rsplit(maxsplit=1)
    if len(parts) == 2:
        first, last = parts[0], parts[1]
    else:
        first, last = "", parts[0]

    clauses: list[str] = []
    if last:
        clauses.append(f"family-name:{last}")
    if first:
        clauses.append(f"given-names:{first}")
    if affiliation:
        clauses.append(f"affiliation-org-name:{affiliation}")
    return " AND ".join(clauses)


async def disambiguate_author(
    name: str, affiliation: str | None = None
) -> list[OrcidCandidate]:
    query = _build_query(name, affiliation)
    if not query:
        return []

    async with httpx.AsyncClient(timeout=30.0, headers=_HEADERS) as client:
        resp = await client.get(
            f"{_BASE}/expanded-search/",
            params={"q": query, "rows": str(_MAX_CANDIDATES)},
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        results: list[dict[str, Any]] = data.get("expanded-result") or []
        if not results:
            return []

        candidates: list[OrcidCandidate] = []
        last_ts = time.monotonic()

        for entry in results[:_MAX_CANDIDATES]:
            orcid_id: str = entry.get("orcid-id", "")
            if not orcid_id:
                continue

            given: str = entry.get("given-names") or ""
            family: str = entry.get("family-names") or ""
            display_name = f"{given} {family}".strip()
            if not display_name:
                display_name = entry.get("credit-name", "") or orcid_id

            affs: list[Any] = entry.get("institution-name") or []

            elapsed = time.monotonic() - last_ts
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
            last_ts = time.monotonic()

            try:
                w_resp = await client.get(f"{_BASE}/{orcid_id}/works")
                w_resp.raise_for_status()
                w_data: dict[str, Any] = w_resp.json()
                works_count = len(w_data.get("group") or [])
            except httpx.HTTPError:
                works_count = 0

            candidates.append(
                OrcidCandidate(
                    orcid_id=orcid_id,
                    name=display_name,
                    affiliations=[str(a) for a in affs],
                    works_count=works_count,
                )
            )

        candidates.sort(key=lambda c: c.works_count, reverse=True)
        return candidates
