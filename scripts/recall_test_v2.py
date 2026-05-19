"""N=100+100 recall/precision study for PaperGuard.

v2 improvements over v1 (see ``docs/recall_test_v1.md``):

1. **PDF-only fetcher.** Try Unpaywall ``best_oa_location.url_for_pdf``
   first (more reliable than OpenAlex ``oa_url``). Fall back to
   OpenAlex. After download, validate that the bytes begin with
   ``%PDF-`` — if not, discard and try the fallback.
2. **Scanner is now error-tolerant** (PaperGuard 2.0.3) so individual
   pathological PDFs no longer derail the whole run.
3. **Per-paper timeout** raised to 600s for image-heavy PDFs.

Output JSON has the same shape as v1 so a `recall_test_v1_results.json`
viewer would still work; v2 just has more (and more usable) rows.

Run from the repo root:

    .venv/Scripts/python.exe scripts/recall_test_v2.py \
        --n 100 \
        --out scripts/recall_test_v2_results.json

This makes 200 OpenAlex calls (well within the 100k/day anonymous
limit) and 200+ direct publisher PDF downloads (rate-limited at
1 request/sec per host). Wall clock ≈ 1-2 hours on a fast link.
"""
from __future__ import annotations

import argparse
import hashlib
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

OPENALEX = "https://api.openalex.org"
UNPAYWALL = "https://api.unpaywall.org/v2"
USER_AGENT = "PaperGuard/2.0.3 (recall-test; https://github.com/exergyleizhou-ux/PaperGuard)"
# Unpaywall requires an email parameter; OpenAlex appreciates one for
# the polite pool. Override with PAPERGUARD_CONTACT_EMAIL.
CONTACT_EMAIL = os.environ.get("PAPERGUARD_CONTACT_EMAIL", "research@example.org")

_last_request_per_host: dict[str, float] = {}


def _rate_limit(url: str, min_interval: float = 1.0) -> None:
    """Crude per-host throttle so we don't hammer publishers."""
    host = urlparse(url).netloc
    now = time.time()
    last = _last_request_per_host.get(host, 0.0)
    wait = (last + min_interval) - now
    if wait > 0:
        time.sleep(wait)
    _last_request_per_host[host] = time.time()


def fetch(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    _rate_limit(url, min_interval=0.2)
    r = httpx.get(url, params=params, timeout=30, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    return r.json()


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
                    "fields/24|fields/29|fields/30"  # Med, Bio, Agri, Neuro, Pharm, Health
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
            if not (r.get("open_access") or {}).get("oa_url"):
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
        if not (r.get("open_access") or {}).get("oa_url"):
            continue
        return r
    return None


def resolve_pdf_url(work: dict[str, Any]) -> str | None:
    """Try Unpaywall first, fall back to OpenAlex `oa_url`."""
    doi = (work.get("doi") or "").replace("https://doi.org/", "")
    if doi:
        try:
            data = fetch(f"{UNPAYWALL}/{doi}", params={"email": CONTACT_EMAIL})
            best = data.get("best_oa_location") or {}
            pdf_url = best.get("url_for_pdf")
            if pdf_url:
                return str(pdf_url)
        except Exception:  # noqa: BLE001
            pass
    return (work.get("open_access") or {}).get("oa_url")


def download_pdf(url: str, dest: Path) -> tuple[bool, str, str]:
    """Return (success, sha256_or_error, content_type)."""
    try:
        _rate_limit(url, min_interval=1.0)
        with httpx.stream(
            "GET",
            url,
            timeout=60,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as r:
            r.raise_for_status()
            ctype = (r.headers.get("content-type") or "").lower()
            # peek first 8 bytes to confirm PDF signature
            first_chunk = next(r.iter_bytes(chunk_size=8192), b"")
            if not first_chunk.startswith(b"%PDF-"):
                return False, "not a PDF (first bytes != %PDF-)", ctype
            h = hashlib.sha256()
            h.update(first_chunk)
            with dest.open("wb") as f:
                f.write(first_chunk)
                for chunk in r.iter_bytes(chunk_size=65536):
                    h.update(chunk)
                    f.write(chunk)
        return True, h.hexdigest(), ctype
    except Exception as e:  # noqa: BLE001
        return False, f"error: {type(e).__name__}: {e}", ""


def run_scan(pdf: Path, out_json: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    paperguard = (
        Path(__file__).resolve().parent.parent
        / ".venv"
        / "Scripts"
        / "paperguard.exe"
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
            return {
                "error": f"exit={result.returncode}",
                "stderr": result.stderr[-2000:],
            }
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    if not out_json.exists():
        return {"error": "no json output"}
    with out_json.open(encoding="utf-8") as f:
        return json.load(f)


def summarise(report: dict[str, Any]) -> dict[str, Any]:
    if "error" in report:
        return report
    findings = report.get("all_findings") or []
    sev_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    detector_hits: dict[str, int] = {}
    for f in findings:
        sev = f.get("severity", 0)
        sev_counts[sev] = sev_counts.get(sev, 0) + 1
        d = f.get("detector_id", "?")
        detector_hits[d] = detector_hits.get(d, 0) + 1
    return {
        "overall_severity": report.get("overall_severity"),
        "n_findings": len(findings),
        "severity_counts": sev_counts,
        "detectors_fired": sorted(detector_hits.keys()),
        "detector_hits": detector_hits,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100, help="papers per arm")
    ap.add_argument("--out", required=True, help="JSON output path")
    ap.add_argument(
        "--work-dir",
        default=None,
        help="Directory for downloaded PDFs (default: a system temp dir)",
    )
    args = ap.parse_args()

    work_dir = (
        Path(args.work_dir)
        if args.work_dir
        else Path(tempfile.mkdtemp(prefix="pg_recall_v2_"))
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    print(f"Work dir: {work_dir}", file=sys.stderr)

    print(f"Fetching {args.n} OA retracted papers …", file=sys.stderr)
    retracted = get_retracted_sample(args.n)
    print(f"  got {len(retracted)} retracted", file=sys.stderr)

    print("Building matched control sample …", file=sys.stderr)
    pairs: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for r in retracted:
        c = get_matched_control(r)
        pairs.append((r, c))

    results: list[dict[str, Any]] = []
    for i, (r, c) in enumerate(pairs, 1):
        for arm, work in (("retracted", r), ("control", c)):
            if work is None:
                continue
            pdf_url = resolve_pdf_url(work)
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
                "pdf_url": pdf_url,
            }
            if not pdf_url:
                record["download_ok"] = False
                record["pdf_sha256"] = None
                record["download_error"] = "no pdf url"
                results.append(record)
                continue
            print(
                f"[{i:3d}/{args.n}] {arm:9s} {doi}",
                file=sys.stderr,
                flush=True,
            )
            ok, h_or_err, ctype = download_pdf(pdf_url, pdf_path)
            record["download_ok"] = ok
            record["content_type"] = ctype
            if ok:
                record["pdf_sha256"] = h_or_err
                report = run_scan(pdf_path, json_path)
                record["scan"] = summarise(report)
            else:
                record["pdf_sha256"] = None
                record["download_error"] = h_or_err
            results.append(record)

            # Stream-write the results JSON every 10 records so a crash
            # mid-run doesn't lose progress.
            if len(results) % 10 == 0:
                tmp_out = Path(args.out).with_suffix(".partial.json")
                with tmp_out.open("w", encoding="utf-8") as f:
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
