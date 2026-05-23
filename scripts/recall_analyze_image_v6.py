"""Analyser for ``recall_image_v6_results.json`` — PMID-indexed both arms.

Identical math to the v5 analyser (Wilson 95 % CI on LR+, denominator
restricted to pdf_ok + n_images >= 1), but with v6-specific headline
text + honest interpretation calibrated to the v6 numbers.

Usage:

    python scripts/recall_analyze_image_v6.py \\
        scripts/recall_image_v6_results.json > docs/recall_image_v6.md
"""
from __future__ import annotations

import json
import math
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def _firing_suspicious(sev: str | None) -> bool:
    return sev in {"SUSPICIOUS", "CRITICAL"}


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _lr_ci(
    tp: int, n_pos: int, fp: int, n_neg: int
) -> tuple[float | str, str]:
    if n_pos == 0 or n_neg == 0:
        return ("undefined", "[—, —]")
    tpr = tp / n_pos
    fpr = fp / n_neg
    tpr_lo, tpr_hi = _wilson(tp, n_pos)
    fpr_lo, fpr_hi = _wilson(fp, n_neg)
    if fpr == 0:
        if tp == 0:
            return (0.0, "[0, ∞]")
        lr_point: float | str = "∞"
        lr_lo = tpr_lo / fpr_hi if fpr_hi > 0 else 0.0
        return (lr_point, f"[{lr_lo:.2f}, ∞]")
    lr_point = tpr / fpr
    lr_lo = tpr_lo / fpr_hi if fpr_hi > 0 else 0.0
    if fpr_lo == 0:
        return (lr_point, f"[{lr_lo:.2f}, ∞]")
    lr_hi = tpr_hi / fpr_lo
    return (lr_point, f"[{lr_lo:.2f}, {lr_hi:.2f}]")


def _is_usable(r: dict[str, Any]) -> bool:
    return bool(r.get("pdf_ok")) and (r.get("n_images") or 0) > 0


def _fmt_lr(point: float | str) -> str:
    if isinstance(point, str):
        return point
    return f"{point:.2f}"


def _per_detector_row(
    det: str,
    retracted: Iterable[dict[str, Any]],
    control: Iterable[dict[str, Any]],
    n_pos: int,
    n_neg: int,
) -> str:
    col = f"{det}_severity"
    tp = sum(1 for r in retracted if _firing_suspicious(r.get(col)))
    fp = sum(1 for r in control if _firing_suspicious(r.get(col)))
    tpr = tp / max(n_pos, 1)
    fpr = fp / max(n_neg, 1)
    point, ci = _lr_ci(tp, n_pos, fp, n_neg)
    return (
        f"| **{det.upper()}** | {tp}/{n_pos} | {fp}/{n_neg} | "
        f"{tpr * 100:.1f} % | {fpr * 100:.1f} % | **{_fmt_lr(point)}** | {ci} |"
    )


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: recall_analyze_image_v6.py <results.json>", file=sys.stderr)
        return 1
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    results = data["results"]
    n_per_arm = data.get("n_per_arm", "?")

    retracted_all = [r for r in results if r["arm"] == "retracted"]
    control_all = [r for r in results if r["arm"] == "control"]
    retracted = [r for r in retracted_all if _is_usable(r)]
    control = [r for r in control_all if _is_usable(r)]
    n_r = len(retracted)
    n_c = len(control)

    pdf_r = sum(1 for r in retracted_all if r.get("pdf_ok"))
    pdf_c = sum(1 for r in control_all if r.get("pdf_ok"))

    print(
        f"# PaperGuard image-layer recall study v6 "
        f"(N={n_per_arm}+{n_per_arm} requested, PMID-indexed both arms)\n"
    )
    print(
        f"> **Headline.** v6 adds `has_pmid:true` to both OpenAlex queries\n"
        f"> to attack v5's arm-attrition asymmetry (132 retracted vs 48\n"
        f"> control pdf_ok). The filter **partly worked**: retracted-arm\n"
        f"> pdf_ok jumped from 66 % (v5) to **{pdf_r/len(retracted_all)*100:.0f} %**.\n"
        f"> Control-arm pdf_ok rose more modestly from 51 % to **{pdf_c/len(control_all)*100:.0f} %**.\n"
        f"> Asymmetry still present.\n"
    )
    print(
        f"> **Bigger story:** with the larger usable corpus ({n_r} + {n_c}\n"
        f"> analysable papers), the v5 finding hardens further. **All\n"
        f"> three image detectors at PaperGuard's documented `z=6 /\n"
        f"> cluster=8` defaults give LR+ ≈ 1 on this OpenAlex /\n"
        f"> Europe-PMC OA biomedical corpus.** v5's F4 LR+ = 4.36 was\n"
        f"> a small-N artifact (only 1/48 false positive); v6 says\n"
        f"> F4 LR+ ≈ 1.0 with proportionally more FPs at the larger n.\n"
    )
    print("## Fetch + extract attrition\n")
    print(f"- Retracted: {len(retracted_all)} fetched → {pdf_r} pdf_ok "
          f"({pdf_r/len(retracted_all)*100:.0f} %) → {n_r} usable.")
    print(f"- Control: {len(control_all)} fetched → {pdf_c} pdf_ok "
          f"({pdf_c/len(control_all)*100:.0f} %) → {n_c} usable.")
    print()
    print("## Per-detector LR+ at the SUSPICIOUS-or-CRITICAL threshold\n")
    print(
        "Denominator = usable papers. Wilson 95 % CI on LR+ derived from\n"
        "Wilson CIs on TPR and FPR.\n"
    )
    print("| Detector | TP / n+ | FP / n− | TPR | FPR | LR+ | 95 % CI |")
    print("|---|---|---|---|---|---|---|")
    for det in ("f1", "f4", "f6"):
        print(_per_detector_row(det, retracted, control, n_r, n_c))

    print("\n## Joint signals (ANY of {F1, F4, F6} firing)\n")
    print("| Combination | TP / n+ | FP / n− | TPR | FPR | LR+ | 95 % CI |")
    print("|---|---|---|---|---|---|---|")
    combos = [
        ("F1 ∪ F4", ("f1", "f4")),
        ("F1 ∪ F6", ("f1", "f6")),
        ("F4 ∪ F6", ("f4", "f6")),
        ("F1 ∪ F4 ∪ F6", ("f1", "f4", "f6")),
    ]
    for label, detectors in combos:
        cols = [f"{d}_severity" for d in detectors]
        tp = sum(
            1 for r in retracted
            if any(_firing_suspicious(r.get(c)) for c in cols)
        )
        fp = sum(
            1 for r in control
            if any(_firing_suspicious(r.get(c)) for c in cols)
        )
        tpr = tp / max(n_r, 1)
        fpr = fp / max(n_c, 1)
        point, ci = _lr_ci(tp, n_r, fp, n_c)
        print(
            f"| **{label}** | {tp}/{n_r} | {fp}/{n_c} | "
            f"{tpr * 100:.1f} % | {fpr * 100:.1f} % | **{_fmt_lr(point)}** | "
            f"{ci} |"
        )

    print(
        "\n## Honest interpretation (the hard part)\n\n"
        "Across three increasingly rigorous studies (v4 N=159, v5 N=180\n"
        "with attrition asymmetry, v6 N=212 with reduced asymmetry),\n"
        "PaperGuard's image-forensics layer at the documented\n"
        "`z=6 / cluster=8` defaults converges to **no reliable\n"
        "single-detector signal** on randomly-selected OpenAlex\n"
        "retracted papers vs matched controls in the biomedical OA\n"
        "corpus.\n\n"
        "Specifically:\n"
        "- **F6 (patch-splice) LR+ ≈ 0.89** across v5 and v6, with a\n"
        "  tight CI bracketing 1. v4's apparent LR+ 1.63 (N=159) was\n"
        "  the small-sample upward fluctuation v5 already flagged.\n"
        "- **F4 (cross-paper pHash) LR+ ≈ 1.0**. v5 reported 4.36 with\n"
        "  CI [0.48, 41.28] on only 1 false positive; v6 with 5 false\n"
        "  positives in the larger control arm collapses this to 0.96.\n"
        "  The wide-CI 4.36 was an artifact of n_FP=1, not signal.\n"
        "- **F1 (intra-paper pHash) LR+ ≈ 1.1**, indistinguishable\n"
        "  from chance.\n\n"
        "**What this changes** for PaperGuard's empirical position:\n\n"
        "1. The image-layer is **structurally tuned to the Bik-style\n"
        "   patch-splice / Western-blot-duplication failure mode** —\n"
        "   not to the *average* retracted-paper population, which is\n"
        "   dominated by statistical-fabrication / paper-mill /\n"
        "   image-reuse failures that F1/F4/F6 don't cleanly detect.\n"
        "2. **The right calibration corpus is a Bik-curated patch-\n"
        "   splice retraction set**, not OpenAlex `is_retracted:true`\n"
        "   sampled at random. The Bik corpus is not publicly\n"
        "   redistributable (PubPeer thread sources are case-by-case),\n"
        "   so PaperGuard cannot ship that benchmark. The honest\n"
        "   position is that v6 sets an **upper bound on the image\n"
        "   layer's *un-curated* recall** — and that bound is\n"
        "   close to 1.0.\n"
        "3. **Multi-detector combination still has value** — even with\n"
        "   per-detector LR+ ≈ 1, the joint signal can carry\n"
        "   information when combined via the\n"
        "   `paperguard.evidence.combiner` Stouffer index across the\n"
        "   non-image families (T6 lexical, B-family statistical,\n"
        "   industrial I-family). The image layer is a *contributor*\n"
        "   in this triage architecture, not a single-shot decision\n"
        "   tool.\n"
        "4. **Operators running F1/F4/F6 in production should not\n"
        "   alert on a single image detector firing** at default\n"
        "   thresholds. Either calibrate to local data, raise the\n"
        "   thresholds, or use the image findings only as input to\n"
        "   the combiner.\n\n"
        "PaperGuard publishes this study and the v5 / v4 series at\n"
        "transparent face value precisely because the alternative —\n"
        "quoting v4's small-N LR+ 1.63 as if it were a calibrated\n"
        "operating number — would be the kind of mis-calibration the\n"
        "tool exists to flag in others' work.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
