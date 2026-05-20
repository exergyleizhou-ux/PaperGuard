"""Analyse a recall_test_v9_results.json and produce a Markdown report.

Extends recall_analyze_v8 with optional T7 + T8 columns. When T7/T8
runs returned None across the whole study (because the configured
endpoint dropped logprobs / had weak paraphrasing), we annotate that
explicitly rather than computing meaningless LR+.

Usage:
    python scripts/recall_analyze_v9.py \\
        scripts/recall_test_v9_results.json \\
        > docs/recall_test_v9.md
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path


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
    if not pos or not neg:
        return float("nan"), float("nan"), float("nan")
    tpr = sum(1 for x in pos if x >= threshold) / len(pos)
    fpr = sum(1 for x in neg if x >= threshold) / len(neg)
    if fpr == 0:
        fpr_floor = 1.0 / (len(neg) + 1)
        return tpr, fpr, tpr / fpr_floor
    return tpr, fpr, tpr / fpr


def main(path: str) -> int:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    results = data.get("results", [])
    model = data.get("model", "unknown")

    retracted = [r for r in results if r["arm"] == "retracted"]
    control = [r for r in results if r["arm"] == "control"]

    out: list[str] = []
    out.append("# recall_test_v9 — N=100 LR+ study (T6 + T7 + T8)\n\n")
    out.append(
        f"PaperGuard 2.1.0. Reference LM: `{model}`. "
        f"N = {len(retracted)} retracted + {len(control)} controls.\n\n"
    )

    pmc_ok_ret = [r for r in retracted if r.get("pmc_ok")]
    pmc_ok_con = [r for r in control if r.get("pmc_ok")]
    out.append("## Coverage\n\n")
    out.append(f"- Retracted with PMC full text: **{len(pmc_ok_ret)} / {len(retracted)}**\n")
    out.append(f"- Controls with PMC full text:  **{len(pmc_ok_con)} / {len(control)}**\n\n")

    # ---- T6 ----
    ret_t6 = [
        r.get("t6_density") or 0.0
        for r in pmc_ok_ret
        if r.get("t6_density") is not None
    ]
    con_t6 = [
        r.get("t6_density") or 0.0
        for r in pmc_ok_con
        if r.get("t6_density") is not None
    ]

    out.append("## T6 phrase-density LR+\n\n")
    out.append("| threshold | TPR | FPR | LR+ |\n|---|---|---|---|\n")
    for thr in (0.0005, 0.001, 0.002, 0.003, 0.005, 0.008):
        tpr, fpr, lr = _lr_plus(ret_t6, con_t6, thr)
        out.append(
            f"| ≥ {thr:.4f} | {tpr:.2%} | {fpr:.2%} | {lr:.2f} |\n"
        )
    out.append("\n")

    out.append("**T6 density distribution**\n\n")
    out.append("| arm | N | mean | median | P75 | P90 | P95 |\n|---|---|---|---|---|---|---|\n")

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

    out.append(_row("retracted", ret_t6) + "\n")
    out.append(_row("control", con_t6) + "\n\n")

    # ---- T7 ----
    ret_t7 = [
        r["t7_perplexity"]
        for r in pmc_ok_ret
        if r.get("t7_perplexity") is not None
    ]
    con_t7 = [
        r["t7_perplexity"]
        for r in pmc_ok_con
        if r.get("t7_perplexity") is not None
    ]
    out.append("## T7 perplexity\n\n")
    if not ret_t7 and not con_t7:
        outcomes_r = Counter(r.get("t7_outcome") for r in pmc_ok_ret)
        outcomes_c = Counter(r.get("t7_outcome") for r in pmc_ok_con)
        out.append(
            "T7 returned no perplexity values on the configured endpoint "
            f"(`{model}`). Outcomes per arm:\n\n"
        )
        out.append(f"- Retracted: {dict(outcomes_r)}\n")
        out.append(f"- Controls:  {dict(outcomes_c)}\n\n")
        out.append(
            "This is expected on endpoints that drop the `logprobs` "
            "field. Re-run on a logprobs-capable GPT-4o-class endpoint "
            "to populate the LR+ row.\n\n"
        )
    else:
        out.append("| threshold (≤) | TPR | FPR | LR+ |\n|---|---|---|---|\n")
        # T7: LOW perplexity = LLM signal, so threshold is "≤"
        for thr in (5.0, 10.0, 15.0, 20.0):
            tpr = sum(1 for x in ret_t7 if x <= thr) / max(1, len(ret_t7))
            fpr = sum(1 for x in con_t7 if x <= thr) / max(1, len(con_t7))
            lr = (
                tpr / fpr if fpr > 0
                else tpr / (1.0 / (len(con_t7) + 1))
            )
            out.append(f"| ≤ {thr:.0f} | {tpr:.2%} | {fpr:.2%} | {lr:.2f} |\n")
        out.append("\n")

    # ---- T8 ----
    ret_t8 = [
        r["t8_score"]
        for r in pmc_ok_ret
        if r.get("t8_score") is not None
    ]
    con_t8 = [
        r["t8_score"]
        for r in pmc_ok_con
        if r.get("t8_score") is not None
    ]
    out.append("## T8 DetectGPT score\n\n")
    if not ret_t8 and not con_t8:
        outcomes_r = Counter(r.get("t8_outcome") for r in pmc_ok_ret)
        outcomes_c = Counter(r.get("t8_outcome") for r in pmc_ok_con)
        out.append(
            "T8 returned no scores on the configured endpoint "
            f"(`{model}`). Outcomes per arm:\n\n"
        )
        out.append(f"- Retracted: {dict(outcomes_r)}\n")
        out.append(f"- Controls:  {dict(outcomes_c)}\n\n")
        out.append(
            "This is expected on endpoints whose paraphraser preserves "
            "LLM-style markers — the original-vs-paraphrase score gap "
            "collapses to ≈0. Re-run on a GPT-4o-class endpoint to "
            "populate the LR+ row.\n\n"
        )
    else:
        out.append("| threshold (≤) | TPR | FPR | LR+ |\n|---|---|---|---|\n")
        # T8: NEGATIVE score = LLM signal, so threshold is "≤"
        for thr in (-1.5, -1.0, -0.5, 0.0):
            tpr = sum(1 for x in ret_t8 if x <= thr) / max(1, len(ret_t8))
            fpr = sum(1 for x in con_t8 if x <= thr) / max(1, len(con_t8))
            lr = (
                tpr / fpr if fpr > 0
                else tpr / (1.0 / (len(con_t8) + 1))
            )
            out.append(f"| ≤ {thr:+.1f} | {tpr:.2%} | {fpr:.2%} | {lr:.2f} |\n")
        out.append("\n")

    # ---- Headline ----
    out.append("## Interpretation\n\n")
    if ret_t6 and con_t6:
        _, _, lr3 = _lr_plus(ret_t6, con_t6, 0.003)
        out.append(
            f"At the default T6 CONCERN threshold (0.003), LR+ = "
            f"{lr3:.2f} on N={len(ret_t6)}+{len(con_t6)}. "
        )
        if lr3 >= 2.0:
            out.append("Clears the 'useful for triage' bar.\n\n")
        elif lr3 >= 1.3:
            out.append(
                "Weak triage signal — keep T6 on but combine with "
                "T7 / T8 for stronger inference.\n\n"
            )
        else:
            out.append(
                "Below the triage bar. T6 alone is too weak for "
                "post-publication Nature-tier screening; better use is "
                "pre-submission / preprint screening.\n\n"
            )

    out.append(
        "T7 / T8 empirical LR+ depends on having a GPT-4o-class endpoint "
        "with token logprobs and a paraphraser that drifts off the "
        "LLM-likelihood manifold. Re-run this script with such an "
        "endpoint configured to populate the T7/T8 rows.\n\n"
    )

    print("".join(out))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "usage: python scripts/recall_analyze_v9.py "
            "<results.json>",
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
