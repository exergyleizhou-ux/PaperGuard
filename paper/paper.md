---
title: 'PaperGuard: A 33-detector open-source pipeline for statistical anomaly screening in research-data integrity'
tags:
  - Python
  - research integrity
  - statistical forensics
  - LLM detection
  - GRIM
  - SPRITE
  - Carlisle
  - DetectGPT
authors:
  - name: PaperGuard Contributors
    affiliation: 1
affiliations:
  - name: Independent
    index: 1
date: 2026-05-20
bibliography: paper.bib
---

# Summary

`PaperGuard` is an open-source command-line and library pipeline for
**triage-stage** screening of statistical anomalies in scientific
manuscripts. It composes 33 independent detectors spanning seven
methodological families — terminal-digit distribution, Benford's law,
arithmetic consistency, GRIM / SPRITE / GRIMMER, Carlisle (RCT
baseline plausibility), image-forensic perceptual-hash detectors,
paper-mill co-authorship graph signatures, and an LLM-text layer
(lexical / perplexity / DetectGPT-style curvature) — into a single
audit report. Every finding ships with at least three innocent
explanations and refers the reader to the underlying test, so the
tool's output is structurally **non-verdict**: it surfaces papers
worth a human reviewer's attention, it does not render judgment.

# Statement of need

Existing research-integrity tools target single signals: `statcheck`
[@nuijten2016statcheck] re-computes p-values from reported test
statistics; the GRIM test [@brown2017grim] checks granularity-vs-mean
consistency; Carlisle's baseline-plausibility procedure
[@carlisle2017non] flags suspicious randomization in RCTs; pHash
forensics [@bik2016prevalence] catches image duplication. Each
addresses a real failure mode, but each lives in a separate codebase
with its own input format, threshold choices, and reporting style.

`PaperGuard` integrates these and 26 additional detectors into a
single Python package with a uniform `BaseDetector` interface, a
unified `Finding` data class carrying severity, innocent
explanations, and academic citations, and an evidence combiner
that aggregates per-detector p-values via Benjamini-Hochberg false
discovery rate correction and a Stouffer-style integrity index.

The pipeline targets three use cases:

- **Pre-submission self-audit** for authors who want to catch
  data-formatting inconsistencies before peer review.
- **Editorial-office triage** of high-volume submission streams,
  surfacing manuscripts with multiple cross-detector anomalies for
  human review.
- **Forensic re-examination** of post-publication concerns, where
  multi-detector concordance provides independent confirmation.

`PaperGuard` does **not** replace human review; the conservative
disclaimer architecture is the load-bearing trust mechanism.

# Design

The 33 built-in detectors fall into seven families (Table 1). Each
detector is a `BaseDetector` subclass with declared
`data_requirements`, an explicit random seed, and a return value
structured as `DetectorResult(findings: list[Finding])`. A regression
suite (`tests/test_golden.py`) ensures no new detector causes a
regression on a curated set of synthetic genuine inputs.

The cross-detector combiner (`paperguard.evidence.combiner`) computes
an `integrity_score` via Stouffer combination of BH-FDR-adjusted
p-values [@benjamini1995controlling]. High scores map to **severity**
levels (NOTE / CONCERN / SUSPICIOUS / CRITICAL) rather than to a
verdict.

The LLM-text family is the newest addition: T6 (lexical signature),
T7 (continuation-perplexity proxy), and T8 (DetectGPT-style
naturalness-curvature). T6 ships a built-in phrase dictionary curated
from Kobak et al. [@kobak2025delving] and Cabanac et al.
[@cabanac2024chatgpt] and a `paperguard refresh-ai-dict` command for
user updates. T7 and T8 adapt the published-literature techniques
[@mitchell2023detectgpt; @gehrmann2019gltr] to chat-completion
endpoints that do not expose `/v1/completions echo=true logprobs`.

# Empirical calibration

Two empirical studies measure the detectors against post-publication
retraction data:

- **Text-layer studies (v8 / v9, N=85)**: T6 lexical density at the
  default 0.003 threshold has LR+ ≈ 0 against Nature-tier
  retractions — copy-editing removes lexical LLM markers before
  publication. T6's value is therefore at the **pre-submission /
  preprint** stage. T7/T8 live LR+ awaits a logprobs-capable
  endpoint; on the test environment's weak-LM proxy they correctly
  fall back to a NOTE-level "inconclusive" finding.
- **Image-layer study (v1, N=60)**: F1 (intra-paper pHash) and F4
  (cross-paper pHash) are measured on the same OpenAlex-derived
  sample. Results are reported in `docs/recall_image_v1.md`.

These transparent recall numbers are an explicit design choice:
PaperGuard reports its own false-negative rate alongside its
detection methodology.

# Acknowledgements

PaperGuard owes its statistical foundation to the work of James
Heathers, Nick Brown, Matthew Pittelkow, Elisabeth Bik, John
Carlisle, Michèle Nuijten, Guillaume Cabanac, Dmitry Kobak,
Eric Mitchell, and the broader research-integrity community. The
project is independent and unaffiliated with any of the authors
cited.

# References
