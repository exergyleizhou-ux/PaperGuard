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

## Beyond 0.5.0

- Paper-mill detection (author/journal/citation graph + community detection)
- Bik splice / wash detection (per-channel histogram analysis at patch level)
- Multi-tenant Web UI with auth and shared scan history
- Pluggable cache backend (Redis)
- Image-extraction for old `.doc` / `.docb` formats

## What This Tool Will Never Do

- Output the words "fraud", "造假", "misconduct" in any report
- Submit findings to journals, editors, or institutions on the user's behalf
- Auto-generate retraction recommendations
- Make probabilistic judgments about an author's intent

These boundaries are non-negotiable.

## Contributing

Pick an item, file an issue first to coordinate, then open a PR. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the detector template.
