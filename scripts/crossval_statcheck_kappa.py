"""Cohen's κ between PaperGuard B4 and statcheck-R on the N=41 corpus.

Pipeline:
  1. Dump the N=41 corpus from crossval_statcheck.py into a text file.
  2. Run scripts/crossval_statcheck_r.R against that text via Rscript;
     it writes scripts/crossval_statcheck_r_results.json.
  3. Re-run B4 on the same corpus.
  4. For each ground-truth claim, label both detectors as "fired" /
     "not fired" on (a) any inconsistency, (b) decision-flip class.
  5. Compute Cohen's κ over the two binary matrices.

Output: ``scripts/crossval_statcheck_kappa_results.json`` and a
human-readable summary on stdout.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from paperguard.detectors.b4_statcheck import B4StatcheckDetector
from scripts.crossval_statcheck import CORPUS  # type: ignore[import-not-found]


REPO_ROOT = Path(__file__).resolve().parent.parent
RSCRIPT = Path("C:/Program Files/R/R-4.6.0/bin/Rscript.exe")
R_DRIVER = REPO_ROOT / "scripts" / "crossval_statcheck_r.R"
CORPUS_TXT = REPO_ROOT / "scripts" / "crossval_statcheck_corpus.txt"
R_RESULTS = REPO_ROOT / "scripts" / "crossval_statcheck_r_results.json"


def _cohen_kappa(a: list[bool], b: list[bool]) -> float:
    """Cohen's κ on two equal-length binary label lists.

    κ = (po − pe) / (1 − pe)
    where po = observed agreement, pe = expected agreement by chance.
    """
    n = len(a)
    if n == 0 or len(b) != n:
        return float("nan")
    agree = sum(1 for x, y in zip(a, b) if x == y)
    po = agree / n
    p_a = sum(a) / n
    p_b = sum(b) / n
    pe = p_a * p_b + (1 - p_a) * (1 - p_b)
    if 1 - pe < 1e-12:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def main() -> int:
    # 1. Dump corpus
    text = "\n".join(c.text for c in CORPUS)
    CORPUS_TXT.write_text(text, encoding="utf-8")
    print(f"Wrote {CORPUS_TXT} ({len(text)} chars)", file=sys.stderr)

    # 2. Run statcheck-R
    if not RSCRIPT.exists():
        print(f"Rscript not found at {RSCRIPT}; aborting", file=sys.stderr)
        return 1
    r_cmd = [str(RSCRIPT), str(R_DRIVER), str(CORPUS_TXT), str(R_RESULTS)]
    print(f"Running: {' '.join(r_cmd)}", file=sys.stderr)
    r_proc = subprocess.run(r_cmd, capture_output=True, text=True, timeout=300)
    if r_proc.returncode != 0:
        print(f"R driver failed (rc={r_proc.returncode}):", file=sys.stderr)
        print(r_proc.stderr, file=sys.stderr)
        return 1
    print(r_proc.stderr, file=sys.stderr)

    # 3. Load R-side results
    r_data = json.loads(R_RESULTS.read_text(encoding="utf-8"))
    r_claims = r_data.get("claims", [])
    print(f"statcheck-R flagged {len(r_claims)} claims", file=sys.stderr)

    # Build a "did statcheck-R flag this claim?" map keyed by claim text
    # (substring match — statcheck-R returns its raw match).
    r_flags_any: dict[str, bool] = {c.text: False for c in CORPUS}
    r_flags_decision: dict[str, bool] = {c.text: False for c in CORPUS}
    for r_claim in r_claims:
        raw = r_claim.get("raw_text", "") or ""
        is_decision_error = bool(r_claim.get("decision_error"))
        for c in CORPUS:
            # Match by raw_text overlap — statcheck-R's "raw" is the
            # claim it parsed; if our claim's core (test+stat+p) appears,
            # we credit the match.
            core = c.text.replace(" ", "")[:20]
            raw_norm = raw.replace(" ", "")
            if core in raw_norm:
                r_flags_any[c.text] = True
                if is_decision_error:
                    r_flags_decision[c.text] = True
                break

    # 4. Re-run B4
    pg_text = "Stats: " + ". ".join(c.text for c in CORPUS) + "."
    pg_result = B4StatcheckDetector().detect(pg_text)
    pg_flagged_any: set[str] = set()
    pg_flagged_decision: set[str] = set()
    if pg_result.applicable:
        for finding in pg_result.findings:
            for c in CORPUS:
                if c.text in finding.detail or c.text in (
                    finding.evidence.get("raw") or ""
                ):
                    pg_flagged_any.add(c.text)
                    # Check if it's a decision-flip class. PaperGuard's
                    # severity scales with the magnitude; SUSPICIOUS /
                    # CRITICAL ~= decision-flip per our docs.
                    if finding.severity.name in {"SUSPICIOUS", "CRITICAL"}:
                        pg_flagged_decision.add(c.text)
                    break

    # 5. Cohen's κ
    a_any = [c.text in pg_flagged_any for c in CORPUS]
    b_any = [r_flags_any[c.text] for c in CORPUS]
    kappa_any = _cohen_kappa(a_any, b_any)

    a_dec = [c.text in pg_flagged_decision for c in CORPUS]
    b_dec = [r_flags_decision[c.text] for c in CORPUS]
    kappa_dec = _cohen_kappa(a_dec, b_dec)

    # Per-claim disagreement
    disagreements = []
    for c in CORPUS:
        pg_any = c.text in pg_flagged_any
        r_any = r_flags_any[c.text]
        if pg_any != r_any:
            disagreements.append(
                {
                    "text": c.text,
                    "test_type": c.test_type,
                    "pg_fired": pg_any,
                    "statcheck_r_fired": r_any,
                }
            )

    out = {
        "n_claims": len(CORPUS),
        "pg_flagged_any": len(pg_flagged_any),
        "statcheck_r_flagged_any": sum(b_any),
        "pg_flagged_decision_flip": len(pg_flagged_decision),
        "statcheck_r_flagged_decision_flip": sum(b_dec),
        "cohen_kappa_any": round(kappa_any, 4),
        "cohen_kappa_decision_flip": round(kappa_dec, 4),
        "n_disagreements_any": len(disagreements),
        "disagreements": disagreements,
    }

    out_path = REPO_ROOT / "scripts" / "crossval_statcheck_kappa_results.json"
    out_path.write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nWrote {out_path}", file=sys.stderr)

    print(
        f"\n=== Cohen's κ summary ===\n"
        f"  N claims:                    {len(CORPUS)}\n"
        f"  PG B4 flagged (any):         {len(pg_flagged_any)}\n"
        f"  statcheck-R flagged (any):   {sum(b_any)}\n"
        f"  PG decision-flip flagged:    {len(pg_flagged_decision)}\n"
        f"  statcheck-R decision-flip:   {sum(b_dec)}\n"
        f"  N disagreements (any):       {len(disagreements)}\n"
        f"  Cohen's κ (any-flag):        {kappa_any:.4f}\n"
        f"  Cohen's κ (decision-flip):   {kappa_dec:.4f}\n",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
