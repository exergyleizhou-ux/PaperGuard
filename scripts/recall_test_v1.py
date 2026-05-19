"""Small-N recall/precision pilot for PaperGuard.

Pulls a sample of OA retracted papers and matched non-retracted controls
from OpenAlex, scans each with PaperGuard CLI, and emits a JSON summary
of per-paper severity + per-detector firing rate.

Run from the repo root:

    .venv/Scripts/python.exe scripts/recall_test_v1.py \
        --out scripts/recall_test_v1_results.json \
        --n 10

This is a v1 pilot, not the eventual 100-vs-100 study. The OpenAlex
queries are deterministic enough that re-running on a different machine
should produce the same paper list (modulo OpenAlex re-indexing). PDF
content can change if a publisher re-renders the OA PDF; SHA-256 of
each download is logged so divergence is detectable.

Methodology:

- Retracted sample: ``filter=is_retracted:true,open_access.is_oa:true``,
  sort by cited_by_count desc, English only, exclude pure
  "Retraction Notice" articles (those are not the original research).
- Control sample: matched on subfield + publication year ± 1 + journal
  if possible, with ``is_retracted=false``, sort by cited_by_count desc.
  Fall back to subfield + year only when journal match fails.
- Both samples download OA PDFs from the publisher URL OpenAlex returns.

The output JSON is the input for ``docs/recall_test_v1.md``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx

OPENALEX = "https://api.openalex.org"


def fetch(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    r = httpx.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def is_retraction_notice(title: str | None) -> bool:
    if not title:
        return True
    t = title.lower()
    return any(
        kw in t for kw in ("retraction notice", "retraction:", "notice of retraction")
    )


def get_retracted_sample(n: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor = "*"
    while len(out) < n:
        data = fetch(
            f"{OPENALEX}/works",
            params={
                "filter": "is_retracted:true,open_access.is_oa:true,"
                "type:article,language:en",
                "sort": "cited_by_count:desc",
                "per_page": 50,
                "cursor": cursor,
            },
        )
        for r in data["results"]:
            if is_retraction_notice(r.get("title")):
                continue
            if not r["open_access"].get("oa_url"):
                continue
            out.append(r)
            if len(out) >= n:
                break
        cursor = data["meta"].get("next_cursor")
        if not cursor:
            break
    return out


def get_matched_control(retracted: dict[str, Any]) -> dict[str, Any] | None:
    """Find one non-retracted OA control matching subfield + year ±1."""
    year = retracted["publication_year"]
    primary_topic = retracted.get("primary_topic") or {}
    subfield_id = (primary_topic.get("subfield") or {}).get("id")
    if not subfield_id:
        return None
    subfield_short = subfield_id.split("/")[-1]
    filt = (
        f"is_retracted:false,open_access.is_oa:true,type:article,"
        f"language:en,primary_topic.subfield.id:{subfield_short},"
        f"publication_year:{year - 1}-{year + 1}"
    )
    data = fetch(
        f"{OPENALEX}/works",
        params={"filter": filt, "sort": "cited_by_count:desc", "per_page": 5},
    )
    for r in data["results"]:
        if r["id"] == retracted["id"]:
            continue
        if is_retraction_notice(r.get("title")):
            continue
        if not r["open_access"].get("oa_url"):
            continue
        return r
    return None


def download_pdf(url: str, dest: Path) -> tuple[bool, str]:
    """Return (success, sha256)."""
    try:
        with httpx.stream("GET", url, timeout=60, follow_redirects=True) as r:
            r.raise_for_status()
            ctype = (r.headers.get("content-type") or "").lower()
            if "pdf" not in ctype and not url.endswith(".pdf"):
                # Some publishers return HTML wrappers — accept anyway,
                # PaperGuard's PDF reader will fail loudly if it isn't PDF.
                pass
            h = hashlib.sha256()
            with dest.open("wb") as f:
                for chunk in r.iter_bytes(chunk_size=65536):
                    h.update(chunk)
                    f.write(chunk)
        return True, h.hexdigest()
    except Exception as e:  # noqa: BLE001
        return False, f"error: {e}"


def run_scan(pdf: Path, out_json: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    paperguard = (
        Path(__file__).resolve().parent.parent
        / ".venv"
        / "Scripts"
        / "paperguard.exe"
    )
    if not paperguard.exists():
        paperguard = "paperguard"  # type: ignore[assignment]
    cmd = [
        str(paperguard),
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
            cmd, env=env, capture_output=True, timeout=300, text=True
        )
        if result.returncode != 0:
            return {"error": f"exit={result.returncode}", "stderr": result.stderr[-2000:]}
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
    ap.add_argument("--n", type=int, default=10, help="papers per arm")
    ap.add_argument("--out", required=True, help="JSON output path")
    ap.add_argument(
        "--work-dir",
        default=None,
        help="Directory for downloaded PDFs (default: a system temp dir)",
    )
    args = ap.parse_args()

    work_dir = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="pg_recall_"))
    work_dir.mkdir(parents=True, exist_ok=True)
    print(f"Work dir: {work_dir}", file=sys.stderr)

    print(f"Fetching {args.n} OA retracted papers from OpenAlex …", file=sys.stderr)
    retracted = get_retracted_sample(args.n)
    print(f"  got {len(retracted)} retracted", file=sys.stderr)

    print(f"Building matched control sample …", file=sys.stderr)
    pairs: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for r in retracted:
        c = get_matched_control(r)
        pairs.append((r, c))
        print(
            f"  retracted {r['id'].split('/')[-1]} -> control "
            f"{c['id'].split('/')[-1] if c else 'NONE'}",
            file=sys.stderr,
        )

    results: list[dict[str, Any]] = []
    for i, (r, c) in enumerate(pairs, 1):
        for arm, work in (("retracted", r), ("control", c)):
            if work is None:
                continue
            oa_url = work["open_access"]["oa_url"]
            doi = (work.get("doi") or "unknown").replace("https://doi.org/", "")
            slug = doi.replace("/", "_")
            pdf_path = work_dir / f"{arm}_{i:02d}_{slug}.pdf"
            json_path = work_dir / f"{arm}_{i:02d}_{slug}.report.json"
            print(f"[{i}/{args.n}] {arm:9s} downloading {doi} …", file=sys.stderr)
            ok, h = download_pdf(oa_url, pdf_path)
            record: dict[str, Any] = {
                "arm": arm,
                "doi": doi,
                "openalex_id": work["id"],
                "title": work.get("title", ""),
                "year": work.get("publication_year"),
                "oa_url": oa_url,
                "pdf_sha256": h if ok else None,
                "download_ok": ok,
            }
            if ok:
                print(f"  scanning …", file=sys.stderr)
                report = run_scan(pdf_path, json_path)
                record["scan"] = summarise(report)
            results.append(record)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "n_per_arm": args.n,
                "results": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\nWrote {len(results)} records to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
