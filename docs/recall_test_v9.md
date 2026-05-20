# recall_test_v9 — N=100 LR+ study (T6 + T7 + T8)

PaperGuard 2.1.0. Reference LM: `gpt-4o-mini (default)`. N = 30 retracted + 24 controls.

## Coverage

- Retracted with PMC full text: **25 / 30**
- Controls with PMC full text:  **10 / 24**

## T6 phrase-density LR+

| threshold | TPR | FPR | LR+ |
|---|---|---|---|
| ≥ 0.0005 | 0.00% | 0.00% | 0.00 |
| ≥ 0.0010 | 0.00% | 0.00% | 0.00 |
| ≥ 0.0020 | 0.00% | 0.00% | 0.00 |
| ≥ 0.0030 | 0.00% | 0.00% | 0.00 |
| ≥ 0.0050 | 0.00% | 0.00% | 0.00 |
| ≥ 0.0080 | 0.00% | 0.00% | 0.00 |

**T6 density distribution**

| arm | N | mean | median | P75 | P90 | P95 |
|---|---|---|---|---|---|---|
| retracted | 25 | 0.00000 | 0.00000 | 0.00000 | 0.00000 | 0.00000 |
| control | 10 | 0.00000 | 0.00000 | 0.00000 | 0.00000 | 0.00000 |

## T7 perplexity

T7 returned no perplexity values on the configured endpoint (`gpt-4o-mini (default)`). Outcomes per arm:

- Retracted: {'skip': 25}
- Controls:  {'skip': 10}

This is expected on endpoints that drop the `logprobs` field. Re-run on a logprobs-capable GPT-4o-class endpoint to populate the LR+ row.

## T8 DetectGPT score

T8 returned no scores on the configured endpoint (`gpt-4o-mini (default)`). Outcomes per arm:

- Retracted: {'skip': 25}
- Controls:  {'skip': 10}

This is expected on endpoints whose paraphraser preserves LLM-style markers — the original-vs-paraphrase score gap collapses to ≈0. Re-run on a GPT-4o-class endpoint to populate the LR+ row.

## Interpretation

At the default T6 CONCERN threshold (0.003), LR+ = 0.00 on N=25+10. Below the triage bar. T6 alone is too weak for post-publication Nature-tier screening; better use is pre-submission / preprint screening.

T7 / T8 empirical LR+ depends on having a GPT-4o-class endpoint with token logprobs and a paraphraser that drifts off the LLM-likelihood manifold. Re-run this script with such an endpoint configured to populate the T7/T8 rows.


