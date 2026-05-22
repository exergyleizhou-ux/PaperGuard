"""T7 controlled benchmark — same 10+10 corpus as t8_controlled_benchmark.py.

Measures continuation-perplexity (T7) on real endpoints. Use:

    OPENAI_API_KEY=<key> \\
    PAPERGUARD_LLM_BASE_URL=<base_url> \\
    PAPERGUARD_LLM_MODEL=<model_id> \\
    PAPERGUARD_PERPLEXITY_CHECK=1 \\
    python scripts/t7_controlled_benchmark.py

Output: scripts/t7_controlled_benchmark_results.json
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

from paperguard.detectors.t7_perplexity import compute_perplexity

# Import corpus from sibling script
_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))
from t8_controlled_benchmark import AI_SAMPLES, HUMAN_SAMPLES  # noqa: E402


def main() -> int:
    print(f"=== T7 controlled benchmark ===", file=sys.stderr)
    print(f"  model = {os.environ.get('PAPERGUARD_LLM_MODEL', 'default')}",
          file=sys.stderr)
    print(f"  base  = {os.environ.get('PAPERGUARD_LLM_BASE_URL', 'default')}",
          file=sys.stderr)
    print(f"  N = {len(HUMAN_SAMPLES)} human + {len(AI_SAMPLES)} AI",
          file=sys.stderr)

    results: list[dict] = []
    for i, text in enumerate(HUMAN_SAMPLES):
        print(f"  [human {i+1:2d}/{len(HUMAN_SAMPLES)}]",
              file=sys.stderr, flush=True)
        ppl = compute_perplexity(text, max_segments=2)
        results.append({"arm": "human", "idx": i, "perplexity": ppl})

    for i, text in enumerate(AI_SAMPLES):
        print(f"  [ai    {i+1:2d}/{len(AI_SAMPLES)}]",
              file=sys.stderr, flush=True)
        ppl = compute_perplexity(text, max_segments=2)
        results.append({"arm": "ai", "idx": i, "perplexity": ppl})

    out_path = Path("scripts/t7_controlled_benchmark_results.json")
    out_path.write_text(
        json.dumps(
            {
                "model": os.environ.get("PAPERGUARD_LLM_MODEL", "default"),
                "base_url": os.environ.get(
                    "PAPERGUARD_LLM_BASE_URL", "default"
                ),
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Distributions
    human_ppl = [
        r["perplexity"]
        for r in results
        if r["arm"] == "human" and r["perplexity"] is not None
    ]
    ai_ppl = [
        r["perplexity"]
        for r in results
        if r["arm"] == "ai" and r["perplexity"] is not None
    ]

    print(f"\n=== Perplexity distributions ===", file=sys.stderr)
    if human_ppl:
        print(
            f"  human (n={len(human_ppl)}): "
            f"min={min(human_ppl):.3f}  "
            f"median={statistics.median(human_ppl):.3f}  "
            f"max={max(human_ppl):.3f}  "
            f"mean={statistics.mean(human_ppl):.3f}",
            file=sys.stderr,
        )
    if ai_ppl:
        print(
            f"  ai    (n={len(ai_ppl)}): "
            f"min={min(ai_ppl):.3f}  "
            f"median={statistics.median(ai_ppl):.3f}  "
            f"max={max(ai_ppl):.3f}  "
            f"mean={statistics.mean(ai_ppl):.3f}",
            file=sys.stderr,
        )

    # LR+ at the median-of-human threshold
    if human_ppl and ai_ppl:
        median_human = statistics.median(human_ppl)
        a_tp = sum(1 for p in ai_ppl if p < median_human)
        h_fp = sum(1 for p in human_ppl if p < median_human)
        tpr = a_tp / len(ai_ppl)
        fpr = h_fp / len(human_ppl)
        lr = (
            tpr / fpr if fpr > 0
            else float("inf") if tpr > 0 else 0
        )
        print(
            f"\n=== LR+ at threshold = median(human) = {median_human:.3f} ===",
            file=sys.stderr,
        )
        print(f"  AI samples below threshold (TP):    {a_tp}/{len(ai_ppl)} = {tpr:.2%}",
              file=sys.stderr)
        print(f"  human samples below threshold (FP): {h_fp}/{len(human_ppl)} = {fpr:.2%}",
              file=sys.stderr)
        print(f"  LR+ = {lr}", file=sys.stderr)

        # Welch t-test for difference of means
        try:
            from scipy.stats import ttest_ind

            t_res = ttest_ind(human_ppl, ai_ppl, equal_var=False)
            print(
                f"\n=== Welch's t-test (human vs AI ppl) ===",
                file=sys.stderr,
            )
            print(
                f"  t = {t_res.statistic:.3f}  p = {t_res.pvalue:.4g}",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"  t-test failed: {e}", file=sys.stderr)

    print(f"\nWrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
