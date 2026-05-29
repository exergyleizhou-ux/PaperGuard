"""Calibrate T9's specificity on real Open-Access papers (false-positive study).

This is a **research/calibration** script (not part of the shipped package). It
measures how often the T9 LLM-text classifier flags *real, human-led*
Open-Access abstracts — i.e. T9's false-positive behaviour on out-of-domain
text (T9 was trained on HC3, English Q&A; here we test it on materials /
environmental science abstracts).

Ethics + data handling (matches the project's iron rule):
  * Open-Access works only (abstracts via the free OpenAlex API).
  * Aggregate statistics ONLY. No raw abstract text, no author names, and no
    per-paper verdicts are printed or committed. We never label any individual
    paper as "AI-written" — T9 emits a probability, never a verdict.
  * The institution is a *data source* for a specificity check, not a target.
    Pass any ROR/OpenAlex id via --institution to reuse this on any corpus.

Usage:
    .venv/Scripts/python.exe scripts/calibrate_t9_oa.py \
        --institution I1284762954 --max 400

Interpretation caveat (important): a "flag" on a 2025 abstract is NOT
necessarily a false positive. Many authors legitimately polish English
abstracts with an LLM (often disclosed/allowed). So a non-zero flag rate mixes
(a) genuine out-of-domain false positives and (b) real LLM-assisted writing.
This study bounds specificity; it does not accuse anyone.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OPENALEX = "https://api.openalex.org/works"
# T9 tiers (mirror the detector's cut-points).
NOTE, CONCERN, SUSPICIOUS = 0.50, 0.70, 0.90
MIN_WORDS = 150  # detector applicability floor


def _reconstruct_abstract(inv: dict | None) -> str:
    """Rebuild plain text from OpenAlex abstract_inverted_index."""
    if not inv:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def fetch_oa_abstracts(institution: str, max_n: int) -> list[str]:
    """Page through OpenAlex OA works (last year) and return abstracts."""
    flt = (
        f"institutions.id:{institution},is_oa:true,"
        "from_publication_date:2025-05-29,has_abstract:true"
    )
    out: list[str] = []
    cursor = "*"
    with httpx.Client(timeout=40.0) as client:
        while len(out) < max_n and cursor:
            r = client.get(
                OPENALEX,
                params={
                    "filter": flt,
                    "per_page": 200,
                    "cursor": cursor,
                    "select": "abstract_inverted_index",
                    "mailto": "research@example.org",
                },
            )
            r.raise_for_status()
            data = r.json()
            for w in data.get("results", []):
                ab = _reconstruct_abstract(w.get("abstract_inverted_index"))
                if ab:
                    out.append(ab)
                if len(out) >= max_n:
                    break
            cursor = data.get("meta", {}).get("next_cursor")
            time.sleep(0.2)  # be polite to the free API
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--institution", default="I1284762954", help="OpenAlex institution id")
    ap.add_argument("--max", type=int, default=400)
    args = ap.parse_args()

    from paperguard.detectors.t9_classifier import _load_model

    model = _load_model()
    if model is None:
        sys.exit("T9 model artifact not found — run scripts/train_t9_classifier.py first")

    print(f"fetching up to {args.max} OA abstracts for {args.institution} ...")
    abstracts = fetch_oa_abstracts(args.institution, args.max)
    print(f"  got {len(abstracts)} abstracts with text")

    probs: list[float] = []
    eligible_probs: list[float] = []  # >= MIN_WORDS (what the detector would score)
    for ab in abstracts:
        p = model.prob_llm(ab)
        probs.append(p)
        if len(ab.split()) >= MIN_WORDS:
            eligible_probs.append(p)

    def _summary(label: str, ps: list[float]) -> None:
        if not ps:
            print(f"\n[{label}] no samples")
            return
        n = len(ps)
        note = sum(p >= NOTE for p in ps)
        concern = sum(p >= CONCERN for p in ps)
        susp = sum(p >= SUSPICIOUS for p in ps)
        ps_sorted = sorted(ps)
        print(f"\n[{label}] N={n}")
        print(f"  mean p(LLM)      : {statistics.mean(ps):.4f}")
        print(f"  median p(LLM)    : {statistics.median(ps):.4f}")
        print(f"  90th pct         : {ps_sorted[int(0.9 * (n - 1))]:.4f}")
        print(f"  >= NOTE  (0.50)  : {note:4d}  ({100 * note / n:.1f}%)")
        print(f"  >= CONCERN(0.70) : {concern:4d}  ({100 * concern / n:.1f}%)")
        print(f"  >= SUSP  (0.90)  : {susp:4d}  ({100 * susp / n:.1f}%)  <- flag rate at ship threshold")

    _summary("ALL abstracts", probs)
    _summary("detector-eligible (>=150 words)", eligible_probs)
    print(
        "\nNote: flags mix out-of-domain false positives AND genuine "
        "LLM-assisted writing; this bounds specificity, it does not accuse."
    )


if __name__ == "__main__":
    main()
