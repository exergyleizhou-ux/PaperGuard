"""N=100+100 recall/precision study — v5: wired through paperguard.fetcher.oa_pdf.

v5 differences from v2 (see ``docs/recall_test_v2.md``):

- **All PDF fetching now goes through ``paperguard.fetcher.oa_pdf``**,
  which tries Europe PMC / PubMed Central first (clean PDFs for any
  PMC-indexed paper), then Unpaywall ``best_oa_location.url_for_pdf``,
  then the caller-supplied OpenAlex ``oa_url``. Every download is
  ``%PDF-`` header-validated.
- Scanner is error-tolerant since PaperGuard 2.0.3.
- T3 ethics rule is CONCERN (not SUSPICIOUS) since 2.0.4.
- T5 only emits findings on genuine outliers since 2.0.5.

The OpenAlex sample selection logic is unchanged. The only difference
versus v2 is *how the PDFs are obtained*. Comparing v5 to v2 on the
same query is therefore a clean A/B on the fetcher.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from paperguard.fetcher.oa_pdf import fetch_oa_pdf

OPENALEX = "https://api.openalex.org"
USER_AGENT = (
    "PaperGuard/2.0.5 (recall-test v5; "
    "https://github.com/exergyleizhou-ux/PaperGuard)"
)
CONTACT_EMAIL = os.environ.get("PAPERGUARD_CONTACT_EMAIL", "research@example.org")

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
    """GET ``url`` as JSON with up to 3 retries on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            _rate_limit(url)
            r = httpx.get(
                url, params=params, timeout=30, headers={"User-Agent": USER_AGENT}
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


def get_retracted_sample(n: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor = "*"
    pages = 0
    while len(out) < n and pages < 20:
        data = fetch(
            f"{OPENALEX}/works",
            params={
                "filter": (
                    "is_retracted:true,open_access.is_oa:true,"
                    "type:article,language:en,"
                    "primary_topic.field.id:fields/27|fields/13|fields/11|"
                    "fields/24|fields/29|fields/30"
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


def run_scan(pdf: Path, out_json: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    paperguard = (
        Path(__file__).resolve().parent.parent / ".venv" / "Scripts" / "paperguard.exe"
    )
    cmd = [
        str(paperguard) if paperguard.exists() else "paperguard",
        "scan",
        "-f",
        str(pdf),
        "--output-json",
        str(out_json),
        "--lang",
        "en",
    ]
    try:
        result = subprocess.run(
            cmd, env=env, capture_output=True, timeout=600, text=True
        )
        if result.returncode != 0:
            return {"error": f"exit={result.returncode}", "stderr": result.stderr[-1500:]}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    if not out_json.exists():
        return {"error": "no json output"}
    with out_json.open(encoding="utf-8") as f:
        return json.load(f)


def summarise(rep: dict[str, Any]) -> dict[str, Any]:
    if "error" in rep:
        return rep
    findings = rep.get("all_findings") or []
    sev_counts: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}
    hits: dict[str, int] = {}
    for f in findings:
        s = f.get("severity", 0)
        sev_counts[s] = sev_counts.get(s, 0) + 1
        d = f.get("detector_id", "?")
        hits[d] = hits.get(d, 0) + 1
    return {
        "overall_severity": rep.get("overall_severity"),
        "n_findings": len(findings),
        "severity_counts": sev_counts,
        "detectors_fired": sorted(hits),
        "detector_hits": hits,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", required=True)
    ap.add_argument("--work-dir", default=None)
    args = ap.parse_args()

    work_dir = (
        Path(args.work_dir)
        if args.work_dir
        else Path(tempfile.mkdtemp(prefix="pg_recall_v5_"))
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    print(f"Work dir: {work_dir}", file=sys.stderr)

    print(f"Fetching {args.n} OA retracted papers …", file=sys.stderr)
    retracted = get_retracted_sample(args.n)
    print(f"  got {len(retracted)} retracted", file=sys.stderr)

    print("Building matched control sample …", file=sys.stderr)
    pairs: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for r in retracted:
        try:
            c = get_matched_control(r)
        except Exception as e:  # noqa: BLE001
            print(
                f"  control lookup failed for {r['id']}: {type(e).__name__}",
                file=sys.stderr,
            )
            c = None
        pairs.append((r, c))

    results: list[dict[str, Any]] = []
    for i, (r, c) in enumerate(pairs, 1):
        for arm, work in (("retracted", r), ("control", c)):
            if work is None:
                continue
            doi = (work.get("doi") or "unknown").replace("https://doi.org/", "")
            slug = doi.replace("/", "_").replace(":", "_")[:80]
            pdf_path = work_dir / f"{arm}_{i:03d}_{slug}.pdf"
            json_path = work_dir / f"{arm}_{i:03d}_{slug}.report.json"

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

            print(f"[{i:3d}/{args.n}] {arm:9s} {doi}", file=sys.stderr, flush=True)

            oa_url = (work.get("open_access") or {}).get("oa_url")
            try:
                fetch_res = fetch_oa_pdf(doi, pdf_path, openalex_oa_url=oa_url)
            except Exception as e:  # noqa: BLE001
                record["download_ok"] = False
                record["download_error"] = f"exception: {type(e).__name__}: {e}"
                record["pdf_sha256"] = None
                record["fetch_source"] = ""
                results.append(record)
                continue

            record["download_ok"] = fetch_res.ok
            record["fetch_source"] = fetch_res.source
            record["content_type"] = fetch_res.content_type
            if fetch_res.ok:
                record["pdf_sha256"] = fetch_res.sha256
                report = run_scan(pdf_path, json_path)
                record["scan"] = summarise(report)
            else:
                record["pdf_sha256"] = None
                record["download_error"] = fetch_res.error

            results.append(record)
            if len(results) % 10 == 0:
                with Path(args.out).with_suffix(".partial.json").open(
                    "w", encoding="utf-8"
                ) as f:
                    json.dump(
                        {"n_per_arm": args.n, "results": results},
                        f,
                        indent=2,
                        ensure_ascii=False,
                    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(
            {"n_per_arm": args.n, "results": results},
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\nWrote {len(results)} records to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
