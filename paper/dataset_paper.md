---
title: 'The PaperGuard research-integrity benchmark suite: a 13-dataset corpus for empirical evaluation of statistical, image, and LLM-text anomaly detectors'
authors:
  - name: PaperGuard Contributors
    orcid: 0000-0000-0000-0000
    affiliation: 1
affiliations:
  - name: Independent
    index: 1
target-journal: Scientific Data (Springer Nature)
target-track: Data Descriptor
status: outline / draft
date: 23 May 2026
---

# Outline + draft (not for submission yet)

> Companion to the [JOSS software paper](paper.md). The JOSS paper
> describes **the tool**; this paper describes **the empirical
> corpora used to calibrate it**. JOSS DOI is a prerequisite for
> citing the tool from this dataset paper.

## Why submit to Scientific Data

Scientific Data publishes "data descriptors" — peer-reviewed
articles describing scientifically valuable datasets, with the
data themselves deposited in a recognised repository (Zenodo,
figshare, Dryad). The 13 PaperGuard recall studies fit cleanly:

- They are reproducible (raw JSON + Python analyser scripts).
- They have non-trivial scientific value: empirical likelihood
  ratios for individual statistical-anomaly detectors that are
  not currently quantified in the research-integrity literature.
- They are tested against known ground truth (post-publication
  retractions via OpenAlex / Europe PMC).
- They are reusable: anyone building a competing research-
  integrity tool can use them as a benchmark.

Median Scientific Data time-to-publication: 4-6 months.

## Proposed abstract (250 words)

> Detecting fabricated or otherwise anomalous data in published
> research is constrained by the lack of public benchmark
> datasets against which competing detectors can be evaluated. We
> describe a corpus of 13 reproducible empirical studies covering
> three orthogonal anomaly families: (1) statistical reporting
> consistency, evaluated against an N=41 ground-truth corpus
> cross-validated with the R `statcheck` package (Cohen's κ =
> 0.79 between PaperGuard's Python re-implementation and the
> reference R tool); (2) image forensics, evaluated on N=132+48
> open-access PDFs of OpenAlex-retracted papers and matched
> controls with three per-channel detectors (intra-paper
> perceptual hash, cross-paper perceptual hash, and patch-splice
> per-channel histogram); and (3) LLM-text detection, evaluated
> on N=200 retracted/control papers via lexical phrase density
> at multiple density thresholds, plus controlled benchmarks of
> continuation-perplexity and DetectGPT-curvature methods against
> known LLM-authored vs human-authored prose corpora. We report
> per-detector positive likelihood ratios with Wilson 95 %
> confidence intervals, document the per-endpoint failure modes
> of reasoning-model paraphrasers on DetectGPT-style probes
> (LR+ collapses to 0.25 on DeepSeek-v4-flash), and release all
> raw run outputs, analysis scripts, and an installable Python
> implementation under the MIT license. The corpus is the largest
> public ground-truth resource for research-integrity detector
> benchmarking known to the authors at submission and is intended
> to support reproducible evaluation of future detectors.

## Sections (proposed)

### 1. Background and summary

- Why research-integrity detectors need shared benchmarks
  (parallels: BLEU/GLUE in NLP, BraTS in medical imaging).
- Why each existing approach (statcheck, GRIM, Carlisle, Bik
  pHash, DetectGPT) sits in its own codebase with its own
  evaluation set.
- The 13 studies cover all three anomaly families.

### 2. Methods

- Data sources: OpenAlex (`is_retracted:true`), Europe PMC for
  OA full text, Unpaywall for fallback OA, controlled synthetic
  corpora for T7/T8 (10 + 10 human-vs-AI prose) and industrial
  layer (50 + 50 per domain × 2 domains).
- Per-study ground truth construction: retraction-notice
  filtering, matched-control selection by year and subfield, hand
  inspection of edge cases.
- Reproducibility: every study is one `scripts/recall_*.py` run +
  one `scripts/recall_analyze_*.py` run; the latter prints the
  Markdown table that appears in the corresponding
  `docs/recall_*.md` writeup.
- License: all raw run outputs and analyser code released MIT.
  PDFs themselves are not redistributed; the analyser scripts
  re-fetch from public OA sources on demand.

### 3. Data records (Table 1)

| Study ID | What it tests | N (usable) | Headline LR+ | Notes |
|---|---|---|---|---|
| recall_test_v5 | T6 lexical, F1/F4 image, B-family stats | 100+100 | T6 ≈ 0 at default | v5 is the legacy "full pipeline" arm; later text and image studies split it. |
| recall_test_v8 | T6 lexical only, N=50 | 50+50 | T6 LR+ ≈ 0 at default 0.003 | First focused T6 measurement against retractions. |
| recall_test_v9 | Same as v8, N=30 retest + T7/T8 columns wired | 30+30 | T6 unchanged | Documents cliproxy logprobs gap. |
| **recall_test_v10** | **T6 lexical, N=200, multiple thresholds** | **100+95** | **T6 LR+ = ∞ at 0.001** (1 TP / 0 FP) | **The headline academic-layer result.** |
| recall_image_v1 | F1/F4 image, N=15+15 | small | F1/F4 around 1.0-1.5 | First image-layer study. |
| recall_image_v2 | + F6 patch-splice | small | F6 FPR=75% at relaxed defaults | Triggered 2.1.9 calibration. |
| recall_image_v3 | + F6 at z=6/cluster=8 | 85 | F6 LR+ = 1.91 | Default calibration confirmed on N=85. |
| recall_image_v4 | F1/F4/F6 at calibrated defaults | 132+27 | F6 LR+ = 1.63 | Small-sample upward fluctuation. |
| **recall_image_v5** | **F1/F4/F6, N=200+200 target** | **132+48** | **F6 LR+ = 0.92 [0.75, 1.20]** | **Honest revision: v4's 1.63 was sampling noise. F4 LR+ ≈ 4.4 with wide CI.** |
| recall_industrial_v1 | I1/I2/I5 mass-balance / SCADA / batch-repetition | 50+50 wastewater + 50+50 pharma | **I5 wastewater LR+ = ∞** | Industrial layer headline. |
| crossval_statcheck | B4 vs scipy reference | 41 | recall 100%, decision-flip 94% | Cross-validation against the published statcheck protocol. |
| **crossval_statcheck_kappa** | **B4 vs statcheck-R itself** | **41** | **Cohen's κ = 0.79** | Cross-language cross-implementation agreement. |
| t7_controlled_benchmark | T7 perplexity vs 10+10 corpus | 17 | LR+ = 1.69, p ≈ 0.11 | Real-but-weak signal; non-reasoning LM with real logprobs required. |
| t8_controlled_benchmark | T8 DetectGPT vs same corpus | 20 | **LR+ = 0.25 (reversed)** | Documents structural incompatibility with reasoning-model paraphrasers. |

### 4. Technical validation

- For each study: per-detector confusion matrix at the documented
  default threshold + a Wilson 95 % CI on the LR+ estimate (added
  in 2.3.1's analyser refresh).
- For T6: the v10 result is shown across 4 thresholds
  (0.0001 / 0.001 / 0.003 / 0.01) to make the threshold-vs-LR+
  tradeoff explicit.
- For F1/F4/F6: v3 → v4 → v5 progression shows the small-sample
  upward fluctuation in v4 collapsing back to ~1 at v5's N=132+48.
  We frame this **as a feature of the corpus**: it correctly
  diagnoses an over-fit calibration claim.
- For T7/T8: per-endpoint compatibility matrix (cliproxy /
  DeepSeek / Groq Qwen3 / Anthropic / OpenAI) showing that the
  methods themselves are sound but require non-reasoning
  endpoints with real per-token logprobs.

### 5. Code availability

- GitHub: <https://github.com/exergyleizhou-ux/PaperGuard>
- PyPI: `pip install paperguard==2.3.1` (or later)
- Docker: `ghcr.io/exergyleizhou-ux/paperguard:latest` (multi-arch)
- HuggingFace Space (interactive demo):
  <https://huggingface.co/spaces/exergyleizhou/paperguard-demo>
- All `scripts/recall_*` and `docs/recall_*` paths reproducible
  with one command each.

### 6. Data deposit

Proposed plan:
- Zenodo deposit at submission. Single archive containing:
  - All `scripts/recall_*.py` runner scripts + `recall_analyze_*.py`
    analysers.
  - All `scripts/*_results.json` raw run outputs (sanitised — the
    2.2.7 commit removed embedded local paths).
  - `docs/recall_*.md` writeups.
  - Frozen snapshot of the PaperGuard 2.3.x source tree at the
    submission tag.
- DOI for the Zenodo archive becomes the canonical citation for
  the corpus; the Scientific Data paper cites that DOI.

### 7. Limitations (honest)

- OA bias: the retracted-paper arms over-represent journals with
  strong OA programs (PLOS, Frontiers, Nature Communications
  open-access). Closed-access retractions are under-sampled.
- N is small for F1/F4/F6 even at v5 (132+48). The Bik-curated
  patch-splice corpus would be a much sharper instrument for F6
  calibration but is not redistributable.
- T7/T8 numbers depend critically on endpoint choice; we report
  the best-available free-tier endpoints (Groq Qwen3-32B, DeepSeek
  v4-flash) and document why production deployments need OpenAI
  `gpt-4o-mini`/`gpt-4o`.
- Industrial-layer benchmark is purely synthetic; no FDA Warning
  Letter / EPA enforcement corpus is publicly redistributable.
  This sets a **lower bound** on detector capability against real
  process logs, not an upper bound.
- We do not report a verdict-level F1 or accuracy. PaperGuard is
  **non-verdict by design**; LR+ at a documented threshold is the
  right summary statistic.

### 8. Acknowledgements

OpenAlex, Europe PMC, Unpaywall for the OA fetch pipeline.
PubMed Central for the underlying PDF index. Kobak et al. 2025
and Cabanac et al. 2024 for the seed lexical dictionary. James
Heathers, Nick Brown, Elisabeth Bik, John Carlisle, Michèle
Nuijten for the statistical foundations.

## Open items before submission

1. **JOSS DOI must be obtained first** — Scientific Data papers
   typically cite the tool DOI; submitting both in parallel
   complicates editorial review.
2. **ORCID** must be filled in (replace `0000-0000-0000-0000`).
3. **Zenodo archive** must be created and DOI minted; this is
   ~30 min of work post-JOSS-DOI.
4. **Hand-checked retraction labels** for v10 — currently we
   trust OpenAlex's `is_retracted` flag, which the data quality
   literature notes can have a ~5 % error rate. A hand-check on
   a random 20-paper subset would let us report a corrected
   ground-truth accuracy.
5. **Add a v6 image-recall study** with PubMed Central as the
   OA source (instead of mixed OpenAlex + Europe PMC) to
   eliminate the control-arm attrition bias documented in
   `docs/recall_image_v5.md`.

Items 1-3 are user actions. Items 4-5 are mine when prioritised.

## What this paper does NOT claim

- That PaperGuard is a fraud detector. It is not. The whole
  pipeline is non-verdict; the paper makes this explicit in the
  same paragraph as the headline numbers.
- That the corpus is large. N=200 per arm is small by NLP
  standards. The corpus is structured for **reproducibility and
  honest calibration**, not for training a detector from scratch.
- That the LLM-text detectors work on every endpoint. They do
  not. The per-endpoint compatibility matrix is part of the
  corpus contribution.

## Status

Draft outline only. Submission gated on:
- JOSS DOI in hand
- ORCID filled in
- Zenodo archive minted
- v6 image-recall study (PubMed Central control source) — optional
  but recommended

Estimated remaining work to submission: **1 week of writing + the
gating items above**.
