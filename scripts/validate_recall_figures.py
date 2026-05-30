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


def epmc_pmcids(query: str, want: int) -> list[str]:
    """Return PMCIDs (with full text in EPMC) matching a Europe PMC query."""
    ids: list[str] = []
    cursor = "*"
    with httpx.Client(timeout=40.0) as client:
        while len(ids) < want and cursor:
            r = client.get(
                EPMC_SEARCH,
                params={
                    "query": query,
                    "format": "json",
                    "pageSize": 100,
                    "cursorMark": cursor,
                    "resultType": "lite",
                },
            )
            r.raise_for_status()
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
    args = ap.parse_args()

    from paperguard.core.types import Severity
    from paperguard.evidence.figure_pipeline import run_figure_pipeline
    from paperguard.fetcher.oa_pdf import _pmc_pdf_url, _try_download

    def run_cohort(query: str, label: str, tmp: Path) -> dict[str, int]:
        print(f"\n[{label}] searching Europe PMC ...", flush=True)
        pmcids = epmc_pmcids(query, args.n * 6)
        print(f"  {len(pmcids)} OA candidates; downloading up to {args.n} PDFs ...",
              flush=True)
        counts = {k: 0 for k in ALL_KEYS}
        got = 0
        n_with_images = 0
        n_with_tables = 0
        for pmcid in pmcids:
            if got >= args.n:
                break
            pdf_path = tmp / f"{pmcid}.pdf"
            ok, _sha_or_err, _ctype = _try_download(_pmc_pdf_url(pmcid), pdf_path)
            if not ok:
                continue
            work = tmp / f"work_{pmcid}"
            try:
                res = run_figure_pipeline(pdf_path, work_dir=work)
            except Exception:
                pdf_path.unlink(missing_ok=True)
                continue
            # only count papers we could actually extract SOMETHING from
            if not res.image_paths and res.n_baseline_tables == 0:
                pdf_path.unlink(missing_ok=True)
                continue
            got += 1
            n_with_images += int(bool(res.image_paths))
            n_with_tables += int(res.n_baseline_tables > 0)
            flags = {k: False for k in ALL_KEYS}
            for r in res.results:
                if r.detector_id in flags and any(
                    f.severity >= Severity.CONCERN for f in r.findings
                ):
                    flags[r.detector_id] = True
            flags["ANY"] = any(flags[k] for k in (*IMAGE_DETECTORS, "C1"))
            for k in ALL_KEYS:
                counts[k] += int(flags[k])
            pdf_path.unlink(missing_ok=True)
            print(f"    {got}/{args.n} scored "
                  f"(imgs={len(res.image_paths)}, tables={res.n_baseline_tables})",
                  flush=True)
            time.sleep(0.2)
        counts["N"] = got
        counts["with_images"] = n_with_images
        counts["with_tables"] = n_with_tables
        print(f"  scored {got} papers "
              f"({n_with_images} had images, {n_with_tables} had baseline tables)",
              flush=True)
        return counts

    with tempfile.TemporaryDirectory(prefix="pg_figrecall_") as td:
        tmp = Path(td)
        retracted = run_cohort(
            'PUB_TYPE:"Retracted Publication" AND OPEN_ACCESS:Y AND IN_EPMC:Y',
            "RETRACTED", tmp,
        )
        control = run_cohort(
            'OPEN_ACCESS:Y AND IN_EPMC:Y AND NOT PUB_TYPE:"Retracted Publication" '
            'AND FIRST_PDATE:[2018-01-01 TO 2023-12-31]',
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
