---
title: 'PaperGuard: A 39-detector open-source pipeline for triage-stage statistical-anomaly screening in research-data integrity'
tags:
  - Python
  - research integrity
  - statistical forensics
  - LLM detection
  - image forensics
  - GRIM
  - SPRITE
  - Carlisle
  - statcheck
  - DetectGPT
authors:
  - name: PaperGuard Contributors
    orcid: 0000-0000-0000-0000
    affiliation: 1
affiliations:
  - name: Independent
    index: 1
date: 23 May 2026
bibliography: paper.bib
---

# Summary

`PaperGuard` is an open-source Python command-line tool and library for
**triage-stage** screening of statistical anomalies in scientific
manuscripts, their accompanying data, and industrial process logs. It
composes 39 independent detectors spanning eight methodological
families — terminal-digit distribution, Benford's law, arithmetic and
decimal consistency, GRIM / SPRITE / GRIMMER reverse-reconstruction
tests, the Carlisle baseline-plausibility procedure for randomised
trials, perceptual-hash and per-channel-histogram image forensics,
paper-mill co-authorship graph signatures, a three-detector LLM-text
layer (lexical dictionary, continuation-perplexity, and a DetectGPT
naturalness-curvature probe), and a four-detector **industrial layer**
(mass-balance closure, SCADA timestamp integrity, batch-repetition
detection, and process-trend over-smoothness) covering 12
preconfigured domains (wastewater, waste-gas, pharmaceutical,
semiconductor, food, environmental, agricultural, biopharma,
biocomputation, distillation, chemical, and medical) — into a single
uniform audit report.

Every `Finding` ships with at least three plausible innocent
explanations and refers the reader back to the underlying statistical
test. Verdict language ("fraud", "fabrication", "misconduct") is
forbidden in the codebase by a static check applied to all detector
code paths. The tool is therefore structurally **non-verdict**: its
purpose is to surface manuscripts worth a human reviewer's attention,
not to render judgment.

# Statement of need

Existing research-integrity tools target single signals:
`statcheck` [@nuijten2016statcheck] re-computes p-values from
reported test statistics; the GRIM test [@brown2017grim] checks
granularity-vs-mean consistency in summary statistics; the Carlisle
baseline-plausibility procedure [@carlisle2017non] flags suspicious
randomization in clinical trials; SPRITE [@heathers2018sprite] tries
to reconstruct sample distributions from summary statistics; pHash
forensics has been used since Bik et al. [@bik2016prevalence] to
catch image duplication. Each addresses a real failure mode, but
each lives in a separate codebase (often in R rather than Python)
with its own input format, threshold choices, and reporting style.

`PaperGuard` integrates these published procedures and 30+ additional
detectors — including a four-detector industrial layer for process-data
forensics that has no direct prior art in the academic-integrity
literature — into a single Python package with:

1. A uniform `BaseDetector` interface and a uniform `Finding`
   structure carrying severity, innocent explanations, academic
   citations, and applicability notes.
2. A cross-detector combiner (`paperguard.evidence.combiner`) that
   aggregates per-detector p-values via Benjamini-Hochberg false
   discovery rate correction [@benjamini1995controlling] and a
   Stouffer-style integrity index.
3. A plugin entry-point system that lets third parties register
   custom detectors without forking the codebase.
4. A `paperguard doctor` diagnostic command for environment
   pre-flight checks suitable for CI use.

The pipeline targets three use cases:

- **Pre-submission self-audit** for authors who want to catch
  data-formatting inconsistencies before peer review.
- **Editorial-office triage** of high-volume submission streams,
  surfacing manuscripts with multiple cross-detector anomalies for
  human review.
- **Forensic re-examination** of post-publication concerns, where
  multi-detector concordance provides independent corroboration.

`PaperGuard` does **not** replace human review; the conservative
disclaimer architecture is the load-bearing trust mechanism.

# Design

Detectors are organised into eight families summarised in Table 1.
Each is a `BaseDetector` subclass with declared `data_requirements`,
an explicit random seed, and a return value structured as
`DetectorResult(findings: list[Finding])`. A golden-fixture
regression suite (`tests/test_golden.py`) ensures no new detector
causes a regression on a curated set of synthetic genuine inputs.

| Family | Detectors | Example methods |
|---|---|---|
| Digit-distribution | A1, A2, A7 | Terminal digit, Benford, last-digit 0/5 |
| Arithmetic / bounds | A3, A5, A6 | Inter-column arithmetic, decimal consistency, plausible ranges |
| Summary-statistic consistency | B1, B4, B5, B6, B7, B8 | GRIM, statcheck, TIVA, GRIMMER, p-curve, SPRITE |
| Clinical-trial plausibility | C1 | Carlisle baseline-imbalance |
| Variance / independence | D1, D2, E1 | Residual smoothness, missing-pattern, intra-class correlation |
| Image / metadata forensics | F1–F6, G1, G3, G4, G5 | pHash duplication, splice forensics, per-channel histogram, EXIF, docx rsid, file-metadata, reagent / equipment year-of-citation temporal consistency |
| Text / authorship / paper-mill | M1, T1–T8 | Co-authorship graph, n-gram plagiarism, trial-outcome drift, data-availability audit, stylometry, three LLM-text detectors |
| Industrial process data | I1, I2, I5, I6 | Mass-balance closure, SCADA timestamp integrity, batch-repetition detection, process-trend over-smoothness |

The cross-detector combiner produces an `integrity_score` by
Stouffer-style combination of BH-FDR-adjusted p-values. The score
maps to severity tiers (NOTE / CONCERN / SUSPICIOUS / CRITICAL)
rather than to a verdict.

The LLM-text family is the most recent addition. T6 (lexical
signature) ships a built-in phrase dictionary curated from
Kobak et al. [@kobak2025delving] and Cabanac et al.
[@cabanac2024chatgpt], plus a `paperguard refresh-ai-dict` command
that lets users extend the dictionary without waiting for a release.
T7 and T8 adapt published-literature techniques
[@mitchell2023detectgpt; @gehrmann2019gltr] so they function on
chat-completion endpoints that do not expose the legacy
`/v1/completions echo=true logprobs` interface.

# Empirical calibration

PaperGuard ships 13 public empirical studies, including a recall
benchmark series (v1 – v10), four image-recall studies, an
industrial-process recall study, two cross-validation studies, and
two controlled LLM-endpoint benchmarks. All raw data and analysers
are in the
[`scripts/`](https://github.com/exergyleizhou-ux/PaperGuard/tree/main/scripts) directory of the repository; per-study writeups
are in [`docs/`](https://github.com/exergyleizhou-ux/PaperGuard/tree/main/docs).

- **Text-layer recall (v10, 100 OpenAlex retracted + 100 matched
  controls via Europe PMC; 95 with parsable full text).** At the default 0.003 lexical-density
  threshold T6 has positive likelihood ratio LR+ ≈ 0 against
  Nature-tier post-publication retractions — copy-editing largely
  removes lexical LLM markers before publication. At a stricter
  0.001 threshold T6 achieves **LR+ = ∞ (1 TP / 0 FP)**: one
  retracted manuscript exceeds the density bar while every control
  stays below. T6's operating point is therefore the
  **pre-submission / preprint** stage, not post-publication
  forensics. Both numbers are public; the conservative default is
  the one shipped in the CLI.
- **Image-layer recall (v6, 163 retracted + 49 control = 212
  analysable; raw arm sizes 200 + 83 before OA-fetch attrition,
  with `has_pmid:true` filter on both arms to reduce v5's
  attrition asymmetry).** At the documented `z=6 / cluster=8`
  defaults all three image detectors converge to **LR+ ≈ 1**:
  F6 (patch-splice) 0.89, 95 % Wilson CI [0.74, 1.12]; F4
  (cross-paper pHash) 0.96 [0.28, 3.46]; F1 (intra-paper pHash)
  1.09 [0.44, 2.86]. v5's apparent F4 LR+ = 4.36 (1 false
  positive in 48 controls) collapses to 0.96 with 5 false
  positives in 49 controls — that earlier figure was the
  small-sample artifact v5 had already flagged but could not
  yet quantify. The image layer at PaperGuard's published
  defaults is **structurally tuned to the Bik-style
  patch-splice / Western-blot-duplication failure mode**, which
  is rare in randomly-sampled retracted papers; on the
  biomedical OA corpus dominated by statistical-fabrication,
  paper-mill, and image-reuse failures, the layer's single-
  detector LR+ is indistinguishable from chance. PaperGuard
  publishes this study at face value precisely because the
  alternative — quoting v4's small-N LR+ of 1.63 as if it were
  a calibrated operating point — would be the kind of
  mis-calibration the tool exists to flag. The image layer
  retains value as a contributor to the cross-detector
  combiner; future work needs F6 calibration against a
  Bik-curated patch-splice corpus that is not publicly
  redistributable today.
- **Industrial-layer recall (v1, 2 domains × N=50 clean + 50
  tampered = 200 synthetic datasets total).** On the wastewater
  domain at template-default thresholds, I5 (batch-repetition
  detection) achieves **LR+ = ∞** (60 % TPR, 0 % FPR); I1
  (mass-balance) and I2 (timestamp integrity) fire on 100 %
  TPR / 100 % FPR at the same defaults, indicating their
  out-of-the-box tolerances need calibration to the local plant's
  noise floor before they discriminate. On the pharma domain all
  three detectors fire at 100 % / 100 %. The industrial layer is
  the most recent addition and has no direct prior art in the
  academic-integrity literature; this study sets a **lower bound**
  on detector capability against synthetic ground truth, not an
  upper bound against real EPA / FDA enforcement actions.
- **B4 statcheck cross-validation (N=41 ground-truth corpus).**
  Against an independent scipy-based p-value reference, B4 achieves
  recall = 100 % and decision-flip recall = 94.12 %. A separate
  cross-validation directly against the R `statcheck` package on the
  same corpus yields Cohen's κ = 0.79 (Landis-Koch substantial
  agreement) on the decision-flip class
  [@landis1977measurement; @nuijten2016statcheck].
- **T7 controlled endpoint benchmark — five-endpoint study
  (10+10 controlled corpus per run).** Across the five real-logprobs
  endpoints tested, the four OpenAI models all show reversed
  direction (AI continuation perplexity > human, opposite of the
  classical DetectGPT assumption), while the one non-OpenAI
  endpoint (Groq `qwen/qwen3-32b`) shows the textbook direction.
  At an inverted threshold equal to the maximum human perplexity
  observed in the corpus, three of four OpenAI runs yield
  LR+ = ∞ (i.e. no false positive) at TPR 70–90 %:
  `gpt-3.5-turbo` (LR+ = ∞, TPR 90 %, *p* = 0.0009),
  `gpt-4` (LR+ = ∞, TPR 90 %, *p* = 2.1 × 10⁻⁶),
  `gpt-4o` (LR+ = ∞, TPR 70 %, *p* = 0.0011);
  `gpt-4o-mini` shows the same reversal more weakly
  (*p* = 0.047, LR+ = 1.57 at median(human)).
  Groq `qwen/qwen3-32b` gives textbook-direction LR+ = 1.69
  (*p* = 0.11, weak). The pattern is **not monotonic in model
  size** — both `gpt-3.5-turbo` (small, early) and `gpt-4` (older
  base) outperform `gpt-4o` (newer, larger) at this task — so the
  driver of the inversion is the specific RLHF training schedule
  rather than parameter count. PaperGuard exposes the inversion
  as a per-endpoint configuration choice
  (`PAPERGUARD_T7_INVERT_THRESHOLD` env var, auto-detected for
  OpenAI endpoints since 2.6.0). OpenAI reasoning models
  (`o1`, `o3-mini`, `o4-mini`) cannot be used as T7 reference LMs
  at all: the OpenAI API returns HTTP 400 *"You are not allowed
  to request logprobs from this model"* — a clean infrastructure-
  level confirmation of the structural-incompatibility claim
  PaperGuard had previously argued only on empirical grounds.
- **T8 controlled endpoint benchmark.** Two real-endpoint runs.
  On a non-reasoning paraphraser (OpenAI `gpt-4o`, N=10+10) T8
  yields LR+ = ∞ (2 / 10 TP, 0 / 10 FP) — the cleanest result
  PaperGuard has on the DetectGPT family. On a reasoning-model
  paraphraser (DeepSeek-v4-flash, N=10+10) the rewrites stay on
  the LLM-likelihood manifold, the Mitchell-style probability-
  curvature signal inverts, and measured LR+ collapses to 0.25 —
  worse than coin flip — directly validating the structural
  prediction made in [@mitchell2023detectgpt]. The detector ships
  an authoritative compatibility matrix
  (`docs/llm_detection_real_endpoints.md`) documenting which
  endpoint classes the method is mathematically valid on
  (non-reasoning `gpt-4o`, self-hosted Llama-3.3-70B) and which it
  is structurally incompatible with (OpenAI o-series,
  DeepSeek-v4, Qwen3-thinking, GPT-5).

These transparent recall numbers — including the negative findings
and structural-incompatibility notes — are an explicit design choice.
PaperGuard publishes its own false-negative rate and per-endpoint
failure modes alongside its detection methodology so users can
calibrate trust.

# Software quality

PaperGuard 2.6.1 ships 103 source files with 539 unit and
integration tests (3 additional network-dependent tests deselected
by default). The project enforces `ruff` style checks and
`mypy --strict` type checks in CI on Linux, macOS, and Windows for
Python 3.11 and 3.12. A `paperguard doctor` command runs a
19-item environment health check (Python version, required and
optional dependencies, detector registry, plugin entry points, cache
directory writability, dynamic dictionary state, image-corpus
presence, and LLM endpoint configuration) and reports
machine-readable JSON suitable for CI pre-flight use.

The package is on PyPI as `paperguard` (current 2.6.1), with a live
browser demo at
[huggingface.co/spaces/exergyleizhou/paperguard-demo](https://huggingface.co/spaces/exergyleizhou/paperguard-demo)
and multi-architecture Docker images
(`linux/amd64` + `linux/arm64`) on the GitHub Container Registry at
`ghcr.io/exergyleizhou-ux/paperguard:latest`.

# Acknowledgements

PaperGuard owes its statistical foundation to the work of James
Heathers, Nick Brown, Elisabeth Bik, John Carlisle, Michèle
Nuijten, Guillaume Cabanac, Dmitry Kobak, Eric Mitchell, and the
broader research-integrity community. The project is independent
and unaffiliated with any of the authors cited; any errors in the
implementation or interpretation are entirely the implementers'.

# References
