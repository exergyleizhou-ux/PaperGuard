"""B4 (PaperGuard's statcheck implementation) cross-validation.

Ground-truth design
-------------------
The reference statcheck implementation (Nuijten et al. 2016, R package)
is not installable in this environment. Instead we build a
**synthetic ground-truth corpus** of N=40 statistical claims whose
correctness is determined analytically (via scipy independently of
B4's code path) before B4 sees them.

Each claim has three independent paths to its truth value:
1. The claim itself (`text`, `reported_p`).
2. The ground-truth p computed by *this script* via scipy's
   distribution CDFs.
3. Whether reported_p vs computed_p crosses the conventional 0.05
   reporting boundary (the "decision flip" — statcheck's primary
   error class).

We then run B4 on the same text and measure:
- **recall**: of the K ground-truth-flagged claims, how many did B4
  flag?
- **precision**: of the J claims B4 flagged, how many are actually
  inconsistent?
- **decision-flip agreement**: B4 should always flag claims whose
  computed_p crosses the 0.05 boundary in a direction opposite to
  reported_p (statcheck's "gross_error" class).

The result is an honest agreement number for PaperGuard's B4 module
against an independent scipy reference, even without statcheck-R
installed.

Outputs `scripts/crossval_statcheck_results.json`.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from scipy import stats

from paperguard.detectors.b4_statcheck import B4StatcheckDetector


@dataclass
class Claim:
    text: str
    test_type: str
    df1: float
    df2: float | None
    reported_stat: float
    reported_p: float
    inequality: str  # "=", "<", "≤"

    def computed_p(self) -> float:
        """Independent scipy reference. Two-tailed by default."""
        if self.test_type == "t":
            return float(
                2 * (1 - stats.t.cdf(abs(self.reported_stat), self.df1))
            )
        if self.test_type == "F":
            assert self.df2 is not None
            return float(
                1 - stats.f.cdf(self.reported_stat, self.df1, self.df2)
            )
        if self.test_type == "chi2":
            return float(1 - stats.chi2.cdf(self.reported_stat, self.df1))
        if self.test_type == "r":
            # r → t conversion: t = r * sqrt((n-2)/(1-r²)), df = n-2
            r = self.reported_stat
            df = self.df1
            t_val = r * ((df / max(1 - r * r, 1e-12)) ** 0.5)
            return float(
                2 * (1 - stats.t.cdf(abs(t_val), df))
            )
        if self.test_type == "z":
            return float(
                2 * (1 - stats.norm.cdf(abs(self.reported_stat)))
            )
        raise ValueError(f"unknown test_type {self.test_type}")

    def reported_decision(self) -> bool:
        """Was the reported p < 0.05?"""
        return self.reported_p < 0.05

    def computed_decision(self) -> bool:
        return self.computed_p() < 0.05

    def is_decision_flip(self) -> bool:
        """statcheck's 'gross_error' class — the most consequential
        statcheck error."""
        return self.reported_decision() != self.computed_decision()

    def is_p_inconsistent(self, tolerance: float = 0.005) -> bool:
        """Is reported_p materially different from computed_p?"""
        if self.inequality == "<":
            # "p < 0.05" is consistent iff computed_p < 0.05.
            return self.computed_p() > self.reported_p + tolerance
        return abs(self.reported_p - self.computed_p()) > tolerance


# ---------------------------------------------------------------------------
# The N=40 ground-truth corpus
# ---------------------------------------------------------------------------
# Mix of: consistent claims (B4 should NOT fire), p-decimal-error
# inconsistencies (B4 SHOULD fire), and decision-flip "gross_errors"
# (B4 must catch).
CORPUS: list[Claim] = [
    # ----- Consistent t-tests (B4 should not fire) -----
    Claim("t(98) = 2.45, p = 0.016", "t", 98, None, 2.45, 0.016, "="),
    Claim("t(120) = 3.10, p = 0.002", "t", 120, None, 3.10, 0.002, "="),
    Claim("t(50) = 1.21, p = 0.232", "t", 50, None, 1.21, 0.232, "="),
    Claim("t(200) = 0.42, p = 0.675", "t", 200, None, 0.42, 0.675, "="),
    Claim("t(30) = 4.55, p < 0.001", "t", 30, None, 4.55, 0.001, "<"),
    # ----- Inconsistent t-tests (B4 should fire) -----
    Claim("t(98) = 2.45, p = 0.005", "t", 98, None, 2.45, 0.005, "="),   # wrong: actual ≈ 0.016
    Claim("t(50) = 1.21, p = 0.04",  "t", 50, None, 1.21, 0.04, "="),    # decision flip
    Claim("t(120) = 3.10, p = 0.250", "t", 120, None, 3.10, 0.250, "="), # decision flip
    Claim("t(30) = 4.55, p = 0.15",   "t", 30,  None, 4.55, 0.15,  "="), # decision flip
    Claim("t(60) = 2.00, p = 0.001",  "t", 60,  None, 2.00, 0.001, "="), # actual ≈ 0.050
    # ----- Consistent F-tests -----
    Claim("F(3, 96) = 4.20, p = 0.008", "F", 3, 96, 4.20, 0.008, "="),
    Claim("F(2, 47) = 1.85, p = 0.168", "F", 2, 47, 1.85, 0.168, "="),
    Claim("F(1, 28) = 15.40, p < 0.001", "F", 1, 28, 15.40, 0.001, "<"),
    # ----- Inconsistent F-tests -----
    Claim("F(2, 47) = 1.85, p = 0.04",  "F", 2, 47, 1.85, 0.04, "="),   # decision flip
    Claim("F(3, 96) = 4.20, p = 0.15",  "F", 3, 96, 4.20, 0.15, "="),   # decision flip
    Claim("F(1, 28) = 15.40, p = 0.10", "F", 1, 28, 15.40, 0.10, "="),  # decision flip
    # ----- Consistent chi2 -----
    Claim("chi2(2) = 5.99, p = 0.050",  "chi2", 2, None, 5.99, 0.050, "="),
    Claim("chi2(4) = 9.49, p = 0.050",  "chi2", 4, None, 9.49, 0.050, "="),
    Claim("chi2(1) = 0.10, p = 0.752",  "chi2", 1, None, 0.10, 0.752, "="),
    # ----- Inconsistent chi2 -----
    Claim("chi2(2) = 5.99, p = 0.20",   "chi2", 2, None, 5.99, 0.20, "="), # decision flip
    Claim("chi2(4) = 9.49, p = 0.005",  "chi2", 4, None, 9.49, 0.005, "="), # wrong dir
    # ----- Consistent r -----
    Claim("r(48) = 0.30, p = 0.038",    "r", 48, None, 0.30, 0.038, "="),
    Claim("r(98) = 0.20, p = 0.046",    "r", 98, None, 0.20, 0.046, "="),
    Claim("r(28) = 0.50, p = 0.007",    "r", 28, None, 0.50, 0.007, "="),
    # ----- Inconsistent r -----
    Claim("r(48) = 0.30, p = 0.20",     "r", 48, None, 0.30, 0.20, "="),   # decision flip
    Claim("r(98) = 0.20, p = 0.001",    "r", 98, None, 0.20, 0.001, "="),  # wrong magnitude
    # ----- Consistent z -----
    Claim("z = 1.96, p = 0.050",        "z", 0, None, 1.96, 0.050, "="),
    Claim("z = 2.58, p = 0.010",        "z", 0, None, 2.58, 0.010, "="),
    Claim("z = 1.00, p = 0.317",        "z", 0, None, 1.00, 0.317, "="),
    # ----- Inconsistent z -----
    Claim("z = 1.96, p = 0.20",         "z", 0, None, 1.96, 0.20, "="),    # decision flip
    Claim("z = 1.00, p = 0.001",        "z", 0, None, 1.00, 0.001, "="),
    # ----- Edge cases B4 should handle gracefully -----
    Claim("t(98) = 2.45, p < .05",      "t", 98, None, 2.45, 0.05, "<"),
    Claim("F(1, 50) = 4.00, p = .049",  "F", 1, 50, 4.00, 0.049, "="),
    Claim("chi2(3) = 7.815, p = .050",  "chi2", 3, None, 7.815, 0.050, "="),
    # ----- Additional inconsistent (boundary) -----
    Claim("t(98) = 2.00, p = 0.001",    "t", 98, None, 2.00, 0.001, "="),  # actual ≈ 0.049
    Claim("F(2, 50) = 3.18, p = 0.001", "F", 2, 50, 3.18, 0.001, "="),     # actual ≈ 0.050
    # ----- Filler -----
    Claim("z = 0.50, p = 0.617",        "z", 0, None, 0.50, 0.617, "="),
    Claim("z = 3.29, p < 0.001",        "z", 0, None, 3.29, 0.001, "<"),
    Claim("t(10) = 2.23, p = 0.050",    "t", 10, None, 2.23, 0.050, "="),
    Claim("F(4, 100) = 2.46, p = 0.05", "F", 4, 100, 2.46, 0.05, "="),
    Claim("chi2(6) = 12.59, p = 0.050", "chi2", 6, None, 12.59, 0.050, "="),
]


def _run_b4(claims: list[Claim]) -> set[str]:
    """Run B4 over the concatenated corpus; return set of claim.text
    strings that B4 fired on."""
    # Concatenate with sentence boundaries so B4 can find each claim.
    text = "Stats: " + ". ".join(c.text for c in claims) + "."
    det = B4StatcheckDetector()
    result = det.detect(text)
    flagged: set[str] = set()
    if not result.applicable:
        return flagged
    for finding in result.findings:
        raw = finding.evidence.get("raw") or finding.summary
        for c in claims:
            if c.text in raw or c.text in finding.detail:
                flagged.add(c.text)
                break
    return flagged


def main() -> int:
    ground_truth_inconsistent: set[str] = set()
    ground_truth_flip: set[str] = set()
    per_claim: list[dict] = []

    for c in CORPUS:
        computed = c.computed_p()
        is_inc = c.is_p_inconsistent()
        is_flip = c.is_decision_flip()
        if is_inc:
            ground_truth_inconsistent.add(c.text)
        if is_flip:
            ground_truth_flip.add(c.text)
        per_claim.append(
            {
                "text": c.text,
                "test_type": c.test_type,
                "reported_p": c.reported_p,
                "computed_p_scipy": round(computed, 6),
                "is_decision_flip": is_flip,
                "is_p_inconsistent": is_inc,
            }
        )

    b4_flagged = _run_b4(CORPUS)

    # Per-claim metrics
    tp = sum(
        1 for c in CORPUS
        if c.text in ground_truth_inconsistent and c.text in b4_flagged
    )
    fp = sum(
        1 for c in CORPUS
        if c.text not in ground_truth_inconsistent and c.text in b4_flagged
    )
    fn = sum(
        1 for c in CORPUS
        if c.text in ground_truth_inconsistent and c.text not in b4_flagged
    )
    tn = sum(
        1 for c in CORPUS
        if c.text not in ground_truth_inconsistent
        and c.text not in b4_flagged
    )

    recall = tp / max(tp + fn, 1)
    precision = tp / max(tp + fp, 1)
    accuracy = (tp + tn) / len(CORPUS)

    # Decision-flip subset
    flip_caught = sum(1 for t in ground_truth_flip if t in b4_flagged)
    flip_recall = flip_caught / max(len(ground_truth_flip), 1)

    out = {
        "n_claims": len(CORPUS),
        "n_inconsistent_groundtruth": len(ground_truth_inconsistent),
        "n_decision_flip_groundtruth": len(ground_truth_flip),
        "b4_flagged": len(b4_flagged),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "recall_overall": round(recall, 4),
        "precision_overall": round(precision, 4),
        "accuracy_overall": round(accuracy, 4),
        "decision_flip_recall": round(flip_recall, 4),
        "per_claim": per_claim,
        "b4_flagged_texts": sorted(b4_flagged),
        "groundtruth_inconsistent_texts": sorted(ground_truth_inconsistent),
        "groundtruth_flip_texts": sorted(ground_truth_flip),
    }

    out_path = Path("scripts/crossval_statcheck_results.json")
    out_path.write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {out_path}", file=sys.stderr)
    print(
        f"\nN={len(CORPUS)} claims, "
        f"GT inconsistent={len(ground_truth_inconsistent)}, "
        f"GT decision-flip={len(ground_truth_flip)}",
        file=sys.stderr,
    )
    print(
        f"B4 flagged {len(b4_flagged)} | "
        f"TP={tp} FP={fp} FN={fn} TN={tn}",
        file=sys.stderr,
    )
    print(
        f"Recall={recall:.2%} Precision={precision:.2%} "
        f"Accuracy={accuracy:.2%} | Decision-flip recall={flip_recall:.2%}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
