"""N=30+30 image-layer recall study — F1 (intra-paper pHash) + F4 (cross-paper).

The text-layer studies (v8 / v9) measured T6/T7/T8 only. F1 and F4
detect *image-content* anomalies — intra-paper Western-blot panel
duplication (F1) and cross-paper figure re-use (F4). These have
never been measured against a public retraction dataset.

Pipeline per paper:
  1. Fetch OA PDF via paperguard.fetcher.oa_pdf.
  2. Extract images via paperguard.extractor.images.extract_pdf_images
     (with raster-fallback so vector figures are captured).
  3. F1: compute pairwise pHash hamming on intra-paper image set;
     record min distance + severity reached.
  4. F4: insert images into a corpus SQLite store keyed by DOI;
     after all retracted are inserted, run F4 over each retracted
     paper again to detect cross-paper duplication; then over each
     control to measure the control-arm cross-paper signal.

Outputs ``scripts/recall_image_v1_results.json`` with one record per
paper:
  {arm, doi, year, subfield,
   pdf_ok, n_images,
   f1_min_hamming, f1_severity, f1_n_pairs_concern,
   f4_min_hamming_cross, f4_severity, f4_n_matches,
   error}

Resumable via --resume (skips records already in the partial file).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from paperguard.detectors.f1_image_duplication import (
    F1ImageDuplicationDetector,
    ImageDuplicationInput,
)
from paperguard.detectors.f4_cross_paper_image import (
    CrossPaperImageInput,
    F4CrossPaperImageDetector,
)
from paperguard.extractor.images import extract_pdf_images
from paperguard.fetcher.oa_pdf import fetch_oa_pdf

OPENALEX = "https://api.openalex.org"
USER_AGENT = (
    "PaperGuard/2.1.2 (recall-image v1; "
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
            httpx.ReadError, httpx.ConnectError,
            httpx.RemoteProtocolError, httpx.TimeoutException,
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
            "retraction notice", "retraction:", "notice of retraction",
            "retracted:", "withdrawn:",
        )
    )


def get_retracted_sample(n: int, year_min: int = 2020) -> list[dict[str, Any]]:
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
                    f"publication_year:>{year_min - 1},"
                    # bias toward image-heavy fields
                    "primary_topic.field.id:fields/27|fields/13|fields/11|"
                    "fields/24"
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
            "filter": filt, "sort": "cited_by_count:desc",
            "per_page": 10, "mailto": CONTACT_EMAIL,
        },
    )
    for r in data["results"]:
        if r["id"] == retracted["id"]:
            continue
        if is_retraction_notice(r.get("title")):
            continue
        return r
    return None


def _severity_from_min_hamming(min_h: int | None) -> str:
    if min_h is None:
        return "none"
    if min_h <= 2:
        return "CRITICAL"
    if min_h <= 5:
        return "SUSPICIOUS"
    if min_h <= 8:
        return "CONCERN"
    return "none"


def _run_f1(image_paths: list[Path]) -> dict[str, Any]:
    """Return F1 summary: min hamming + severity + n concern pairs."""
    if len(image_paths) < 2:
        return {
            "f1_min_hamming": None,
            "f1_severity": "skip",
            "f1_n_pairs_concern": 0,
        }
    det = F1ImageDuplicationDetector()
    result = det.detect(ImageDuplicationInput(image_paths=image_paths))
    if not result.applicable:
        return {
            "f1_min_hamming": None,
            "f1_severity": f"skip:{result.skip_reason}",
            "f1_n_pairs_concern": 0,
        }
    if not result.findings:
        return {
            "f1_min_hamming": None,
            "f1_severity": "none",
            "f1_n_pairs_concern": 0,
        }
    # finding evidence carries the pairs + distances
    min_h: int | None = None
    n_pairs = 0
    for f in result.findings:
        n_pairs += 1
        d = f.evidence.get("hamming_distance")
        if isinstance(d, int):
            if min_h is None or d < min_h:
                min_h = d
    return {
        "f1_min_hamming": min_h,
        "f1_severity": _severity_from_min_hamming(min_h),
        "f1_n_pairs_concern": n_pairs,
    }


def _run_f4(
    image_paths: list[Path],
    store_path: Path,
    paper_id: str,
    authors: list[str],
) -> dict[str, Any]:
    if not image_paths:
        return {
            "f4_min_hamming_cross": None,
            "f4_severity": "skip:no_images",
            "f4_n_matches": 0,
        }
    det = F4CrossPaperImageDetector()
    result = det.detect(
        CrossPaperImageInput(
            image_paths=image_paths,
            store_path=store_path,
            current_paper_id=paper_id,
            current_authors=authors,
        )
    )
    if not result.applicable:
        return {
            "f4_min_hamming_cross": None,
            "f4_severity": f"skip:{result.skip_reason}",
            "f4_n_matches": 0,
        }
    if not result.findings:
        return {
            "f4_min_hamming_cross": None,
            "f4_severity": "none",
            "f4_n_matches": 0,
        }
    min_h: int | None = None
    n = 0
    for f in result.findings:
        n += 1
        d = f.evidence.get("hamming_distance")
        if isinstance(d, int):
            if min_h is None or d < min_h:
                min_h = d
    return {
        "f4_min_hamming_cross": min_h,
        "f4_severity": _severity_from_min_hamming(min_h),
        "f4_n_matches": n,
    }


def _scan_one(
    work: dict[str, Any],
    work_dir: Path,
    store_path: Path,
    arm: str,
    idx: int,
) -> dict[str, Any]:
    doi = (work.get("doi") or "unknown").replace("https://doi.org/", "")
    slug = doi.replace("/", "_").replace(":", "_")[:80]
    pdf_path = work_dir / f"{arm}_{idx:03d}_{slug}.pdf"
    image_dir = work_dir / f"{arm}_{idx:03d}_{slug}_imgs"
    image_dir.mkdir(parents=True, exist_ok=True)

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
        "pdf_ok": False,
        "n_images": 0,
        "f1_severity": "skip",
        "f4_severity": "skip",
        "error": None,
    }

    # 1) Fetch PDF
    oa_url = (work.get("open_access") or {}).get("oa_url")
    try:
        fetch_res = fetch_oa_pdf(doi, pdf_path, openalex_oa_url=oa_url)
    except Exception as e:  # noqa: BLE001
        record["error"] = f"pdf_fetch: {type(e).__name__}: {e}"
        return record
    if not fetch_res.ok:
        record["error"] = f"pdf_fetch: {fetch_res.error}"
        return record
    record["pdf_ok"] = True

    # 2) Extract images
    try:
        images = extract_pdf_images(pdf_path, image_dir)
    except Exception as e:  # noqa: BLE001
        record["error"] = f"img_extract: {type(e).__name__}: {e}"
        return record
    record["n_images"] = len(images)
    if not images:
        record["f1_severity"] = "skip:no_images"
        record["f4_severity"] = "skip:no_images"
        return record

    # 3) F1 intra-paper
    record.update(_run_f1(images))

    # 4) F4 cross-paper (inserts into store)
    authors = []
    for a in work.get("authorships", [])[:10]:
        n = (a.get("author") or {}).get("display_name")
        if n:
            authors.append(n)
    record.update(_run_f4(images, store_path, doi, authors))

    return record


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--out", required=True)
    ap.add_argument("--year-min", type=int, default=2020)
    ap.add_argument("--work-dir", default=None)
    ap.add_argument(
        "--resume", action="store_true",
        help="Skip records already in the partial JSON.",
    )
    args = ap.parse_args()

    out_path = Path(args.out)
    partial_path = out_path.with_suffix(".partial.json")
    work_dir = (
        Path(args.work_dir) if args.work_dir
        else Path(tempfile.mkdtemp(prefix="pg_image_recall_v1_"))
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    store_path = work_dir / "image_corpus.db"
    print(f"Work dir: {work_dir}", file=sys.stderr)

    seen_keys: set[str] = set()
    existing: list[dict[str, Any]] = []
    if args.resume and partial_path.exists():
        prev = json.loads(partial_path.read_text(encoding="utf-8"))
        existing = prev.get("results", [])
        seen_keys = {f"{r['arm']}::{r['doi']}" for r in existing}
        print(
            f"Resume: {len(existing)} existing records", file=sys.stderr
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
                f"{type(e).__name__}", file=sys.stderr,
            )
            c = None
        pairs.append((r, c))

    results: list[dict[str, Any]] = list(existing)

    for i, (r, c) in enumerate(pairs, 1):
        for arm, work in (("retracted", r), ("control", c)):
            if work is None:
                continue
            doi = (work.get("doi") or "unknown").replace(
                "https://doi.org/", ""
            )
            key = f"{arm}::{doi}"
            if key in seen_keys:
                print(
                    f"[{i:3d}/{args.n}] {arm:9s} {doi}  (resume-skip)",
                    file=sys.stderr, flush=True,
                )
                continue
            print(
                f"[{i:3d}/{args.n}] {arm:9s} {doi}",
                file=sys.stderr, flush=True,
            )
            record = _scan_one(work, work_dir, store_path, arm, i)
            results.append(record)
            seen_keys.add(key)
            partial_path.write_text(
                json.dumps(
                    {
                        "n_per_arm": args.n,
                        "store_path": str(store_path),
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
                "store_path": str(store_path),
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
