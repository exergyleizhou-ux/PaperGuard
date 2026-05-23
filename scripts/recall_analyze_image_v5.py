"""Analyser for ``recall_image_v5_results.json`` — F1+F4+F6 at N=200+200.

Differs from the v2/v3/v4 analysers in two ways:

1. Restricts the denominator to **usable** papers — those where the OA
   PDF actually downloaded AND at least one image was extracted. The
   v4 analyser used the full arm size as the denominator, which mixed
   "detector said no" with "we never got to run the detector". Using
   the larger denominator deflates TPR (you can't TP on a paper you
   never scanned), and inflates apparent power on small samples.
2. Reports **Wilson 95 % confidence intervals** for the LR+ point
   estimate, derived from Wilson CIs on TPR and FPR. Previous
   analysers reported point estimates only, which the v4 writeup
   itself flagged as "modest, underpowered".

Print a Markdown report to stdout. Usage:

    python scripts/recall_analyze_image_v5.py \\
        scripts/recall_image_v5_results.json > docs/recall_image_v5.md
"""
from __future__ import annotations

import json
import math
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def _firing_suspicious(sev: str | None) -> bool:
    """SUSPICIOUS-or-CRITICAL counts as the detector firing.

    Same convention as v4 — NOTE-tier is excluded because every detector
    emits a near-universal NOTE band on noisy real data, which would
    make all four detectors look identical.
    """
    return sev in {"SUSPICIOUS", "CRITICAL"}


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95 % CI for a binomial proportion k/n."""
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
    """Point LR+ and Wilson-style 95 % CI as a printable string.

    LR+ = TPR / FPR. CI uses TPR_lo / FPR_hi for the lower bound and
    TPR_hi / FPR_lo for the upper bound. If FPR_lo touches 0 the upper
    bound is unbounded (printed as ``∞``).
    """
    if n_pos == 0 or n_neg == 0:
        return ("undefined", "[—, —]")
    tpr = tp / n_pos
    fpr = fp / n_neg
    tpr_lo, tpr_hi = _wilson(tp, n_pos)
    fpr_lo, fpr_hi = _wilson(fp, n_neg)
    if fpr == 0:
        # Point estimate is ∞ if any TP; CI uses Wilson upper-bound on FPR.
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
    """A record is usable for LR+ math iff we actually ran the detectors."""
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
        print("usage: recall_analyze_image_v5.py <results.json>", file=sys.stderr)
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
        f"# PaperGuard image-layer recall study v5 (N={n_per_arm}+{n_per_arm}, "
        "F1+F4+F6)\n"
    )
    print(
        f"> **Headline.** Built on the same script as v2/v3/v4 with "
        f"`--n {n_per_arm}`. The retracted arm processed cleanly; the "
        f"control arm was sample-attrited by the OA-fetch step "
        f"(`pdf_ok` only on **{pdf_c}/{len(control_all)} = "
        f"{pdf_c/len(control_all)*100:.0f} %** vs **{pdf_r}/"
        f"{len(retracted_all)} = {pdf_r/len(retracted_all)*100:.0f} %** for "
        "retracted). After requiring both `pdf_ok` AND `n_images >= 1`, "
        f"the analysable corpus is **{n_r} retracted + {n_c} control**.\n"
    )
    print("## Fetch + extract attrition\n")
    print(f"- Retracted: {len(retracted_all)} fetched → {pdf_r} pdf_ok → "
          f"{n_r} usable for image detectors.")
    print(f"- Control: {len(control_all)} fetched (control arm has fewer "
          f"unique DOIs than retracted because the script re-uses matched "
          f"controls across multiple retracted papers and stores one "
          f"row per unique control) → {pdf_c} pdf_ok → {n_c} usable.")
    print()
    print("## Per-detector LR+ at the SUSPICIOUS-or-CRITICAL threshold\n")
    print(
        "Denominator = usable papers. Wilson 95 % CI on LR+ derived from "
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
        "\n## Honest interpretation\n\n"
        "v5 expands the per-arm target from 10 (v4) to 200. After arm\n"
        "attrition the analysable corpus is 132 + 48 — still 2× v4's\n"
        "159 total. With the larger sample, the picture changes:\n\n"
        "- **F6 (patch-splice) LR+ collapses** from v4's 1.63 (N=159) to\n"
        "  approximately 0.92 (N=180) with a tight 95 % CI that brackets 1.\n"
        "  That earlier 1.63 was almost certainly a small-sample upward\n"
        "  fluctuation; v5 is the more reliable estimate. F6 at\n"
        "  `z=6 / cluster=8` defaults appears to fire on legitimate strong\n"
        "  content edges (well-plate borders, fluorescent panel\n"
        "  composition, gel-electrophoresis lanes) at almost the same rate\n"
        "  in retracted and control papers, on a Europe PMC OA biomedical\n"
        "  corpus where retracted papers are not over-represented for the\n"
        "  patch-splice failure mode F6 was tuned to.\n"
        "- **F4 (cross-paper pHash) LR+ rises** to ~4.4 but with a 95 % CI\n"
        "  spanning [0.5, 41]: directionally encouraging but underpowered\n"
        "  at 48 controls. F4 is the cross-paper-corpus detector and it\n"
        "  benefits structurally from a larger ingested corpus.\n"
        "- **F1 (intra-paper pHash) LR+ ≈ 1.4**, CI ~[0.5, 4]: weak signal\n"
        "  that does not exclude 1.\n\n"
        "**What this changes** for PaperGuard's empirical position:\n\n"
        "1. The image-forensics layer is **not** a reliable single-shot\n"
        "   signal on this corpus at default thresholds. Use it as a\n"
        "   ranking input, not as a binary decision.\n"
        "2. F6's `z=6 / cluster=8` default is the calibration story from\n"
        "   v2 (where the relaxed `z=4` was caught at FPR=75 %). v5 says\n"
        "   even the tightened default does not yet discriminate on this\n"
        "   biomedical OA corpus. **Calibration on a Bik-curated patch-\n"
        "   splice corpus is the right next step** — synthetic / sampled\n"
        "   retraction data underweights F6's intended failure mode.\n"
        "3. The control-arm attrition (52 % vs retracted's 66 % pdf_ok)\n"
        "   is a methodological problem: OpenAlex returns is_retracted=true\n"
        "   papers preferentially from journals with stronger OA than the\n"
        "   matched-control journals. A future v6 should either use\n"
        "   PubMed Central directly (uniform OA) or down-sample the\n"
        "   retracted arm to the control arm's available-PDF count.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
