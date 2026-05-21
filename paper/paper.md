---
title: 'PaperGuard: A 34-detector open-source pipeline for triage-stage statistical-anomaly screening in research-data integrity'
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
date: 21 May 2026
bibliography: paper.bib
---

# Summary

`PaperGuard` is an open-source Python command-line tool and library for
**triage-stage** screening of statistical anomalies in scientific
manuscripts and their accompanying data. It composes 34 independent
detectors spanning seven methodological families — terminal-digit
distribution, Benford's law, arithmetic and decimal consistency, GRIM /
SPRITE / GRIMMER reverse-reconstruction tests, the Carlisle
baseline-plausibility procedure for randomised trials, perceptual-hash
and per-channel-histogram image forensics, paper-mill co-authorship
graph signatures, and a three-detector LLM-text layer (lexical
dictionary, continuation-perplexity proxy, and a DetectGPT-style
naturalness-curvature probe) — into a single uniform audit report.

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

`PaperGuard` integrates these published procedures and 26 additional
detectors into a single Python package with:

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

Detectors are organised into seven families summarised in Table 1.
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
| Image / metadata forensics | F1–F6, G1, G3, G4 | pHash duplication, splice forensics, per-channel histogram, EXIF, docx rsid, file-metadata |
| Text / authorship / paper-mill | M1, T1–T8 | Co-authorship graph, n-gram plagiarism, trial-outcome drift, data-availability audit, stylometry, three LLM-text detectors |

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

PaperGuard ships five public empirical studies and a sixth
cross-validation; all raw data and analysers are in the
[`scripts/`](https://github.com/exergyleizhou-ux/PaperGuard/tree/main/scripts) directory of the repository.

- **Text-layer studies (v8 / v9, N=85 OpenAlex retracted +
  matched controls via Europe PMC).** T6 lexical density at the
  default 0.003 threshold has LR+ ≈ 0 against Nature-tier
  post-publication retractions — copy-editing removes lexical LLM
  markers before publication. T6's value is therefore at the
  **pre-submission / preprint** stage, not as a
  post-publication forensic signal. This finding is documented in
  the technical report and re-quoted in the LLM-detection guide.
- **Image-layer study v2 (N=18, F1+F4+F6).** Demonstrates that
  the new F6 patch-splice detector contributes structurally
  different signal to F1 (intra-paper pHash) and F4 (cross-paper
  pHash). The study revealed that the default F6 thresholds had a
  75 % false-positive rate; PaperGuard 2.1.9 tightened the defaults
  to `z=6 / cluster=8` (the documented "triage tier"), reducing
  FPR to 62.5 %.
- **T8 controlled benchmark (N=20).** A pre-curated 10+10
  human-vs-LLM corpus confirmed that on weak chat-completion proxies
  (cliproxy `gpt-5.4-mini`), T8 produces noise (LR+ = 0). The
  detector correctly returns NOTE-level "inconclusive" findings on
  such endpoints rather than fabricated numbers; a GPT-4-class
  endpoint with logprobs is required for live LR+ measurement.
- **B4 statcheck cross-validation (N=41 ground-truth corpus).**
  Against an independent scipy-based p-value reference, B4 achieves
  recall = 100 %, decision-flip recall = 94.12 %, in line with
  the published statcheck protocol [@nuijten2016statcheck].

These transparent recall numbers — including the negative
findings — are an explicit design choice. PaperGuard publishes its
own false-negative rate and weak-endpoint failure modes alongside
its detection methodology so users can calibrate trust.

# Software quality

PaperGuard 2.1.10 ships 91 source files with 394 unit and
integration tests (3 additional network-dependent tests deselected
by default). The project enforces `ruff` style checks and
`mypy --strict` type checks in CI on Linux, macOS, and Windows for
Python 3.11 and 3.12. A `paperguard doctor` command runs a 19-item
environment health check (Python version, required and optional
dependencies, detector registry, plugin entry points, cache
directory writability, dynamic dictionary state, image-corpus
presence, and LLM endpoint configuration) and reports machine-
readable JSON suitable for CI pre-flight use.

The package is on PyPI as `paperguard` (current 2.1.10), with a
live browser demo at
[huggingface.co/spaces/exergyleizhou/paperguard-demo](https://huggingface.co/spaces/exergyleizhou/paperguard-demo).

# Acknowledgements

PaperGuard owes its statistical foundation to the work of James
Heathers, Nick Brown, Elisabeth Bik, John Carlisle, Michèle
Nuijten, Guillaume Cabanac, Dmitry Kobak, Eric Mitchell, and the
broader research-integrity community. The project is independent
and unaffiliated with any of the authors cited; any errors in the
implementation or interpretation are entirely the implementers'.

# References
