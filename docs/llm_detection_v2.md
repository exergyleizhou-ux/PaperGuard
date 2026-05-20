# LLM-text detection in PaperGuard (T6 + T7 + T8)

> **Empirical calibration (2026-05-20)**
>
> From [`recall_test_v8.md`](recall_test_v8.md) (N = 50 + 50 OpenAlex
> retracted / matched controls via Europe PMC):
>
> - **T6 alone** at the default 0.003 CONCERN threshold: TPR 0%,
>   FPR 0%, LR+ = 0. **T6 is a pre-submission / preprint screening
>   signal**, not a post-publication Nature-tier forensics signal —
>   copy-editing removes lexical LLM markers before publication.
> - **T7 / T8 live LR+ deferred** to a GPT-4o-class endpoint with
>   token logprobs. The cliproxy `gpt-5.4-mini` endpoint drops the
>   logprobs field (blocks T7) and runs a paraphraser that
>   preserves LLM-style markers (blocks T8 curvature signal).
>
> Treat T7 / T8 as built-in but currently dormant under weak
> endpoints. They return NOTE-level inconclusive findings rather
> than fabricated numbers.



PaperGuard ships two complementary detectors for "was this written by an
LLM?" Each has a different failure mode; neither is a verdict on its
own. Use them together.

## T6 — Lexical (dictionary)

**What it does.** Scans manuscript text for phrases that LLMs use much
more often than human academic writers ("delve into", "tapestry of",
"meticulously", "intricate interplay", ...). Reports an *AI-phrase
density*: hits / total words.

**Strengths**
- Zero API cost, deterministic, reproducible.
- Per-provider attribution (GPT / Claude / Gemini): the model says
  which LLM the text most resembles, given the phrase mix.
- Trivially explainable to a reviewer ("we found 14 occurrences of
  these specific phrases in the manuscript: ...").

**Failure mode**
- A determined LLM user can search-and-replace every flagged phrase
  by hand and reduce the signal to nothing. So T6 catches sloppy
  use, not deliberate camouflage.
- Domain phrases that overlap with LLM tics ("pivotal role" in
  cell-biology, "robust framework" in ML) produce false positives.

**Keeping it current.** Use the new `paperguard refresh-ai-dict` CLI to
extend the built-in dictionary without waiting for a release. See the
[dynamic dictionary section](#dynamic-dictionary) below.

## T7 — Statistical (perplexity proxy)

**What it does.** Asks a reference language model to *continue* the
manuscript text. Reads the per-token logprobs of the completion and
computes perplexity (`exp(-mean(logprob))`). Lower perplexity means
the LM finds the text "easy to predict", which is consistent with
LLM-authored text.

**Why "continuation-perplexity" and not classical input-perplexity?**
The classical literature (GLTR, DetectGPT) measures perplexity *of the
input string itself*. That requires the `/v1/completions` endpoint
with `echo=true logprobs=N`, which the major chat-API proxies (cliproxy,
OpenRouter, most team pools) do not expose. T7 uses a continuation
proxy instead: same direction of signal, weaker resolution, but
implementable against any chat-completion endpoint.

**Strengths**
- **Paraphrase-resistant.** Reducing continuation-perplexity back to
  human levels requires substantive rewriting, not search-and-replace.
- Domain-agnostic (no manual dictionary maintenance).
- Quantifiable: a single number to track over time.

**Failure mode**
- The reference LM matters a lot. A small / weak model assigns lower
  likelihood to all text and inflates perplexity. Thresholds are
  GPT-4-class defaults; re-tune via `T7PerplexityDetector.THRESHOLD_*`
  for other models.
- Professional English editing (common for non-native authors)
  reduces perplexity by polishing text into more predictable phrasing.
  The signal **does not distinguish a human author with a good editor
  from an LLM**.
- Boilerplate sections (Methods, Statistical Analysis) sit at low
  perplexity inherently. Run T7 on the abstract / introduction /
  discussion only, where authorial voice matters most.

**Cost.** Each scan costs one LLM API call per text segment (3 by
default). Skip T7 unless you have a specific reason to look.

## Severity tiers

| Perplexity range | Severity   | Interpretation |
|------------------|------------|----------------|
| ≥ 20             | (none)     | Normal academic English. |
| 10 – 20          | NOTE       | Low but ambiguous. Could be edited human prose. |
| 5 – 10           | SUSPICIOUS | Below typical academic range. Worth a second pair of eyes. |
| < 5              | CRITICAL   | Reference LM is essentially predicting the text exactly — characteristic of unedited LLM output. |

These are conservative defaults. Override via:

```python
from paperguard.detectors.t7_perplexity import T7PerplexityDetector
T7PerplexityDetector.THRESHOLD_NOTE = 18.0
T7PerplexityDetector.THRESHOLD_SUSPICIOUS = 8.0
T7PerplexityDetector.THRESHOLD_CRITICAL = 4.0
```

## Combining T6 and T7

The strongest signal is **both detectors flagging the same text**:

| T6 density | T7 perplexity | Read this as |
|------------|---------------|--------------|
| Low        | Normal (≥20)  | No LLM signal. |
| High       | Normal (≥20)  | Phrase tics but coherent prose — likely a human author with stylistic overlap. |
| Low        | Low (<10)     | Edited LLM output; phrases scrubbed but the underlying probability distribution still betrays it. |
| High       | Low (<10)     | Strongly suggestive of LLM authorship (paraphrase-resistant + lexical signal align). |

Neither column alone is a verdict. The role of PaperGuard is to surface
papers that warrant editor / reviewer attention — the human in the
loop makes the call.

## Dynamic dictionary

The T6 dictionary lives at `~/.paperguard/ai_dictionary.json` (override
via `PAPERGUARD_HOME`). Built-in phrases are compiled into the source;
the user dictionary **adds** more without modifying built-ins.

Refresh from a remote JSON file:

```bash
paperguard refresh-ai-dict --source https://example.org/llm_phrases.json
```

Expected JSON shape:

```json
{
  "version": 1,
  "phrases": {
    "gpt": ["new gpt tic", "..."],
    "claude": ["new claude tic"],
    "gemini": [],
    "other": []
  }
}
```

Refresh from a local corpus of suspected LLM output:

```bash
paperguard refresh-ai-dict --corpus suspected_llm.txt --provider gpt
```

This extracts 2- to 4-gram candidates that appear above a baseline
frequency and aren't dominated by stopwords. Inspect the diff with
`--dry-run` first:

```bash
paperguard refresh-ai-dict --corpus suspected_llm.txt --provider gpt --dry-run
```

After a refresh, the next `paperguard scan` picks up the new phrases
automatically. To merge dictionaries in CI, host the JSON file as a
build artifact and run `refresh-ai-dict --source <CI-url>` before each
scan.

## When to use each

| Situation | Run T6 | Run T7 |
|-----------|--------|--------|
| Bulk batch over many papers | ✅ (free) | ❌ (API cost) |
| Single paper deep dive | ✅ | ✅ |
| Author claims "I used LLM only for polishing" | ✅ (will show phrase signal if heavy) | ✅ (perplexity catches what polishing doesn't) |
| Paper is mostly equations / tables | T6 weak | T7 not applicable (too little prose) |
| Adversarial author rewrote phrases by hand | T6 will miss | T7 still has signal |
| You have no LLM API access | ✅ | ❌ |

The bias is conservative across the board: PaperGuard does not call
text "AI-generated" or "AI-written" in any finding. It reports
*signals consistent with* LLM authorship, with at least 3 innocent
explanations per finding (4 for T7).
