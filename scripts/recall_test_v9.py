"""N=100+100 LR+ study — v9: T6 + T7 + T8, doubled cohort.

Same methodology as v8 but with:
- N = 100 per arm (was 50)
- Year filter relaxed to 2020+ to broaden the retracted pool
- Tries T7 logprobs + T8 paraphrase on each paper. Recording is
  graceful — if either route returns None on the configured endpoint,
  we log "skipped" rather than fabricating a number.

This produces the dataset that 2.1.0 ships with: a transparent
record of *which* detectors fired on *which* papers under the
*current* LLM endpoint. As stronger endpoints become available the
JSON can be re-analysed without re-running the PMC fetch.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from paperguard.detectors.t6_ai_text_heuristic import (
    T6AITextHeuristicDetector,
)
from paperguard.detectors.t7_perplexity import compute_perplexity
from paperguard.detectors.t8_detectgpt import compute_detection_score
from paperguard.fetcher.europepmc import fetch_article

OPENALEX = "https://api.openalex.org"
USER_AGENT = (
    "PaperGuard/2.1.0 (recall-test v9; "
    "https://github.com/exergyleizhou-ux/PaperGuard)"
)
CONTACT_EMAIL = os.environ.get(
    "PAPERGUARD_CONTACT_EMAIL", "research@example.org"
)

_last_per_host: dict[str, float] = {}


def _rate_limit(url: str, min_interval: float = 0.2) -> None:
    host = urlparse(url).netloc
    now = time.time()
    last = _last_per_host.get(host, 0.0)
    wait = (last + min_interval) - now
    if wait > 0:
        time.sleep(wait)
    _last_per_host[host] = time.time()


def fetch(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            _rate_limit(url)
            r = httpx.get(
                url, params=params, timeout=30,
                headers={"User-Agent": USER_AGENT},
            )
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
        except (
            httpx.ReadError,
            httpx.ConnectError,
            httpx.RemoteProtocolError,
            httpx.TimeoutException,
        ) as e:
            last_exc = e
            time.sleep(2 + attempt * 3)
            continue
    assert last_exc is not None
    raise last_exc


def is_retraction_notice(title: str | None) -> bool:
    if not title:
        return True
    t = title.lower()
    return any(
        kw in t
        for kw in (
            "retraction notice",
            "retraction:",
            "notice of retraction",
            "retracted:",
            "withdrawn:",
        )
    )


def get_retracted_sample(n: int, year_min: int = 2020) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor = "*"
    pages = 0
    while len(out) < n and pages < 30:
        data = fetch(
            f"{OPENALEX}/works",
            params={
                "filter": (
                    "is_retracted:true,open_access.is_oa:true,"
                    "type:article,language:en,"
                    f"publication_year:>{year_min - 1}"
                ),
                "sort": "cited_by_count:desc",
                "per_page": 50,
                "cursor": cursor,
                "mailto": CONTACT_EMAIL,
            },
        )
        for r in data["results"]:
            if is_retraction_notice(r.get("title")):
                continue
            out.append(r)
            if len(out) >= n:
                break
        cursor = data["meta"].get("next_cursor")
        if not cursor:
            break
        pages += 1
    return out


def get_matched_control(retracted: dict[str, Any]) -> dict[str, Any] | None:
    year = retracted["publication_year"]
    primary_topic = retracted.get("primary_topic") or {}
    subfield = (primary_topic.get("subfield") or {}).get("id")
    if not subfield:
        return None
    subfield_short = subfield.split("/")[-1]
    filt = (
        f"is_retracted:false,open_access.is_oa:true,type:article,"
        f"language:en,primary_topic.subfield.id:{subfield_short},"
        f"publication_year:{year - 1}-{year + 1}"
    )
    data = fetch(
        f"{OPENALEX}/works",
        params={
            "filter": filt,
            "sort": "cited_by_count:desc",
            "per_page": 10,
            "mailto": CONTACT_EMAIL,
        },
    )
    for r in data["results"]:
        if r["id"] == retracted["id"]:
            continue
        if is_retraction_notice(r.get("title")):
            continue
        return r
    return None


def _t6_density(text: str) -> tuple[float | None, str | None]:
    det = T6AITextHeuristicDetector()
    result = det.detect(text)
    if not result.applicable:
        return None, None
    for f in result.findings:
        if "density" in f.evidence:
            density = f.evidence.get("density")
            provider = f.evidence.get("provider_attribution")
            if isinstance(density, (int, float)):
                return float(density), (
                    provider if isinstance(provider, str) else None
                )
    for f in result.findings:
        if "provider_attribution" in f.evidence:
            provider = f.evidence.get("provider_attribution")
            density = f.evidence.get("density", 0.0)
            return float(density), (
                provider if isinstance(provider, str) else None
            )
    return 0.0, None


def _scan_one(doi: str, *, run_t7: bool, run_t8: bool) -> dict[str, Any]:
    record: dict[str, Any] = {
        "pmc_ok": False,
        "n_chars": 0,
        "t6_density": None,
        "t6_provider": None,
        "t7_perplexity": None,
        "t7_outcome": "skip",
        "t8_score": None,
        "t8_outcome": "skip",
        "scan_error": None,
    }
    try:
        article = fetch_article(doi)
    except Exception as e:  # noqa: BLE001
        record["scan_error"] = f"pmc_fetch: {type(e).__name__}: {e}"
        return record
    if not article or not article.full_text:
        record["scan_error"] = "pmc_no_fulltext"
        return record
    text = article.full_text
    record["pmc_ok"] = True
    record["n_chars"] = len(text)
    focused = text[:18000]

    try:
        density, provider = _t6_density(focused)
        record["t6_density"] = density
        record["t6_provider"] = provider
    except Exception as e:  # noqa: BLE001
        record["scan_error"] = f"t6: {type(e).__name__}: {e}"

    if run_t7:
        try:
            ppl = compute_perplexity(focused)
            if ppl is None:
                record["t7_outcome"] = "no_logprobs_or_no_key"
            else:
                record["t7_perplexity"] = ppl
                record["t7_outcome"] = "ok"
        except Exception as e:  # noqa: BLE001
            record["t7_outcome"] = f"err:{type(e).__name__}"

    if run_t8:
        try:
            score, _diag = compute_detection_score(focused)
            if score is None:
                record["t8_outcome"] = "no_scores"
            else:
                record["t8_score"] = score
                record["t8_outcome"] = "ok"
        except Exception as e:  # noqa: BLE001
            record["t8_outcome"] = f"err:{type(e).__name__}"

    return record


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", required=True)
    ap.add_argument("--year-min", type=int, default=2020)
    ap.add_argument("--run-t7", action="store_true")
    ap.add_argument("--run-t8", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    out_path = Path(args.out)
    partial_path = out_path.with_suffix(".partial.json")
    seen_keys: set[str] = set()
    existing: list[dict[str, Any]] = []
    if args.resume and partial_path.exists():
        prev = json.loads(partial_path.read_text(encoding="utf-8"))
        existing = prev.get("results", [])
        seen_keys = {f"{r['arm']}::{r['doi']}" for r in existing}
        print(
            f"Resume: {len(existing)} existing records",
            file=sys.stderr,
        )

    print(f"Fetching {args.n} OA retracted papers …", file=sys.stderr)
    retracted = get_retracted_sample(args.n, year_min=args.year_min)
    print(f"  got {len(retracted)} retracted", file=sys.stderr)

    print("Building matched control sample …", file=sys.stderr)
    pairs: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for r in retracted:
        try:
            c = get_matched_control(r)
        except Exception as e:  # noqa: BLE001
            print(
                f"  control lookup failed for {r['id']}: "
                f"{type(e).__name__}",
                file=sys.stderr,
            )
            c = None
        pairs.append((r, c))

    results: list[dict[str, Any]] = list(existing)
    model_used = (
        os.environ.get("PAPERGUARD_LLM_MODEL")
        or "gpt-4o-mini (default)"
    )

    for i, (r, c) in enumerate(pairs, 1):
        for arm, work in (("retracted", r), ("control", c)):
            if work is None:
                continue
            doi = (work.get("doi") or "unknown").replace(
                "https://doi.org/", ""
            )
            key = f"{arm}::{doi}"
            if key in seen_keys:
                continue

            record: dict[str, Any] = {
                "arm": arm,
                "doi": doi,
                "openalex_id": work["id"],
                "title": (work.get("title") or "")[:200],
                "year": work.get("publication_year"),
                "subfield": (
                    ((work.get("primary_topic") or {}).get("subfield") or {})
                    .get("display_name")
                ),
            }
            print(
                f"[{i:3d}/{args.n}] {arm:9s} {doi}",
                file=sys.stderr, flush=True,
            )
            record.update(
                _scan_one(doi, run_t7=args.run_t7, run_t8=args.run_t8)
            )
            results.append(record)
            seen_keys.add(key)
            partial_path.write_text(
                json.dumps(
                    {
                        "n_per_arm": args.n,
                        "model": model_used,
                        "results": results,
                    },
                    indent=2, ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "n_per_arm": args.n,
                "model": model_used,
                "results": results,
            },
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {len(results)} records to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
