"""Full-TEXT recall validation against public retracted papers (Europe PMC).

Exercises the detectors that actually catch fabrication on full text — above
all **B4 statcheck**, which recomputes every reported p-value and flags
statistically impossible ones. Full text and the retracted/control cohorts both
come from Europe PMC Open-Access, which exposes a `PUB_TYPE:"Retracted
Publication"` filter (OpenAlex's is_retracted has almost no OA full text).

Cohorts (public, no living-author targeting):
  * RETRACTED — Europe PMC `PUB_TYPE:"Retracted Publication"`, OA, in-EPMC.
  * CONTROL   — Europe PMC OA research-articles, in-EPMC, not retracted.

Reports per detector + combined: recall (retracted flagged), FP (control
flagged), LR+ = recall/FP. Aggregate only — no titles, IDs, authors, verdicts.

Usage:
    .venv/Scripts/python.exe scripts/validate_recall_fulltext.py --n 40
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

EPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


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
    ap.add_argument("--n", type=int, default=40, help="full-text samples per cohort")
    args = ap.parse_args()

    os.environ["PAPERGUARD_ML_CHECK"] = "1"

    from paperguard.core.types import Severity
    from paperguard.detectors.b4_statcheck import B4StatcheckDetector
    from paperguard.detectors.t4_tortured_phrases import T4TorturedPhrasesDetector
    from paperguard.detectors.t6_ai_text_heuristic import T6AITextHeuristicDetector
    from paperguard.detectors.t9_classifier import T9ClassifierDetector
    from paperguard.fetcher.europepmc import fetch_full_text_xml, parse_jats

    detectors = {
        "B4": B4StatcheckDetector(),
        "T4": T4TorturedPhrasesDetector(),
        "T6": T6AITextHeuristicDetector(),
        "T9": T9ClassifierDetector(),
    }

    def run_cohort(query: str, label: str) -> dict[str, int]:
        print(f"\n[{label}] searching Europe PMC ...")
        # over-fetch ids: many full-text pulls will be short/empty
        pmcids = epmc_pmcids(query, args.n * 4)
        print(f"  {len(pmcids)} OA full-text candidates; scoring up to {args.n} ...")
        counts = {k: 0 for k in ["B4", "T4", "T6", "T9", "ANY"]}
        got = 0
        for pmcid in pmcids:
            if got >= args.n:
                break
            try:
                xml = fetch_full_text_xml(pmcid)
                text = parse_jats(xml)["full_text"] if xml else ""
            except Exception:
                text = ""
            if not text or len(text.split()) < 400:
                continue
            got += 1
            any_hit = False
            for name, det in detectors.items():
                res = det.detect(text)
                hit = any(f.severity >= Severity.CONCERN for f in res.findings)
                counts[name] += int(hit)
                any_hit = any_hit or hit
            counts["ANY"] += int(any_hit)
            time.sleep(0.1)
        counts["N"] = got
        print(f"  scored {got} full-text papers")
        return counts

    retracted = run_cohort('PUB_TYPE:"Retracted Publication" AND OPEN_ACCESS:Y AND IN_EPMC:Y', "RETRACTED")
    control = run_cohort(
        'OPEN_ACCESS:Y AND IN_EPMC:Y AND NOT PUB_TYPE:"Retracted Publication" '
        'AND FIRST_PDATE:[2018-01-01 TO 2023-12-31]',
        "CONTROL",
    )

    nr, nc = retracted["N"], control["N"]
    if nr == 0 or nc == 0:
        sys.exit("Not enough full-text samples fetched.")

    print("\n=== full-text recall (flag = severity >= CONCERN) ===")
    print(f"retracted N={nr}  control N={nc}")
    print(f"{'det':<5}{'recall%':>10}{'FP%':>10}{'LR+':>10}")
    for k in ["B4", "T4", "T6", "T9", "ANY"]:
        rec = 100 * retracted[k] / nr
        fp = 100 * control[k] / nc
        lrp = "inf" if fp == 0 and rec > 0 else (f"{rec / fp:.2f}" if fp else "0")
        print(f"{k:<5}{rec:>9.1f}{fp:>10.1f}{lrp:>10}")
    print(
        "\nB4 statcheck recomputes reported p-values; a hit = a reported result "
        "is statistically inconsistent. Aggregate only; no per-paper verdicts."
    )


if __name__ == "__main__":
    main()
