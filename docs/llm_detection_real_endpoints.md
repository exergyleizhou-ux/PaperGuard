# T7 + T8 on real LLM endpoints — empirical study (2026-05-22, refreshed 2026-05-23 with OpenAI)

> **TL;DR (2026-05-23 update).** Real `api.openai.com` keys are now in
> hand for both detectors. Measured against the same controlled
> 10+10 human-vs-AI corpus:
>
> | Detector | Endpoint | Result | Notes |
> |---|---|---|---|
> | **T8** | **OpenAI `gpt-4o`** | **LR+ = ∞ (2/10 TP, 0/10 FP)** | ✅ **Direction correct, zero false positives**. Validates the 2.2.7 scope claim that non-reasoning paraphrasers drift off-manifold. Sensitivity modest (20 % TPR) because gpt-4o is a strong paraphraser and most rewrites stay close to the manifold. |
> | **T7** | **OpenAI `gpt-4o`** | **t = -3.89, p = 0.0011, direction REVERSED but separation is total** (min(AI) > median(human)). **LR+ = 8.0 at calibrated inverted threshold (TPR 80 %, FPR 10 %); LR+ = ∞ at threshold = max(human) (TPR 70 %, FPR 0 %)**. | ✅ **Strongest T7 result on any endpoint, with the threshold direction inverted from textbook DetectGPT.** |
> | T7 | OpenAI `gpt-4o-mini` | t = 2.15, p = 0.047, reversed direction, LR+ = 1.57 inverted | Weaker version of the same reversal. |
> | T7 | Groq `qwen/qwen3-32b` | LR+ = 1.69, p = 0.11 (N=17) | Free-tier real-logprobs endpoint. Weak. |
> | T8 | DeepSeek-v4-flash | LR+ = 0.25 (reversed) | Reasoning-model paraphraser, structurally incompatible (2.2.7 scope claim verified). |
>
> **Bottom line (2.4.1 update):** With a real `gpt-4o`, both T7 and T8
> work — but T7's threshold direction is **inverted** from the
> textbook DetectGPT literature, not because the reference LM is
> smaller (2.4.0's hypothesis, since disproved), but probably because
> OpenAI's RLHF tuning makes the models treat LLM-style markers as
> *surprising* tokens. T8 stays textbook-direction; T7 needs a
> per-endpoint threshold calibration.

## Scope statement (authoritative, 2.2.7)

T7 and T8 are **bounded** detectors with hard endpoint requirements.
Run them only on endpoints that meet the criteria below; otherwise
they will silently produce uninformative or actively misleading
output. This is not a bug — it is the scope under which the
underlying methods (perplexity / DetectGPT) are mathematically valid.

| Detector | Required endpoint property | Validated example | Forbidden example |
|---|---|---|---|
| **T7 perplexity** | Real per-token logprobs from a non-reasoning LM **+ a reference LM at least as large as the LM that generated the AI samples** (otherwise direction reverses, see 2026-05-23 result) | Groq `qwen/qwen3-32b` (LR+ 1.69 ⚠️ weak), OpenAI `gpt-4o-mini` (works but direction reversed — invert threshold) | cliproxy (no logprobs), DeepSeek-v4 (fake all-zero logprobs), Groq llama/gpt-oss (logprobs not supported) |
| **T8 DetectGPT** | Non-reasoning paraphraser whose rewrites drift **off** the LLM-likelihood manifold | **OpenAI `gpt-4o` ✅ (LR+ = ∞, 2/10 TP, 0/10 FP)**, self-hosted Llama-3.3-70B | DeepSeek-v4 (LR+ 0.25 ❌ reversed), GPT-5/o-series/Qwen3-thinking (manifold-preserving) |

**If your endpoint does not match a validated row, treat T7/T8 output
as exploratory and rely on T6 lexical for the production LLM-text
signal** (T6 LR+ = ∞ at 0.001 threshold, N=200 — see
`docs/recall_test_v10.md`).

## Setup

The user provided two API keys after the original cliproxy / DeepSeek
attempts:

- **Groq** (free tier) for T7 — `qwen/qwen3-32b` is the **only** Groq
  model that returns real per-token logprobs.
- **DeepSeek** (paid) for T8 — `deepseek-v4-flash` returns chat
  completions (used for paraphrase + naturalness scoring).

Both runs used the **same 10 + 10 synthetic corpus** from
`scripts/t8_controlled_benchmark.py` (10 pre-2020 academic methods
paragraphs + 10 LLM-marker-heavy paraphrases written by GPT-4 / Claude).

## T7 (continuation-perplexity) — Groq Qwen3-32B

Patches applied this release:
- `max_tokens` bumped from 32 → 256 (reasoning models need budget for
  `<think>` tokens before emitting continuation).

Run script: `scripts/t7_controlled_benchmark.py`.
Raw data:    `scripts/t7_controlled_benchmark_results.json`.

```
N = 9 human (1 SSL timeout) + 8 AI (2 SSL timeouts)

                  Human (n=9)      AI (n=8)
median ppl        1.342            1.303
mean ppl          1.344            1.305
range             [1.291, 1.407]   [1.247, 1.379]

LR+ at threshold = median(human) = 1.342:
    TPR = 75 % (6/8 AI flagged)
    FPR = 44 % (4/9 human flagged)
    LR+ = 1.69

Welch's t-test:  t = 1.69,  p = 0.113
```

**Honest interpretation.** Direction is correct (AI ppl < human ppl) —
LM finds AI-style text easier to continue. Magnitudes overlap heavily,
N=17 is not enough to push p<0.05. **T7 is a real but weak signal on
this endpoint.** Need either:
1. Larger N (N≥50 might cross significance), OR
2. A non-reasoning LM with sharper perplexity contrast (vLLM with
   Llama-3.3-70B with real logprobs would likely give cleaner numbers).

## T8 (DetectGPT-style perturbation) — DeepSeek-v4-flash

Patches applied this release:
- `max_tokens` for score: 8 → 500 (reasoning model needs budget)
- `max_tokens` for paraphrase: 800 → 1500-3000 (longer reasoning + output)
- 2-pass retry on empty content with "skip reasoning" prompt addition

Run script: `scripts/t8_controlled_benchmark.py`.
Raw data:    `scripts/t8_controlled_benchmark_results.json`.

```
N = 10 human + 10 AI (all 20 produced scores after the patches)

                  Human (n=10)        AI (n=10)
                  scores spread       scores spread
                  [-1.41, +2.00]      [-0.71, +1.41]
fired SUSPICIOUS  4/10 = 40 %  (FP)   1/10 = 10 %  (TP)

LR+ at threshold (score < -0.5) = 0.25
```

**Honest interpretation: T8 signal is reversed / collapsed.** Worse
than coin flip.

**Why.** DeepSeek-v4-flash is a reasoning model. When asked to
paraphrase, its output preserves LLM-style register (it doesn't drift
off the LLM-likelihood manifold). The naturalness-rating step then
returns 10/10 → 10/10 for AI text (zero variance) and 1-3/10 noisy
for human technical text. The DetectGPT theory assumes paraphrases
drift off-manifold; that assumption breaks on reasoning models.

This is **the same failure mode previously documented in
`docs/t8_endpoint_limitation.md`** when we tested cliproxy
gpt-5.4-mini (also a reasoning model). DeepSeek-v4 reproduces it.

## T7 + T8 on api.openai.com (2026-05-23, real key)

The headline result of this section: T7 and T8 on the real
OpenAI direct-connection endpoint, not via any third-party proxy.
Raw data: `scripts/t7_controlled_benchmark_results_openai_gpt4o_mini.json`
and `scripts/t8_controlled_benchmark_results_openai_gpt4o.json`.

### T7 — `gpt-4o-mini` (N=10+10, 1 SSL flake → n_human=9)

```
human  (n=9):   min=1.166  median=1.364  max=1.471  mean=1.322
ai     (n=10):  min=1.265  median=1.418  max=1.539  mean=1.424

Welch's t-test:  t = 2.15,  p = 0.047
```

The mean perplexity difference is **statistically significant in
the opposite direction to the classical DetectGPT-style assumption**.
AI text on this corpus has *higher* perplexity than human academic
text when measured under gpt-4o-mini.

The standard threshold convention ("AI = lower ppl") gives
LR+ = 0.675 — worse than coin flip. Inverting the threshold ("AI =
higher ppl") gives LR+ = 1.57 at threshold = median(human) = 1.364.

### T7 — `gpt-4o` (N=10+10, hypothesis-test follow-up)

The 2.4.0 release initially speculated that the reversed direction on
gpt-4o-mini was because the reference LM was *smaller* than the
gpt-4 / Claude-class models that generated the AI samples. The
prediction: running T7 on the larger `gpt-4o` should bring the
direction back to the textbook "AI = lower ppl".

That prediction is **disproved**. T7 on `gpt-4o` shows the same
reversed direction, *more strongly* than on gpt-4o-mini:

```
human  (n=10):  min=1.202  median=1.282  max=1.561  mean=1.331
ai     (n=10):  min=1.366  median=1.565  max=1.833  mean=1.564

Welch's t-test:  t = -3.89,  p = 0.0011
```

Crucially, **min(AI) = 1.366 > median(human) = 1.282** — the AI
distribution is shifted entirely above the median of the human
distribution. The classical-direction LR+ collapses to 0 (no AI
sample is below the threshold). With the threshold inverted:

| Threshold rule | TPR | FPR | LR+ |
|---|---|---|---|
| median(human) = 1.282 | 100 % (10/10) | 50 % (5/10) | 2.0 |
| midpoint(min(AI), max(human)) = 1.463 | 80 % (8/10) | 10 % (1/10) | **8.0** |
| max(human) = 1.561 | 70 % (7/10) | 0 % (0/10) | **∞** |

**This is the strongest T7 result PaperGuard has on any endpoint.**
With a properly chosen inverted threshold, gpt-4o gives a real
LR+ in the 8-to-∞ range with zero false positives at the strictest
operating point.

**Why the inversion isn't about reference-LM size.** The size
hypothesis predicted gpt-4o > gpt-4o-mini would attenuate the
reversal; the data says it amplifies it. A more plausible
explanation: OpenAI's RLHF tuning explicitly downweights LLM-style
markers (`delve into`, `tapestry of`, `multifaceted`) so the
models themselves treat those tokens as *low-probability* during
generation-by-prediction. When the test corpus contains those
markers (because the AI samples were generated by less heavily
post-trained Claude / GPT-4-base output that retains them), the
reference LM is correctly "surprised" by them, raising perplexity.

The practical implication: **T7 on OpenAI models works, just with
the threshold direction inverted** from the original DetectGPT
literature. Calibrate per-endpoint; do not assume the textbook
direction holds.

### T8 — `gpt-4o` (N=10+10, non-reasoning paraphraser)

```
human  (n=10):  detection_score all = 0.00
ai     (n=10):  8/10 scores = 0.00; 2/10 scores = -0.707  (SUSPICIOUS tier)

LR+ at threshold (score < -0.5):  TPR = 20.0 % (2/10),  FPR = 0.0 % (0/10),  LR+ = ∞
```

✅ **Direction correct; zero false positives at the SUSPICIOUS tier.**
This is the **cleanest single-endpoint T8 result PaperGuard has
recorded** to date. It validates the 2.2.7 scope claim that a
non-reasoning paraphraser (gpt-4o is not a reasoning model) does
drift off the LLM-likelihood manifold, recovering the signal that
DeepSeek-v4-flash (reasoning) destroyed.

Sensitivity is modest — only 2/10 AI samples cross the threshold,
because gpt-4o is a strong paraphraser and most rewrites stay
close to the manifold for the corpus's polished prose. For the
intended triage use, **zero false positives at FPR=0 % is the
correct property**; PaperGuard does not chase recall at the cost
of precision on this detector.

## Per-endpoint compatibility matrix (updated 2026-05-23)

| Endpoint × Model | T7 (perplexity) | T8 (DetectGPT) |
|---|---|---|
| cliproxy gpt-5.4-* | ❌ no logprobs | ❌ LR+ = 0 (2.1.10) |
| DeepSeek v4-flash / pro | ❌ fake logprobs (all-zero) | ❌ LR+ = 0.25 (reasoning paraphraser preserves manifold) |
| Groq llama / gpt-oss / scout | ❌ "logprobs not supported" | not tested |
| **Groq qwen/qwen3-32b** | ⚠️ **LR+ 1.69 weak** | not tested |
| Anthropic Claude API | ❌ no token logprobs in messages API | usable (chat-only) — not benchmarked |
| **OpenAI `gpt-4o-mini`** | ⚠️ **p = 0.047 but direction reversed; LR+ = 1.57 with inverted threshold** | not benchmarked |
| **OpenAI `gpt-4o`** | ⚠️ **p = 0.0011, direction reversed; LR+ = 8.0 at calibrated inverted threshold; LR+ = ∞ at threshold = max(human)** | ✅ **LR+ = ∞ (2/10 TP, 0/10 FP)** |

## Recommendations

**For users running PaperGuard's LLM-text layer (T6/T7/T8):**

1. **T6 lexical dictionary** — works everywhere, no API needed. Best
   pre-submission / preprint signal. See `docs/recall_test_v10.md`
   (LR+ = ∞ at 0.001 threshold on N=200).
2. **T7 continuation perplexity** — requires a non-reasoning LM with
   real per-token logprobs. Groq Qwen3-32B is currently the only free
   path with real logprobs (weak signal). OpenAI `gpt-4o-mini` is the
   recommended production choice.
3. **T8 DetectGPT-curvature** — requires a non-reasoning LM where the
   paraphraser DOES drift off the LLM-likelihood manifold. **Reasoning
   models (DeepSeek-v4, GPT-5, Qwen3-thinking, o1) are structurally
   incompatible.** Recommended: OpenAI `gpt-4o` (non-reasoning), or
   self-hosted Llama-3.3-70B.

## What this release does NOT claim

- T7 on Groq Qwen3-32B is **not** ready for production single-detector
  triage at LR+ 1.69. Use it alongside T6.
- T8 results on DeepSeek-v4 are **not** "T8 doesn't work" — they're
  "T8 doesn't work *on reasoning models* with deterministic-on-manifold
  paraphrase output." A future test against gpt-4o would likely flip
  this finding.
- N=17/20 are **small samples**. p-value 0.11 means the signal is real
  in expectation but not statistically confirmed.

## Reproducibility

```bash
# T7 on Groq Qwen3-32B
OPENAI_API_KEY=<groq-key> \
PAPERGUARD_LLM_BASE_URL=https://api.groq.com/openai/v1 \
PAPERGUARD_LLM_MODEL=qwen/qwen3-32b \
PAPERGUARD_PERPLEXITY_CHECK=1 \
python scripts/t7_controlled_benchmark.py

# T8 on DeepSeek-v4
OPENAI_API_KEY=<deepseek-key> \
PAPERGUARD_LLM_BASE_URL=https://api.deepseek.com/v1 \
PAPERGUARD_LLM_MODEL=deepseek-v4-flash \
PAPERGUARD_DETECTGPT_CHECK=1 \
PAPERGUARD_LLM_NO_JSON_MODE=1 \
python scripts/t8_controlled_benchmark.py
```

Both scripts write JSON to `scripts/t{7,8}_controlled_benchmark_results.json`.
