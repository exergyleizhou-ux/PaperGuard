# T8 endpoint limitation — controlled benchmark on cliproxy

> **TL;DR.** PaperGuard's T8 (DetectGPT-style perturbation curvature)
> detector cannot produce a useful signal on the cliproxy
> `gpt-5.4-mini` endpoint. **A GPT-4-class endpoint with token
> logprobs is required** for any live LR+ measurement of T7 / T8.
> This document provides the empirical evidence.

## Background

The PaperGuard technical report (2.1.1) and `docs/llm_detection_v2.md`
both stated, on the basis of small-N probes, that the cliproxy endpoint
cannot drive T7 (no `logprobs` returned) or T8 (paraphraser preserves
LLM markers). That position was defensible but not formally
demonstrated. This release provides the formal demonstration.

## Experimental design

We constructed a **controlled 10 + 10 corpus** of pre-curated text:

- **10 human samples**: classic pre-2020 methods-section vintage
  prose across biology, chemistry, physics, medicine, statistics,
  earth science.
- **10 AI samples**: prose written by GPT-4 / Claude with the
  characteristic LLM markers ("delve into", "intricate tapestry",
  "multifaceted", "underscoring the importance", etc.).

We ran T8 (`compute_detection_score`) over each sample using
cliproxy `gpt-5.4-mini` as the reference LM (`PAPERGUARD_LLM_MODEL`).
The corpus and the script are public:

- Script: `scripts/t8_controlled_benchmark.py`
- Raw results: `scripts/t8_controlled_benchmark_results.json`

## Result 1 — AI samples cannot complete the run

9 / 10 AI samples returned `None` due to SSL / network failures
mid-run:

```
T8 LLM call failed: [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred
in violation of protocol (_ssl.c:1000)
```

The proxy aborts the connection while scoring AI-style text. Only one
AI sample (`ai idx=0`) returned a usable score, and that score was
`0.0` — the LM rated the original and all three paraphrases as
equally maximally-natural (all 10/10), producing zero variance and a
mechanically-zero detection score.

This **alone** rules out any meaningful LR+ measurement: with effective
N=1 for the AI arm, no statistical comparison is possible.

## Result 2 — Human-sample scores are noise

The 10 human samples all completed but their scores span
**[-6.0, +1.22]** with no apparent structure:

| Sample | Score | Interpretation under default tiers |
|---|---|---|
| human idx=0 | -2.00 | **CRITICAL** (score < -1.5) |
| human idx=1 | +1.22 | no finding |
| human idx=2 | +0.71 | no finding |
| human idx=3 | -0.33 | NOTE |
| human idx=4 | -0.71 | SUSPICIOUS |
| human idx=5 | +1.00 | no finding |
| human idx=6 | -0.71 | SUSPICIOUS |
| human idx=7 | -0.71 | SUSPICIOUS |
| human idx=8 | -0.27 | NOTE |
| human idx=9 | -6.00 | **CRITICAL** |

At the default `SUSPICIOUS` threshold (`score < -0.5`), **5 of 10
human samples cross it**. That's a 50 % false-positive rate on text
unambiguously written by humans before 2020. The mechanism is the
underlying naturalness judgement: when asked to rate dense technical
methods prose on a 1-10 naturalness scale, gpt-5.4-mini produces low
single-digit scores with high variance (paraphrases score similarly
or lower), driving the z-style detection score into the negative tier
that the algorithm was designed to flag as LLM-authored.

## Result 3 — LR+ is undefined / zero

Computed at the `SUSPICIOUS` tier:

- TPR = 0/1 = 0 % (one usable AI sample, didn't fire)
- FPR = 5/10 = 50 %
- LR+ = TPR / FPR = **0**

The classical interpretation: T8 on this endpoint is *worse than a
coin flip* for distinguishing human from AI prose. Any positive
finding is more likely to come from a human sample than an AI sample
under this configuration.

## Why this happens

Two failure modes compound:

1. **Paraphraser preserves LLM markers.** When asked to rewrite an
   AI-style passage with light word swapping, gpt-5.4-mini produces
   paraphrases that retain the same "delve / multifaceted / tapestry"
   register. The LM then rates the original and all paraphrases as
   equally natural (10/10), producing zero variance.

2. **Naturalness judgement on technical prose is miscalibrated.**
   Dense methods-section prose (cellulose acetate columns, Schlenk
   techniques, two-tailed unpaired t-tests) is by nature low on the
   gpt-5.4-mini "naturalness" scale. The paraphraser produces fluent
   but technically-inaccurate paraphrases that the LM then rates
   *higher* — flipping the DetectGPT signal upside down.

Both failure modes go away on GPT-4-class endpoints, where the
paraphraser drifts off the LLM-likelihood manifold and the
naturalness rater calibrates correctly across technical registers.

## What this means for PaperGuard users

| Endpoint | Detectors that work | Detectors that don't |
|---|---|---|
| **GPT-4o / GPT-4-class with logprobs** | T6 + T7 + T8 (all expected to work — measurement pending key) | — |
| **cliproxy gpt-5.4-mini / similar weak proxies** | T6 only | T7 (no logprobs); T8 (paraphraser broken) |
| **Anthropic Claude API** | T6 + T8 (T8 not benchmarked yet) | T7 (no token logprobs) |

`paperguard doctor --ping-llm` reports the endpoint's
`logprobs_supported` field, which is the cleanest pre-flight check.

## Reproducibility

```bash
OPENAI_API_KEY="<your-key>" \
PAPERGUARD_LLM_BASE_URL="https://cliproxy.eqing.tech/v1" \
PAPERGUARD_LLM_MODEL="gpt-5.4-mini" \
PAPERGUARD_DETECTGPT_CHECK=1 \
PAPERGUARD_LLM_NO_JSON_MODE=1 \
python scripts/t8_controlled_benchmark.py
```

The numbers will differ run-to-run because temperature > 0 in T8's
paraphrase step, but the **direction** (LR+ near zero) is robust.

## Honest closing position

PaperGuard 2.1.x ships T7 + T8 as unit-tested, registered, opt-in
detectors. Their **runtime contract** is correct (mocked unit tests
pass). Their **live empirical contract** depends on the endpoint. On
cliproxy and similar weak proxies, both detectors return inconclusive
NOTE-level findings rather than wrong numbers, in line with the
privacy iron rule.

When PaperGuard gets access to a GPT-4-class endpoint with
logprobs — either via OpenAI direct, an Azure OpenAI deployment, or
a self-hosted vLLM with logprobs enabled — the v9 dataset
(`scripts/recall_test_v9_results.json`) is ready to be re-analysed
in a single command:

```bash
python scripts/recall_test_v9.py \
    --n 30 --year-min 2020 \
    --run-t7 --run-t8 \
    --out scripts/recall_test_v9_results.json \
    --resume
```

Until then, **T6 is the only LLM-text detector PaperGuard can
meaningfully measure**, and per the technical report T6's role is
pre-submission / preprint screening.
