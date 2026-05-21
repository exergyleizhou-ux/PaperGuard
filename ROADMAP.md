# Roadmap

PaperGuard 0.1.0 ships with 5 detectors. This document is the public plan for
what comes next, and why.

## Why these priorities

Real-world misconduct findings, per the Office of Research Integrity case
summaries and Bik's 2016 image-screening study, are dominated by:

1. **Image manipulation / duplication** (~ 40% of validated findings)
2. **Statistical misreporting** (p-value miscalculation, selective reporting)
3. **Data fabrication** (the only category MVP currently addresses)

The roadmap below shifts coverage toward (1) and (2).

## 0.2.0 — Coverage of common signals ✅ shipped

| Item | Status | Notes |
|------|--------|-------|
| A2 Benford first-digit detector | ✅ shipped | With dynamic-range applicability gate |
| B4 statcheck detector | ✅ shipped | t / F / χ² / r / z; decision-reversal flagged as SUSPICIOUS |
| PubPeer client | ✅ shipped | Surfaces existing public concerns by DOI |
| .docx inline-number extraction | ✅ shipped | Classified as p_values / percentages / mean±SD / general |
| PDF text + table extraction | ✅ shipped | `pymupdf` + `pdfplumber` |
| HTML report export | ✅ shipped | Self-contained styled HTML |
| Batch mode | ✅ shipped | `paperguard batch --glob '...' --out-dir ...` |
| Dockerfile | ✅ shipped | `docker run paperguard scan -f /data/x.pdf` |

## 0.7.0 — Statistical-reporting + paper-mill signals ✅ shipped

| Item | Status | Notes |
|------|--------|-------|
| B5 TIVA (z-variance) | ✅ shipped | Schimmack 2014 |
| B6 GRIMMER (mean+SD+N) | ✅ shipped | Anaya 2016; Allard 2018 |
| T4 Tortured Phrases | ✅ shipped | Cabanac 2021; 50+ entries |
| B4 + Q-test | ✅ shipped | Meta-analysis heterogeneity |
| B4 whole-text one-tailed scan | ✅ shipped | statcheck.io heuristic |
| Auto OA PDF via Unpaywall | ✅ shipped | `--doi` without `-f` |
| `paperguard selfcheck` | ✅ shipped | Install-sanity command |
| `paperguard explain` | ✅ shipped | LLM-based finding translation |
| `paperguard diff` | ✅ shipped | Compare two scan reports |
| docs/detectors.md + epistemic_position.md | ✅ shipped | Public docs directory |
| examples/04_full_pipeline_demo.py | ✅ shipped | Every detector class |

## 0.3.0 — Image + RCT detectors ✅ shipped

| Item | Status | Notes |
|------|--------|-------|
| C1 Carlisle baseline-imbalance test | ✅ shipped | Welch t per variable + Stouffer combination |
| F1 image-duplication (perceptual hash) | ✅ shipped | docx/pdf image extraction + pHash cross-comparison |
| G1 image EXIF temporal forensics | ✅ shipped | Acquisition-date timeline + Photoshop signatures |
| G3 docx rsid forensics | ✅ shipped | Detects tool-generated docx via rsid homogeneity |
| Retraction Watch CSV loader | ✅ shipped | Local CSV lookup; user supplies the dataset |

## 0.4.0 — Plugin / i18n / Web UI ✅ shipped

| Item | Status | Notes |
|------|--------|-------|
| Plugin system (entry-point group `paperguard.detectors`) | ✅ shipped | Safe error handling around third-party loaders |
| i18n (en / zh-CN) | ✅ shipped | `--lang` flag + `PAPERGUARD_LANG` env var |
| FastAPI Web UI | ✅ shipped | `paperguard webui`; `pip install paperguard[webui]` |

## 0.5.0 — Toward "actually catching fraud" ✅ shipped

| Item | Status | Notes |
|------|--------|-------|
| F2 Bik-style internal image duplication | ✅ shipped | ORB+RANSAC affine; rotation tolerant |
| T1 text similarity vs corpus | ✅ shipped | 5-gram shingling + Jaccard |
| T2 clinical-trial outcome consistency | ✅ shipped | ClinicalTrials.gov v2 API |
| ORI sanctions local lookup | ✅ shipped | User-maintained CSV |
| Statcheck one-tailed handling | ✅ shipped | Recognizes annotation in context |
| es / ja / de language packs | ✅ shipped | Full coverage |
| WCAG 2.1 AA HTML report | ✅ shipped | Focus, ARIA, contrast, motion |
| LLM explainer (opt-in) | ✅ shipped | OpenAI / Anthropic / Ollama |

## Beyond 0.5.0 ✅ delivered across 2.0 / 2.1 cycle

| Item | Status | Where it shipped |
|---|---|---|
| Paper-mill detection (author/journal/citation graph) | ✅ shipped | 2.0 — M1 detector |
| Multi-tenant Web UI with auth | ✅ shipped | 2.0 — `paperguard.webui` |
| LLM-text detection (T6 lexical) | ✅ shipped | 2.0 — T6 detector |
| LLM-text detection (T7 perplexity) | ✅ shipped | 2.0.15 |
| LLM-text detection (T8 DetectGPT-curvature) | ✅ shipped | 2.0.16 |
| Dynamic T6 dictionary + `refresh-ai-dict` CLI | ✅ shipped | 2.0.15 / 2.0.16 |
| Empirical LR+ studies (v8/v9/image-v1) | ✅ shipped | 2.0.16 / 2.1.0 / 2.1.2 |
| Technical report (manuscript) | ✅ shipped | 2.1.1 |
| JOSS paper draft (`paper/paper.md` + `paper.bib`) | ✅ shipped | 2.1.2 |
| T6 abstract-only mode | ✅ shipped | 2.1.2 |
| HuggingFace Space live demo | ✅ deployed | 2.1.3 — [huggingface.co/spaces/exergyleizhou/paperguard-demo](https://huggingface.co/spaces/exergyleizhou/paperguard-demo) |
| B4 statcheck cross-validation (N=41 ground-truth) | ✅ shipped | 2.1.3 |

## 2.2 — Next horizon

| Item | Why |
|---|---|
| Real GPT-4o-class T7 / T8 LR+ measurement | Currently blocked on logprobs-capable endpoint access. Datasets ready (`recall_test_v9_results.json` has T7/T8 slots wired). |
| Bik splice / wash detection (per-channel histogram analysis at patch level) | Higher resolution image forensics than F3 currently offers. |
| statcheck-R direct comparison (Cohen's κ) | When R is available in CI; cross-validation against the original implementation rather than scipy reference only. |
| F1 / F4 expansion to N=100 | image-v1 used N=15+15; expanding to N=50+50 would give CI-tight LR+ estimates. |
| Pluggable cache backend (Redis) | For multi-tenant Web UI at scale. |
| Image-extraction for old `.doc` / `.docb` formats | Long-tail format coverage. |

## What This Tool Will Never Do

- Output the words "fraud", "造假", "misconduct" in any report
- Submit findings to journals, editors, or institutions on the user's behalf
- Auto-generate retraction recommendations
- Make probabilistic judgments about an author's intent

These boundaries are non-negotiable.

## Contributing

Pick an item, file an issue first to coordinate, then open a PR. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the detector template.
