"""Figure/table recall validation against public retracted papers (PMC OA).

Exercises the decisive anti-fabrication families that text-only validation
never reached: image forensics (F1/F2/F3/F5/F6/F7) and the Carlisle baseline-
balance test (C1). For each cohort paper we download the PMC OA PDF, run the
offline ``evidence.figure_pipeline.run_figure_pipeline`` connector, and tally
how often any image-forensics detector or C1 flags an anomaly.

Cohorts (public, OA only, no living-author targeting):
  * RETRACTED — Europe PMC ``PUB_TYPE:"Retracted Publication"``, OA, in-EPMC.
  * CONTROL   — Europe PMC OA research-articles, in-EPMC, not retracted.

Reports per detector + combined: recall (retracted flagged), FP (control
flagged), LR+ = recall/FP. Aggregate only — no titles, IDs, authors, verdicts.

Usage:
    .venv/Scripts/python.exe scripts/validate_recall_figures.py --n 15
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

EPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
IMAGE_DETECTORS = ["F1", "F2", "F3", "F5", "F6", "F7"]
ALL_KEYS = [*IMAGE_DETECTORS, "C1", "ANY"]


def _get_with_retry(
    client: httpx.Client, params: dict[str, object], tries: int = 4
) -> httpx.Response | None:
    """GET with exponential backoff. Returns None if all tries fail.

    This environment has intermittent TLS faults (SSL bad-record-mac) on
    sustained HTTPS; a transient failure should skip a page, not abort the run.
    """
    delay = 1.0
    for attempt in range(tries):
        try:
            r = client.get(EPMC_SEARCH, params=params)
            r.raise_for_status()
            return r
        except httpx.HTTPError:
            if attempt == tries - 1:
                return None
            time.sleep(delay)
            delay *= 2
    return None


def epmc_pmcids(query: str, want: int) -> list[str]:
    """Return PMCIDs (with full text in EPMC) matching a Europe PMC query.

    Resilient to transient TLS/network errors: a failed page is retried with
    backoff, then skipped, so the whole run is not aborted by one bad record.
    """
    ids: list[str] = []
    cursor = "*"
    with httpx.Client(timeout=40.0) as client:
        while len(ids) < want and cursor:
            r = _get_with_retry(
                client,
                {
                    "query": query,
                    "format": "json",
                    "pageSize": 100,
                    "cursorMark": cursor,
                    "resultType": "lite",
                },
            )
            if r is None:
                break  # network gave up; return what we have
            data = r.json()
            for res in data.get("resultList", {}).get("result", []):
                pmcid = res.get("pmcid")
                if pmcid and res.get("inEPMC") == "Y":
                    ids.append(pmcid)
                if len(ids) >= want:
                    break
            nxt = data.get("nextCursorMark")
            if not nxt or nxt == cursor:
                break
            cursor = nxt
            time.sleep(0.2)
    return ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=15, help="papers scored per cohort")
    ap.add_argument(
        "--over-fetch", type=int, default=6,
        help="candidate-pool multiplier: fetch n*over_fetch PMCIDs per cohort "
             "(raise this when OA figure-package coverage is low, e.g. for "
             "retractions)",
    )
    ap.add_argument(
        "--discipline", default="",
        help="optional Europe PMC sub-query to bias toward figure-heavy fields "
             "so F1-F7 have real panels to score, e.g. "
             "'(western blot OR immunohistochemistry OR microscopy OR flow "
             "cytometry)'",
    )
    args = ap.parse_args()

    from paperguard.core.types import Severity
    from paperguard.evidence.figure_pipeline import (
        _run_baseline_detector,
        _run_image_detectors,
    )
    from paperguard.extractor.pmc_figures import fetch_pmc_figure_images
    from paperguard.fetcher.oa_pdf import _pmc_pdf_url, _try_download

    def run_cohort(query: str, label: str, tmp: Path) -> dict[str, int]:
        print(f"\n[{label}] searching Europe PMC ...", flush=True)
        pmcids = epmc_pmcids(query, args.n * max(1, args.over_fetch))
        print(f"  {len(pmcids)} OA candidates; fetching figure panels for up to "
              f"{args.n} ...", flush=True)
        counts = {k: 0 for k in ALL_KEYS}
        got = 0
        n_with_images = 0
        n_with_tables = 0
        for pmcid in pmcids:
            if got >= args.n:
                break
            # PANEL-LEVEL figures from the PMC OA package (not page rasters).
            fig_dir = tmp / f"figs_{pmcid}"
            try:
                images = fetch_pmc_figure_images(pmcid, fig_dir)
            except Exception:
                images = []

            # C1 still needs the PDF's baseline tables; fetch PDF best-effort.
            n_tables = 0
            baseline_results: list = []
            pdf_path = tmp / f"{pmcid}.pdf"
            ok, _sha, _ct = _try_download(_pmc_pdf_url(pmcid), pdf_path)
            if ok:
                try:
                    n_tables, baseline_results = _run_baseline_detector(pdf_path)
                except Exception:
                    n_tables, baseline_results = 0, []
                pdf_path.unlink(missing_ok=True)

            # only count papers we could extract real panels or tables from
            if len(images) < 2 and n_tables == 0:
                continue
            got += 1
            n_with_images += int(len(images) >= 2)
            n_with_tables += int(n_tables > 0)

            results = list(baseline_results)
            if len(images) >= 2:
                results.extend(_run_image_detectors(images))

            flags = {k: False for k in ALL_KEYS}
            for r in results:
                if r.detector_id in flags and any(
                    f.severity >= Severity.CONCERN for f in r.findings
                ):
                    flags[r.detector_id] = True
            flags["ANY"] = any(flags[k] for k in (*IMAGE_DETECTORS, "C1"))
            for k in ALL_KEYS:
                counts[k] += int(flags[k])
            print(f"    {got}/{args.n} scored "
                  f"(panels={len(images)}, tables={n_tables})", flush=True)
            time.sleep(0.2)
        counts["N"] = got
        counts["with_images"] = n_with_images
        counts["with_tables"] = n_with_tables
        print(f"  scored {got} papers "
              f"({n_with_images} had >=2 panels, {n_with_tables} had tables)",
              flush=True)
        return counts

    disc = f" AND {args.discipline}" if args.discipline else ""
    with tempfile.TemporaryDirectory(prefix="pg_figrecall_") as td:
        tmp = Path(td)
        retracted = run_cohort(
            'PUB_TYPE:"Retracted Publication" AND OPEN_ACCESS:Y AND IN_EPMC:Y'
            + disc,
            "RETRACTED", tmp,
        )
        control = run_cohort(
            'OPEN_ACCESS:Y AND IN_EPMC:Y AND NOT PUB_TYPE:"Retracted Publication" '
            'AND FIRST_PDATE:[2018-01-01 TO 2023-12-31]' + disc,
            "CONTROL", tmp,
        )

    nr, nc = retracted["N"], control["N"]
    if nr == 0 or nc == 0:
        sys.exit("Not enough scoreable PDFs fetched (no images/tables extracted).")

    print("\n=== figure/table recall (flag = severity >= CONCERN) ===")
    print(f"retracted N={nr} (imgs={retracted['with_images']}, "
          f"tables={retracted['with_tables']})  "
          f"control N={nc} (imgs={control['with_images']}, "
          f"tables={control['with_tables']})")
    print(f"{'det':<5}{'recall%':>10}{'FP%':>10}{'LR+':>10}")
    for k in ALL_KEYS:
        rec = 100 * retracted[k] / nr
        fp = 100 * control[k] / nc
        lrp = "inf" if fp == 0 and rec > 0 else (f"{rec / fp:.2f}" if fp else "0")
        print(f"{k:<5}{rec:>9.1f}{fp:>10.1f}{lrp:>10}")
    print(
        "\nImage forensics (F1-F7) + Carlisle (C1) run on extracted PMC OA "
        "figures/tables. A hit = an anomaly signal worth investigation, with "
        "innocent explanations attached. Aggregate only; no per-paper verdicts."
    )


if __name__ == "__main__":
    main()
