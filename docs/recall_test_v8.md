# recall_test_v8 — T6 lexical LLM-text recall study
PaperGuard 2.0.16 (T6 phrase-density only). N = 50 retracted + 38 controls, sampled from OpenAlex `is_retracted` filter + matched-subfield non-retracted control. Full text from Europe PMC.
## Coverage
- Retracted with PMC full text: **35 / 50**
- Controls with PMC full text:  **9 / 38**
- Matched pairs with both arms PMC-resolved: **8**

## T6 phrase-density distribution

| Arm | N | mean | median | P75 | P90 | P95 |
|---|---|---|---|---|---|---|
| retracted | 35 | 0.00017 | 0.00000 | 0.00000 | 0.00000 | 0.00158 |
| control | 9 | 0.00017 | 0.00000 | 0.00000 | 0.00031 | 0.00092 |

## T6 LR+ at candidate thresholds

LR+ = P(test+ | retracted) / P(test+ | control). Higher LR+ means a positive test moves you more toward suspecting the paper. LR+ ≥ 2 is the canonical threshold for 'useful for triage' in clinical-test literature.

| threshold | TPR (retracted) | FPR (control) | LR+ |
|---|---|---|---|
| ≥ 0.0005 | 8.57% | 11.11% | 0.77 |
| ≥ 0.0010 | 8.57% | 11.11% | 0.77 |
| ≥ 0.0020 | 5.71% | 0.00% | 0.57 |
| ≥ 0.0030 | 0.00% | 0.00% | 0.00 |
| ≥ 0.0050 | 0.00% | 0.00% | 0.00 |
| ≥ 0.0080 | 0.00% | 0.00% | 0.00 |

## Provider attribution (sub-threshold NOTE)

| Arm | gpt | claude | gemini | none |
|---|---|---|---|---|
| retracted | 3 | 0 | 0 | 32 |
| control | 1 | 0 | 0 | 8 |

## Interpretation

At the default CONCERN threshold (0.003), T6 achieves LR+ = 0.00. Below the 'useful for triage' bar; T6 alone is too weak for default-on. Consider raising the phrase-density threshold or combining with T7/T8.

## T7 / T8 limitations under cliproxy gpt-5.4-mini

T7 (perplexity) requires token-level logprobs in the response. The cliproxy endpoint silently drops the `logprobs` field; T7 therefore returns a NOTE-level inconclusive finding under that endpoint. T8 (DetectGPT curvature) needs the reference LM's paraphraser to drift OFF the LLM-likelihood manifold when applied to LLM-authored text. With gpt-5.4-mini, the paraphraser preserves LLM-style markers, so the original-vs-paraphrase score gap collapses to ≈0 on both arms. **Live LR+ measurement of T7 and T8 awaits access to a GPT-4o-class endpoint that exposes logprobs.**

T7/T8 are nonetheless shipped in 2.0.16: their unit-test coverage verifies algorithm correctness on synthetic inputs, the CLI flags are wired, and the detectors degrade gracefully (NOTE-level inconclusive) rather than emitting false positives on weak endpoints.

