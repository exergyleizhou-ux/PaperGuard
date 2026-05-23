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
  - name: Lei Zhou
    orcid: 0009-0000-9073-1349
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

PaperGuard ships 13 public empirical studies — a text-layer recall
benchmark series, four image-recall studies, an industrial-process
recall study, two cross-validation studies, and two controlled
LLM-endpoint benchmarks. All raw data and analysers live in the
repository's `scripts/` directory; per-study writeups are in `docs/`.
Headlines:

- **Text-layer recall (v10, 100 retracted + 100 OpenAlex matched
  controls via Europe PMC, 95 analysable).** The T6 lexical detector
  at its default 0.003 density threshold yields LR+ ≈ 0 against
  Nature-tier post-publication retractions, where copy-editing
  removes lexical LLM markers; at a stricter 0.001 threshold it
  yields **LR+ = ∞ (1 TP / 0 FP)**. T6's operating point is the
  pre-submission / preprint stage, not post-publication forensics
  (see `docs/recall_test_v10.md`).
- **Image-layer recall (v6, 163 retracted + 49 control = 212
  analysable).** At the documented `z=6 / cluster=8` defaults all
  three image detectors converge to **LR+ ≈ 1** (F1 1.09, F4 0.96,
  F6 0.89, with 95 % Wilson CIs all bracketing 1). The image layer
  is structurally tuned to the Bik-style patch-splice failure mode
  [@bik2016prevalence], which is rare in randomly-sampled retracted
  papers; on the biomedical OA corpus dominated by statistical-
  fabrication, paper-mill, and image-reuse failures, single-
  detector image LR+ is indistinguishable from chance. The layer
  retains value as a contributor to the cross-detector combiner
  (see `docs/recall_image_v6.md`).
- **Industrial-layer recall (v1, 2 domains × 50+50 synthetic
  datasets).** I5 (batch-repetition) achieves **LR+ = ∞** on the
  wastewater domain at template defaults (60 % TPR / 0 % FPR);
  I1 and I2 fire 100 % / 100 % indicating their tolerances need
  per-plant calibration. No direct prior art exists in the
  academic-integrity literature (see `docs/recall_industrial_v1.md`).
- **B4 statcheck cross-validation (N=41).** Against the R
  `statcheck` package on the same corpus, B4 achieves Cohen's
  κ = 0.79 on the decision-flip class — Landis-Koch substantial
  agreement [@landis1977measurement; @nuijten2016statcheck]
  (see `docs/crossval_statcheck_kappa.md`).
- **T7 controlled endpoint benchmark — five-endpoint study
  (10 + 10 corpus).** All four OpenAI models with logprobs show
  *reversed* direction (AI ppl > human ppl) at *p* ranging from
  0.047 (`gpt-4o-mini`) to 2.1 × 10⁻⁶ (`gpt-4`), with three of
  four giving LR+ = ∞ (TPR 70–90 %, FPR 0 %) at max(human)
  threshold. The non-OpenAI endpoint (Groq `qwen/qwen3-32b`)
  shows the textbook direction (LR+ = 1.69 weak). The pattern is
  not monotonic in model size, and OpenAI reasoning models
  (`o1`/`o3-mini`/`o4-mini`) API-block logprobs entirely. T7
  inversion is exposed as a per-endpoint configuration choice
  (auto-detected since 2.6.0) — see
  `docs/llm_detection_real_endpoints.md`.
- **T8 controlled endpoint benchmark.** On a non-reasoning
  paraphraser (OpenAI `gpt-4o`, N=10+10) T8 yields **LR+ = ∞**
  (2 / 10 TP, 0 / 10 FP). On a reasoning-model paraphraser
  (DeepSeek-v4-flash) the rewrites stay on-manifold and LR+
  collapses to 0.25 — directly validating the structural
  prediction in [@mitchell2023detectgpt]. The detector ships an
  authoritative endpoint-compatibility matrix.

Publishing these numbers at face value — including the image-
layer's LR+ ≈ 1 and the T7 inversion — is an explicit design
choice. PaperGuard publishes its own false-negative rates and
per-endpoint failure modes so users can calibrate trust.

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
