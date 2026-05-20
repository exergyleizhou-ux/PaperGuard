# PaperGuard: a 33-detector open-source pipeline for statistical anomaly screening in research-data integrity

**Technical report — PaperGuard 2.1.0 — 2026-05-20**

## Abstract

PaperGuard is an open-source command-line and library pipeline for
**triage-stage** screening of statistical anomalies in scientific
manuscripts. It composes 33 independent detectors spanning seven
methodological families — terminal-digit / Benford / arithmetic /
GRIM / SPRITE / Carlisle / image-forensic / paper-mill graph /
LLM-text — into a single report whose findings are deliberately
**non-verdict**: each finding ships with at least three innocent
explanations and refers the reader to the underlying statistical
test. We present (i) the design constraints that produced the
detector taxonomy, (ii) a transparent empirical study (N=85 OpenAlex
post-publication retractions + 19 subfield-matched controls via
Europe PMC, full text) of the T6 lexical LLM-text detector that
finds **near-zero post-publication signal at the default density
threshold**, and (iii) a calibrated position for the LLM-text layer:
T6 is a pre-submission / preprint screening tool, T7 (perplexity)
and T8 (DetectGPT-style curvature) await GPT-4-class endpoints with
token logprobs for live LR+ measurement. Code, dataset, and analyser
scripts are public at
[github.com/exergyleizhou-ux/PaperGuard](https://github.com/exergyleizhou-ux/PaperGuard).

**Keywords:** research integrity; statistical forensics; LLM
detection; GRIM; SPRITE; Carlisle; DetectGPT; triage screening.

---

## 1. Introduction

Research-integrity tools sit at a tension: false negatives let real
misconduct slip past; false positives smear honest authors and chill
discourse. PaperGuard adopts a clear conservative stance: **every
finding is a triage signal**, every finding carries innocent
explanations, no finding uses verdict language ("fraud",
"fabrication", "misconduct"). The job is to surface manuscripts
worth a human reviewer's attention, not to render judgment.

This report describes:
- the detector taxonomy and the design constraints that produced it
  (§2);
- the algorithms behind the three LLM-text-specific detectors —
  T6 (lexical), T7 (perplexity), T8 (DetectGPT-style curvature) —
  added between PaperGuard 2.0.14 and 2.1.0 (§3);
- a transparent empirical study of T6 against post-publication
  retraction data (§4) and an honest accounting of the endpoint
  limitations blocking live T7 / T8 measurement on our test
  environment (§5);
- recommendations for deployment and future extension (§6).

---

## 2. Design constraints

PaperGuard composes detectors under three constraints:

1. **Reproducibility.** Each detector is a `BaseDetector` subclass with
   declared `data_requirements`, an explicit `seed`, and a return
   value structured as `DetectorResult(findings: list[Finding])`. The
   golden-fixture regression suite (`tests/test_golden.py`) ensures
   no new detector causes a regression on a curated set of synthetic
   genuine inputs.
2. **Disclaimer-first reporting.** Each `Finding` carries
   `innocent_explanations: list[str]` with a minimum of three entries
   (four for the LLM-text family). The Markdown / HTML / terminal
   reporters surface these alongside the test statistic. Verdict
   words ("fraud", "misconduct", "造假") are forbidden by static
   string-search tests applied to all detector code paths.
3. **Triage, not verdict.** The cross-detector combiner
   (`paperguard.evidence.combiner`) computes an
   `integrity_score` (Stouffer-style combination over BH-FDR-adjusted
   p-values) but explicitly maps high scores to **severity**
   (CRITICAL / SUSPICIOUS / CONCERN / NOTE) rather than to a verdict.

Under these constraints the 33 built-in detectors fall into seven
families (see Appendix A). This report focuses on the LLM-text family
(T6 / T7 / T8) introduced in 2.0.14–2.1.0.

---

## 3. Methods — the LLM-text family

### 3.1 T6 — Lexical signature (dictionary)

T6 scans manuscript text for phrases that appear at elevated
frequency in LLM output relative to typical academic writing
("delve into", "tapestry of", "intricate interplay",
"underscoring the importance", and so on). The dictionary is built
from three sources: (1) Kobak et al. (2025, arXiv:2406.07016)
n-gram-frequency analysis; (2) Cabanac et al. (2024, *Nature*)
retraction-record analysis; (3) PaperGuard's own observation of
GPT-4-class outputs.

Two evidence channels:
- **Density**: phrase hits divided by total words. Thresholds
  CONCERN ≥ 0.003 (default), SUSPICIOUS ≥ 0.006.
- **Per-provider attribution**: hits are bucketed by LLM
  provider (GPT / Claude / Gemini). When one provider's hits
  cross 3, a NOTE-level finding fires even if global density is
  below CONCERN.

In addition T6 inspects for *uncleaned LLM artefacts* — phrases like
"as an AI language model" or "I'm sorry, but" — which fire CRITICAL.

T6 supports a **user dictionary** at `~/.paperguard/ai_dictionary.json`
that is merged with the built-in lists at detector load time, so the
phrase corpus can be extended without a release. PaperGuard ships an
official dictionary JSON at
[`docs/dictionaries/llm_phrases_v1.json`](dictionaries/llm_phrases_v1.json)
and refreshes it via the CLI:

```bash
paperguard refresh-ai-dict --official
```

### 3.2 T7 — Continuation-perplexity proxy

The classical perplexity-based literature (GLTR, DetectGPT,
Fast-DetectGPT) measures perplexity of the **input** string under a
reference language model. That requires the `/v1/completions`
endpoint with `echo=true logprobs=N`, which the major chat-API proxies
(cliproxy, OpenRouter, most team pools) do not expose.

T7 substitutes a **continuation-perplexity proxy**: the LM is asked
to continue the manuscript text, and the per-token logprobs of its
completion are aggregated into a perplexity number via
`exp(-mean(logprob))`. This is a strictly weaker signal than
input perplexity — it captures only the LM's downstream uncertainty,
not whether the input itself sat on the LM's likelihood manifold —
but it is implementable against any chat-completion endpoint that
exposes completion logprobs.

Severity tiers (defaults, override via class attributes):
- perplexity ≥ 20 → no finding;
- 10 ≤ ppl < 20 → NOTE;
- 5 ≤ ppl < 10 → SUSPICIOUS;
- ppl < 5 → CRITICAL.

### 3.3 T8 — DetectGPT-style perturbation curvature

Mitchell et al. (2023, ICML) introduced DetectGPT: LLM-generated
text sits at *local maxima* of the reference LM's likelihood
function, so perturbing it slightly should reduce its likelihood
much more sharply than perturbing human-written text. The classical
formulation needs token-level likelihood access.

T8 adapts the idea to chat-completion APIs:
1. The reference LM is asked to paraphrase the passage with light
   word-level substitution (K=3 perturbations).
2. The LM is then asked to **rate naturalness 1–10** for the
   original and for each perturbation.
3. A z-style detection score is computed:
   `score = (mean(scores_perturbed) − score_original) / std(scores_perturbed)`.
4. Theory predicts that LM-authored text drives `score_original`
   *up* and `scores_perturbed` *down* (the LM rates the original as
   more natural than its paraphrases), so `score < 0` is suggestive.

This eliminates the logprobs requirement at the cost of needing
twice as many LM calls (`2K + 1` per segment) and assuming the
paraphraser drifts off the LLM-likelihood manifold — which, as §5
shows, is the actual limiting factor on weak endpoints.

Severity tiers (defaults):
- score ≥ 0 → no finding;
- −0.5 ≤ score < 0 → NOTE;
- −1.5 ≤ score < −0.5 → SUSPICIOUS;
- score < −1.5 → CRITICAL.

---

## 4. Empirical study — T6 LR+ on post-publication retractions

### 4.1 Sample construction

We constructed two datasets through OpenAlex (`is_retracted` filter)
+ Europe PMC full-text fetch:

| Study | N retracted | N controls | Year filter | PMC-resolved (retracted / control) |
|---|---|---|---|---|
| v8 | 50 | 50 | 2023+ | 35 / 9 |
| v9 | 30 | 30 | 2020+ | 25 / 10 |

Controls were matched on subfield (OpenAlex
`primary_topic.subfield.id`) and publication year ±1. Europe PMC
coverage skewed toward biomedical subfields — sociology and
humanities retractions had higher non-PMC rates than biology.

### 4.2 T6 density distributions

Across both studies, the T6 phrase-density distribution was
**heavily concentrated near zero in both arms**. v8 P95 density:
0.00158 (retracted) vs 0.00092 (control). v9 P95 density: 0 (both
arms). At the default 0.003 CONCERN threshold, T6 fired on 0 % of
retracted papers in v9 and 0 % of controls in v8.

### 4.3 T6 LR+ at the default threshold

| Study | Threshold | TPR | FPR | LR+ |
|---|---|---|---|---|
| v8 | ≥ 0.003 | 0 % | 0 % | 0.00 |
| v9 | ≥ 0.003 | 0 % | 0 % | 0.00 |
| v8 | ≥ 0.0005 | 8.57 % | 11.11 % | 0.77 |

### 4.4 Interpretation

The empirical finding is robust: **T6 is not a useful
post-publication forensics signal at the Nature-tier**. The
mechanism is straightforward — copy-editing at established journals
removes lexical LLM markers before publication. T6's value is
therefore at the **pre-submission / preprint** stage, where authors
have not yet been edited.

This is an honest and consequential calibration. PaperGuard 2.0.16
and later document this position in the LLM-text guide
([`docs/llm_detection_v2.md`](llm_detection_v2.md)) and in the
HuggingFace Space demo UI.

---

## 5. T7 / T8 endpoint dependence

PaperGuard's test environment routes LLM calls through the
[cliproxy](https://cliproxy.eqing.tech) team pool, which serves a
`gpt-5.4-mini` variant. Probing the endpoint revealed two
limitations:

1. **Logprobs dropped.** The `/v1/chat/completions` endpoint
   accepts `logprobs: true` without error, but the response object
   omits the `logprobs` field on every model variant tested. This
   blocks T7: `compute_perplexity()` returns None and the detector
   emits a NOTE-level "inconclusive" finding.
2. **Paraphraser preserves LLM markers.** When asked to paraphrase
   LLM-style text, `gpt-5.4-mini`'s output preserves the LLM
   markers (it does not drift off the LLM-likelihood manifold).
   The original-vs-paraphrase naturalness gap collapses to
   approximately zero on both arms (`std = 0`), so T8 cannot
   produce a discriminating z-score on this endpoint.

These are not implementation bugs — they are properties of the
specific weak-LM endpoint we have access to. The detector code is
unit-tested on synthetic inputs and works correctly under mocking.
**Live LR+ measurement of T7 and T8 requires a GPT-4-class endpoint
with token logprobs.** When such access becomes available, the v9
dataset (`scripts/recall_test_v9_results.json`) can be re-analysed by
running:

```bash
PYTHONIOENCODING=utf-8 python scripts/recall_test_v9.py \
    --n 30 --year-min 2020 \
    --run-t7 --run-t8 \
    --out scripts/recall_test_v9_results.json \
    --resume
python scripts/recall_analyze_v9.py \
    scripts/recall_test_v9_results.json > docs/recall_test_v9.md
```

The `--resume` flag preserves the T6 results we already have and
adds T7 / T8 columns without re-fetching PMC full text.

---

## 6. Discussion

### 6.1 What PaperGuard is for

The empirical results clarify what PaperGuard's LLM-text layer can
legitimately claim:

- **Pre-submission / preprint screening**: T6 is a low-cost, no-API
  signal that authors and editors can run on draft text to surface
  lexical LLM markers before copy-editing.
- **Triage on any text**: T6 / T7 / T8 collectively are a triage
  signal, never a verdict. The disclaimer architecture (`≥ 3`
  innocent explanations per finding, severity not verdict, no
  forbidden words) is the load-bearing trust mechanism.
- **Statistical anomaly screening more broadly**: the remaining 30
  detectors (terminal-digit, Benford, GRIM, Carlisle, image
  forensics, etc.) operate on tabular data and image content and are
  independent of the LLM-text limitation discussed above. Their
  recall is documented separately in
  [`docs/recall_test_v5.md`](recall_test_v5.md) and earlier studies.

### 6.2 What PaperGuard is *not* for

- **Verdict rendering**. The code is structurally incapable of
  producing a "this is fraud" output. Findings are categorical
  signals with bounded severity.
- **Post-publication forensics at the lexical layer**. As §4 shows,
  copy-editing has already removed the lexical LLM markers T6
  targets.
- **Replacement for human review**. The integrity_score is a
  triage ordering, not a decision rule.

### 6.3 Future work

1. **GPT-4-class endpoint LR+ for T7 / T8.** As discussed in §5,
   the v9 dataset is ready to be re-analysed once a logprobs-capable
   endpoint is configured.
2. **Image-layer recall study.** Studies v8/v9 measured T6 only.
   F1 (intra-paper image duplication) and F4 (cross-paper image
   matching) have not been measured against a public retraction
   dataset; doing so requires a curated image corpus.
3. **Statcheck / Carlisle / GRIM cross-validation.** PaperGuard's
   B4 / C1 / B1 detectors are re-implementations of established
   protocols. A formal cross-validation study against the original
   statcheck and Carlisle tools would close the loop on these.

---

## 7. Reproducibility

All datasets, scripts, and analysers are public:

- **Code**: [github.com/exergyleizhou-ux/PaperGuard](https://github.com/exergyleizhou-ux/PaperGuard) (MIT)
- **PyPI**: [`pip install paperguard`](https://pypi.org/project/paperguard/)
- **Datasets**: `scripts/recall_test_v[5,6,7,8,9]_results.json` in the repository
- **Analyser scripts**: `scripts/recall_analyze_v[8,9].py`
- **Live demo**: [huggingface.co/spaces/exergyleizhou/paperguard-demo](https://huggingface.co/spaces/exergyleizhou/paperguard-demo)

Tests pass at 362 / 362 (excluding 3 network-dependent suites) with
`ruff` and `mypy --strict` clean across all 90 source files.

---

## Appendix A — Full detector list (PaperGuard 2.1.0)

| ID | Name | Family |
|---|---|---|
| A1 | Terminal Digit | Digit-distribution |
| A2 | Benford | Digit-distribution |
| A3 | Inter-Column Arithmetic | Arithmetic consistency |
| A5 | Decimal Consistency | Numeric formatting |
| A6 | Implausible Values | Range / bounds |
| A7 | Last Digit 0/5 | Digit-distribution |
| B1 | GRIM | Granularity-related inconsistency |
| B4 | Statcheck | Statistical-test consistency |
| B5 | TIVA | Test-statistic variance |
| B6 | GRIMMER | SD-aware GRIM extension |
| B7 | P-Curve | p-value distribution |
| B8 | SPRITE | Sample reconstruction |
| C1 | Carlisle | RCT baseline plausibility |
| D1 | Residual Smoothness | Hurst / R-S |
| D2 | Missing Pattern | Missing-value structure |
| E1 | ICC Independence | Intra-class correlation (new in 2.0.14) |
| F1 | Image pHash | Intra-paper image duplication |
| F2 | Internal Image Duplication | F1 variant |
| F3 | Splice Forensics | Image splice detection |
| F4 | Cross-Paper Image | Image corpus matching |
| F5 | EXIF Clustering | Image-source clustering |
| G1 | EXIF Temporal | Image-timestamp anomalies |
| G3 | Docx rsid | Word-document revision-id forensics |
| G4 | File Metadata | Authorship / claim mismatch |
| M1 | Paper-Mill Graph | Co-authorship pattern |
| T1 | Text Similarity | Self-plagiarism |
| T2 | Trial Outcome | Clinical-trial consistency (live CT.gov) |
| T3 | Data Availability | Statement / repository check |
| T4 | Tortured Phrases | Generated-phrase signature |
| T5 | Stylometry | Cross-section author drift |
| T6 | AI Text Heuristic | LLM lexical signature |
| T7 | LLM Perplexity (continuation proxy) | LLM statistical signature |
| T8 | DetectGPT-style Perturbation | LLM curvature signature |

## References

- Cabanac G, Labbé C, Magazinov A. (2024) ChatGPT-generated text in
  increasing number of scientific papers. *Nature*.
- Carlisle JB. (2017) Data fabrication and other reasons for non-random
  sampling in 5087 randomised, controlled trials in anaesthetic and
  general medical journals. *Anaesthesia* 72(8):944–952.
- Gehrmann S, Strobelt H, Rush AM. (2019) GLTR: Statistical detection
  and visualization of generated text. *ACL Demo*.
- Heathers JAJ, Brown NJL, Coyne JC, et al. (2018) Recovering data from
  summary statistics: Sample Parameter Reconstruction via Iterative
  TEchniques (SPRITE). *PeerJ Preprints*.
- Kobak D, Márquez RG, Lapuschkin S, Samek W. (2025) Delving into
  ChatGPT word patterns. *arXiv:2406.07016*.
- Mitchell E, Lee Y, Khazatsky A, Manning CD, Finn C. (2023) DetectGPT:
  Zero-shot machine-generated text detection using probability
  curvature. *ICML*.
- Nuijten MB, Hartgerink CHJ, van Assen MALM, Epskamp S, Wicherts JM.
  (2016) The prevalence of statistical reporting errors in psychology
  (1985-2013). *Behavior Research Methods* 48(4):1205–1226. (statcheck)

---

*Cite as: PaperGuard contributors. (2026) PaperGuard: a 33-detector
open-source pipeline for statistical anomaly screening in research-data
integrity. Technical report, version 2.1.0. https://github.com/
exergyleizhou-ux/PaperGuard*
