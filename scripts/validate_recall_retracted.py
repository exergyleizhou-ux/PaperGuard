"""Sensitivity validation: text-layer detectors on PUBLIC retracted papers.

Ethical, reproducible recall test (extends the project's recall_test_v10
methodology). We compare PaperGuard's text-layer detectors on two cohorts:

  * RETRACTED — works flagged ``is_retracted:true`` by OpenAlex (public,
    already-retracted literature; no living-author targeting).
  * CONTROL   — non-retracted Open-Access works (same era).

Both cohorts use Open-Access abstracts only (via OpenAlex
``abstract_inverted_index``). We run the abstract-applicable text detectors:
T4 (tortured phrases), T6 (lexical AI/paper-mill), T9 (learned classifier),
and report, per detector and combined:

    recall      = % of RETRACTED flagged
    FP rate     = % of CONTROL flagged
    LR+         = recall / FP_rate   (>1 means discriminative)

Honesty caveats (printed in the output):
  * Abstracts only — the numeric/statistical and image detectors (PaperGuard's
    strongest families) need full data/tables/figures and are NOT exercised here.
  * Retractions have many causes (data fabrication, ethics, duplicate, honest
    error); most are NOT text-layer-detectable, so text-only recall is expected
    to be modest. This bounds the *text layer*, not the whole tool.
  * Aggregate only. No titles, authors, DOIs, or per-paper verdicts.

Usage:
    .venv/Scripts/python.exe scripts/validate_recall_retracted.py --n 200
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

OPENALEX = "https://api.openalex.org/works"


def _reconstruct(inv: dict | None) -> str:
    if not inv:
        return ""
    pos: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            pos.append((i, word))
    pos.sort()
    return " ".join(w for _, w in pos)


def fetch(filter_str: str, n: int) -> list[str]:
    out: list[str] = []
    cursor = "*"
    with httpx.Client(timeout=40.0) as client:
        while len(out) < n and cursor:
            r = client.get(
                OPENALEX,
                params={
                    "filter": filter_str,
                    "per_page": 200,
                    "cursor": cursor,
                    "select": "abstract_inverted_index",
                    "mailto": "research@example.org",
                },
            )
            r.raise_for_status()
            data = r.json()
            for w in data.get("results", []):
                ab = _reconstruct(w.get("abstract_inverted_index"))
                if ab and len(ab.split()) >= 120:
                    out.append(ab)
                if len(out) >= n:
                    break
            cursor = data.get("meta", {}).get("next_cursor")
            time.sleep(0.2)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200, help="samples per cohort")
    args = ap.parse_args()

    os.environ["PAPERGUARD_ML_CHECK"] = "1"  # enable T9
    os.environ["PAPERGUARD_T6_ABSTRACT_ONLY"] = "1"  # T6 abstract mode

    from paperguard.core.types import Severity
    from paperguard.detectors.t4_tortured_phrases import T4TorturedPhrasesDetector
    from paperguard.detectors.t6_ai_text_heuristic import T6AITextHeuristicDetector
    from paperguard.detectors.t9_classifier import T9ClassifierDetector

    detectors = {
        "T4": T4TorturedPhrasesDetector(),
        "T6": T6AITextHeuristicDetector(),
        "T9": T9ClassifierDetector(),
    }

    print(f"fetching {args.n} retracted + {args.n} control abstracts ...")
    retracted = fetch("is_retracted:true,has_abstract:true", args.n)
    control = fetch(
        "is_retracted:false,has_abstract:true,from_publication_date:2018-01-01", args.n
    )
    print(f"  retracted={len(retracted)}  control={len(control)}")

    def flagged(text: str, cut: Severity) -> dict[str, bool]:
        res = {}
        any_hit = False
        for name, det in detectors.items():
            r = det.detect(text)
            hit = any(f.severity >= cut for f in r.findings)
            res[name] = hit
            any_hit = any_hit or hit
        res["ANY"] = any_hit
        return res

    def cohort_rates(texts: list[str], cut: Severity) -> dict[str, float]:
        counts = {k: 0 for k in ["T4", "T6", "T9", "ANY"]}
        for t in texts:
            for k, v in flagged(t, cut).items():
                counts[k] += int(v)
        n = max(1, len(texts))
        return {k: 100 * c / n for k, c in counts.items()}

    for cut in (Severity.CONCERN, Severity.SUSPICIOUS):
        rec = cohort_rates(retracted, cut)
        fp = cohort_rates(control, cut)
        print(f"\n=== flag = severity >= {cut.name} ===")
        print(f"{'det':<5}{'recall%(retracted)':>20}{'FP%(control)':>16}{'LR+':>10}")
        for k in ["T4", "T6", "T9", "ANY"]:
            lrp = (rec[k] / fp[k]) if fp[k] > 0 else float("inf")
            lrp_s = "inf" if lrp == float("inf") else f"{lrp:.2f}"
            print(f"{k:<5}{rec[k]:>19.1f}{fp[k]:>16.1f}{lrp_s:>10}")

    print(
        "\nCaveats: abstracts only (numeric/image detectors not exercised); "
        "most retractions are not text-layer-detectable; aggregate only, "
        "no per-paper verdicts."
    )


if __name__ == "__main__":
    main()
