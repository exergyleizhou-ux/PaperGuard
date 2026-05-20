"""Analyse a recall_test_v8_results.json file and produce a Markdown report.

Computes T6 phrase-density LR+ at several candidate thresholds, breaks
down by provider attribution, and reports per-arm summary statistics.

Usage:
    python scripts/recall_analyze_v8.py \\
        scripts/recall_test_v8_results.json \\
        > docs/recall_test_v8.md
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = (len(s) - 1) * q
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f) if f != c else s[f]


def _lr_plus(
    pos: list[float], neg: list[float], threshold: float
) -> tuple[float, float, float]:
    """Return (TPR, FPR, LR+ = TPR / FPR). NaN-safe."""
    if not pos or not neg:
        return float("nan"), float("nan"), float("nan")
    tpr = sum(1 for x in pos if x >= threshold) / len(pos)
    fpr = sum(1 for x in neg if x >= threshold) / len(neg)
    if fpr == 0:
        # No false positives at this threshold — report LR+ as inf or
        # the conservative "1/N(neg+1)" floor.
        fpr_floor = 1.0 / (len(neg) + 1)
        return tpr, fpr, tpr / fpr_floor
    return tpr, fpr, tpr / fpr


def main(path: str) -> int:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    results = data.get("results", [])

    retracted = [r for r in results if r["arm"] == "retracted"]
    control = [r for r in results if r["arm"] == "control"]

    out: list[str] = []
    out.append("# recall_test_v8 — T6 lexical LLM-text recall study\n")
    out.append(
        f"PaperGuard 2.0.16 (T6 phrase-density only). "
        f"N = {len(retracted)} retracted + {len(control)} controls, "
        f"sampled from OpenAlex `is_retracted` filter + matched-subfield "
        f"non-retracted control. Full text from Europe PMC.\n"
    )
    out.append("## Coverage\n")
    pmc_ok_ret = sum(1 for r in retracted if r.get("pmc_ok"))
    pmc_ok_con = sum(1 for r in control if r.get("pmc_ok"))
    out.append(f"- Retracted with PMC full text: **{pmc_ok_ret} / {len(retracted)}**\n")
    out.append(f"- Controls with PMC full text:  **{pmc_ok_con} / {len(control)}**\n")
    n_full_pair = sum(
        1
        for i in range(min(len(retracted), len(control)))
        if retracted[i].get("pmc_ok") and control[i].get("pmc_ok")
    )
    out.append(f"- Matched pairs with both arms PMC-resolved: **{n_full_pair}**\n\n")

    # T6 density distributions
    ret_density = [
        r.get("t6_density") or 0.0
        for r in retracted
        if r.get("pmc_ok") and r.get("t6_density") is not None
    ]
    con_density = [
        r.get("t6_density") or 0.0
        for r in control
        if r.get("pmc_ok") and r.get("t6_density") is not None
    ]

    out.append("## T6 phrase-density distribution\n\n")
    out.append("| Arm | N | mean | median | P75 | P90 | P95 |\n")
    out.append("|---|---|---|---|---|---|---|\n")

    def _row(label: str, vals: list[float]) -> str:
        if not vals:
            return f"| {label} | 0 | – | – | – | – | – |"
        return (
            f"| {label} | {len(vals)} | "
            f"{statistics.mean(vals):.5f} | "
            f"{statistics.median(vals):.5f} | "
            f"{_quantile(vals, 0.75):.5f} | "
            f"{_quantile(vals, 0.90):.5f} | "
            f"{_quantile(vals, 0.95):.5f} |"
        )

    out.append(_row("retracted", ret_density) + "\n")
    out.append(_row("control", con_density) + "\n\n")

    # LR+ at candidate thresholds (T6 default CONCERN = 0.003)
    out.append("## T6 LR+ at candidate thresholds\n\n")
    out.append(
        "LR+ = P(test+ | retracted) / P(test+ | control). "
        "Higher LR+ means a positive test moves you more toward suspecting "
        "the paper. LR+ ≥ 2 is the canonical threshold for 'useful for "
        "triage' in clinical-test literature.\n\n"
    )
    out.append("| threshold | TPR (retracted) | FPR (control) | LR+ |\n")
    out.append("|---|---|---|---|\n")
    for thr in (0.0005, 0.001, 0.002, 0.003, 0.005, 0.008):
        tpr, fpr, lr = _lr_plus(ret_density, con_density, thr)
        out.append(
            f"| ≥ {thr:.4f} | {tpr:.2%} | {fpr:.2%} | {lr:.2f} |\n"
        )
    out.append("\n")

    # Provider attribution
    out.append("## Provider attribution (sub-threshold NOTE)\n\n")
    out.append("| Arm | gpt | claude | gemini | none |\n")
    out.append("|---|---|---|---|---|\n")

    def _provider_counts(arm: list[dict[str, Any]]) -> Counter[str]:
        c: Counter[str] = Counter()
        for r in arm:
            if not r.get("pmc_ok"):
                continue
            prov = r.get("t6_provider") or "none"
            c[prov] += 1
        return c

    pc_ret = _provider_counts(retracted)
    pc_con = _provider_counts(control)
    for arm_name, pc in (("retracted", pc_ret), ("control", pc_con)):
        out.append(
            f"| {arm_name} | {pc.get('gpt', 0)} | "
            f"{pc.get('claude', 0)} | {pc.get('gemini', 0)} | "
            f"{pc.get('none', 0)} |\n"
        )
    out.append("\n")

    # Interpretation
    out.append("## Interpretation\n\n")
    if not ret_density or not con_density:
        out.append(
            "Insufficient PMC coverage to draw conclusions. T6 fell back to "
            "the no-text path on most papers.\n"
        )
    else:
        # Use the most-informative threshold (default 0.003 ≡ T6 CONCERN tier)
        tpr3, fpr3, lr3 = _lr_plus(ret_density, con_density, 0.003)
        if lr3 >= 2:
            verdict = (
                f"At the default CONCERN threshold (0.003), T6 achieves "
                f"LR+ = {lr3:.2f}. This clears the 'useful for triage' bar "
                f"and supports keeping T6 on by default in 2.0.16."
            )
        elif lr3 >= 1.3:
            verdict = (
                f"At the default CONCERN threshold (0.003), T6 achieves "
                f"LR+ = {lr3:.2f}. This is a weak but real signal — keep T6 "
                f"on by default but document the limitation: T6 is a "
                f"triage-stage signal, not evidence of misconduct."
            )
        else:
            verdict = (
                f"At the default CONCERN threshold (0.003), T6 achieves "
                f"LR+ = {lr3:.2f}. Below the 'useful for triage' bar; T6 "
                f"alone is too weak for default-on. Consider raising the "
                f"phrase-density threshold or combining with T7/T8."
            )
        out.append(verdict + "\n\n")

    # T7/T8 limitations note
    out.append(
        "## T7 / T8 limitations under cliproxy gpt-5.4-mini\n\n"
        "T7 (perplexity) requires token-level logprobs in the response. "
        "The cliproxy endpoint silently drops the `logprobs` field; T7 "
        "therefore returns a NOTE-level inconclusive finding under that "
        "endpoint. T8 (DetectGPT curvature) needs the reference LM's "
        "paraphraser to drift OFF the LLM-likelihood manifold when "
        "applied to LLM-authored text. With gpt-5.4-mini, the paraphraser "
        "preserves LLM-style markers, so the original-vs-paraphrase score "
        "gap collapses to ≈0 on both arms. **Live LR+ measurement of T7 "
        "and T8 awaits access to a GPT-4o-class endpoint that exposes "
        "logprobs.**\n\n"
        "T7/T8 are nonetheless shipped in 2.0.16: their unit-test coverage "
        "verifies algorithm correctness on synthetic inputs, the CLI flags "
        "are wired, and the detectors degrade gracefully (NOTE-level "
        "inconclusive) rather than emitting false positives on weak "
        "endpoints.\n"
    )

    print("".join(out))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "usage: python scripts/recall_analyze_v8.py "
            "<results.json>",
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
