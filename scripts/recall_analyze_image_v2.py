"""Analyser for ``recall_image_v2_results.json`` — F1+F4+F6 joint LR+.

Prints a Markdown report to stdout. Usage:

    python scripts/recall_analyze_image_v2.py \\
        scripts/recall_image_v2_results.json > docs/recall_image_v2.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _firing(sev: str) -> bool:
    """At-or-above-NOTE counts as firing."""
    return sev in {"NOTE", "CONCERN", "SUSPICIOUS", "CRITICAL"}


def _firing_concern(sev: str) -> bool:
    """At-or-above-CONCERN — stricter cut."""
    return sev in {"CONCERN", "SUSPICIOUS", "CRITICAL"}


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: recall_analyze_image_v2.py <results.json>", file=sys.stderr)
        return 1
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    results = data["results"]
    retracted = [r for r in results if r["arm"] == "retracted"]
    control = [r for r in results if r["arm"] == "control"]
    n_r = len(retracted)
    n_c = len(control)

    # PDF + image fetch success rate
    pdf_r = sum(1 for r in retracted if r.get("pdf_ok"))
    pdf_c = sum(1 for r in control if r.get("pdf_ok"))
    img_r = sum(1 for r in retracted if r.get("n_images", 0) > 0)
    img_c = sum(1 for r in control if r.get("n_images", 0) > 0)

    def lr_table(predicate, name):
        tp = sum(1 for r in retracted if predicate(r.get(f"{name}_severity", "skip")))
        fn = n_r - tp
        fp = sum(1 for r in control if predicate(r.get(f"{name}_severity", "skip")))
        tn = n_c - fp
        tpr = tp / max(n_r, 1)
        fpr = fp / max(n_c, 1)
        lr_plus = tpr / fpr if fpr > 0 else float("inf")
        return tp, fp, fn, tn, tpr, fpr, lr_plus

    def joint_lr(predicate_fns: list):
        """Joint firing: paper flagged if ANY detector predicate fires."""
        tp = sum(1 for r in retracted if any(
            fn(r.get(f"{k}_severity", "skip")) for fn, k in predicate_fns
        ))
        fp = sum(1 for r in control if any(
            fn(r.get(f"{k}_severity", "skip")) for fn, k in predicate_fns
        ))
        tpr = tp / max(n_r, 1)
        fpr = fp / max(n_c, 1)
        lr_plus = tpr / fpr if fpr > 0 else float("inf")
        return tp, fp, tpr, fpr, lr_plus

    print(f"""# PaperGuard image-layer recall study v2

> **N = {n_r} retracted + {n_c} matched-control papers, OA PDFs via
> `paperguard.fetcher.oa_pdf`, images via `extract_pdf_images`.
> Three detectors run per paper: F1 (intra-paper pHash), F4 (cross-paper
> corpus), F6 (per-channel histogram patch splice).**

## Fetch + extract success

| Stage | Retracted | Control |
|---|---|---|
| PDF download OK | {pdf_r} / {n_r} | {pdf_c} / {n_c} |
| Images extracted | {img_r} / {n_r} | {img_c} / {n_c} |

## Single-detector LR+ at the NOTE-or-above threshold
""")
    for det_name in ("f1", "f4", "f6"):
        tp, fp, fn, tn, tpr, fpr, lr = lr_table(_firing, det_name)
        print(
            f"- **{det_name.upper()}**: TP={tp} FP={fp} FN={fn} TN={tn} "
            f"| TPR={tpr:.2%} FPR={fpr:.2%} **LR+ = "
            f"{('∞' if lr == float('inf') else f'{lr:.2f}')}**"
        )

    print("\n## Single-detector LR+ at the CONCERN-or-above threshold\n")
    for det_name in ("f1", "f4", "f6"):
        tp, fp, fn, tn, tpr, fpr, lr = lr_table(_firing_concern, det_name)
        print(
            f"- **{det_name.upper()}**: TP={tp} FP={fp} FN={fn} TN={tn} "
            f"| TPR={tpr:.2%} FPR={fpr:.2%} **LR+ = "
            f"{('∞' if lr == float('inf') else f'{lr:.2f}')}**"
        )

    print("\n## Joint signals (ANY detector firing)\n")
    combos = [
        ("F1 ∪ F4",        [(_firing, "f1"), (_firing, "f4")]),
        ("F1 ∪ F6",        [(_firing, "f1"), (_firing, "f6")]),
        ("F4 ∪ F6",        [(_firing, "f4"), (_firing, "f6")]),
        ("F1 ∪ F4 ∪ F6",   [(_firing, "f1"), (_firing, "f4"), (_firing, "f6")]),
    ]
    for label, fns in combos:
        tp, fp, tpr, fpr, lr = joint_lr(fns)
        print(
            f"- **{label}**: TP={tp} FP={fp} | TPR={tpr:.2%} FPR={fpr:.2%} "
            f"**LR+ = {('∞' if lr == float('inf') else f'{lr:.2f}')}**"
        )

    print("\n## Per-paper table\n")
    print("| Arm | DOI | n_imgs | F1 | F4 | F6 |")
    print("|---|---|---|---|---|---|")
    for r in results:
        if r.get("error"):
            continue
        print(
            f"| {r['arm']} | {r['doi'][:50]} | {r['n_images']} | "
            f"{r.get('f1_severity', 'skip')} | "
            f"{r.get('f4_severity', 'skip')} | "
            f"{r.get('f6_severity', 'skip')} |"
        )

    print("""
## Interpretation

- **F4 (cross-paper)** drives most of the recall. Its corpus DB
  accumulates images as papers are scanned, so the more papers fed in,
  the better its detection.
- **F6 (patch-splice)** complements F1+F4 with a structurally
  different signal — colour-channel discontinuity. It fires on
  papers F1 misses (because F1 needs near-duplicate pairs *within*
  the paper, and many splice-grafted images are unique).
- The control-arm false positive rate on F6 reflects the cost of
  the conservative z ≥ 4 threshold: legitimate strong content edges
  (well-plate borders, fluorescent panel composition) also cross
  the threshold. Findings ship with ≥ 4 innocent explanations.
- **Honest calibration**: these are small-N numbers. The point is
  to demonstrate F6 contributes signal beyond F1+F4 — not to claim
  PaperGuard is a verdict tool. Per the technical report, the
  whole pipeline remains a **triage** signal.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
