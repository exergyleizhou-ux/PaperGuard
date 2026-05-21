# docs/ — central documentation index

PaperGuard ships 30+ Markdown docs across the project. This file is
the index. Categories below; pick the one that matches what you're
trying to do.

---

## 📚 Start here

| Doc | Read when |
|---|---|
| [quickstart.md](quickstart.md) | First time using PaperGuard — 5-minute walk-through. Scans a fabricated CSV, then a real retracted PDF (Wansink 2015), then explains the report. |
| [paperguard_technical_report.md](paperguard_technical_report.md) | You want the **whole story** — 7-section technical report: methods, LLM-text family, N=85 empirical study, calibration of T6's role, reproducibility. |
| [../paper/paper.md](../paper/paper.md) | You want to **cite** PaperGuard — the JOSS submission paper (2-page summary + statement of need + design + empirical calibration). |
| [epistemic_position.md](epistemic_position.md) | You wonder why PaperGuard never says "fraud" — the load-bearing disclaimer architecture. |

---

## 🔬 Detector reference (per-detector deep-dives)

[detectors.md](detectors.md) — overview of all 34 detectors.
[detectors/](detectors/) — auto-generated per-detector pages
(one .md per A1–T6; F6 / T7 / T8 added separately).

Quick map:

| Family | Detectors | Page |
|---|---|---|
| Digit-distribution / arithmetic / bounds | A1-A7 | `detectors/A*.md` |
| Summary-statistic consistency | B1, B4-B8 | `detectors/B*.md` |
| Clinical-trial plausibility | C1 | `detectors/C1.md` |
| Variance / independence | D1, D2, E1 | `detectors/D*.md` |
| Image / metadata forensics | F1-F6, G1, G3, G4 | `detectors/F*.md` + `detectors/G*.md` |
| Paper-mill / text / LLM | M1, T1-T8 | `detectors/T*.md` (+ LLM-text dedicated guide below) |

---

## 🤖 LLM-text family (T6 + T7 + T8) — the new layer

| Doc | Read when |
|---|---|
| [llm_detection_v2.md](llm_detection_v2.md) | You want to know **when each LLM detector works and when it doesn't**, and how to combine them. Includes empirical calibration callout. |
| [t8_endpoint_limitation.md](t8_endpoint_limitation.md) | You wonder why T7/T8 emit "inconclusive" NOTE on weak proxies. Formal proof at N=20 that cliproxy gpt-5.4-mini gives LR+ = 0; diagnosis of both failure modes; per-endpoint compatibility matrix. |
| [dictionaries/llm_phrases_v1.json](dictionaries/llm_phrases_v1.json) | The official dictionary served via `paperguard refresh-ai-dict --official`. |

---

## 📊 Empirical studies (in chronological order)

Each study is a `recall_test_*.md` analysis + `scripts/recall_test_*.py`
driver + `scripts/recall_test_*_results.json` raw dataset.

| Study | What | Headline |
|---|---|---|
| [recall_test_v1.md](recall_test_v1.md) — [v2](recall_test_v2.md) — [v3](recall_test_v3.md) — [v4](recall_test_v4.md) — [v5](recall_test_v5.md) | 2.0.x recall iterations on full-pipeline PDF scans | v5 PMC-first fetcher lifts download success rate from 28 % → 60 % |
| [recall_test_v8.md](recall_test_v8.md) | 2.0.16 — N=50 text-only T6 study | T6 default LR+ ≈ 0 on post-publication retractions → pre-submission tool |
| [recall_test_v9.md](recall_test_v9.md) | 2.1.0 — N=30 retest + transparent T7/T8 columns | T7/T8 await GPT-4o; v9 is pre-wired for re-analysis |
| **[recall_test_v10.md](recall_test_v10.md)** | **2.1.12 — N=200 expansion** | **First true positive at 0.001 threshold: LR+ = ∞ (1 TP / 0 FP). PLOS ONE 2024 ML/medical-imaging paper-mill retraction.** |
| [recall_image_v1.md](recall_image_v1.md) | 2.1.2 — N=15+15 F1/F4 image | First F1/F4 empirical numbers |
| **[recall_image_v2.md](recall_image_v2.md)** | **2.1.8/2.1.9 — N=10+8 F1+F4+F6** | **F6 default tightened from z=4/cluster=4 to z=6/cluster=8 (FPR 75 % → 62.5 %)** |
| [crossval_statcheck.md](crossval_statcheck.md) | 2.1.3 — B4 vs scipy reference | recall = 100 %, decision-flip recall = 94.12 % |

---

## 🧠 Methodology references (for advanced users)

| Doc | What |
|---|---|
| [math_upgrades_v2.md](math_upgrades_v2.md) | Statistical depth upgrades — Stouffer combination, BH-FDR, integrity index, Hurst R/S, BIC Bayes factor, SPRITE enumeration |
| [fraud_case_studies.md](fraud_case_studies.md) | 9 real-world case studies (Stapel, Fujii, Hwang, Schön, Macchiarini, Wansink, Masliah, Geng-style, Bik 2016) mapped to detectors |

---

## 🌍 Operations

| Doc | Read when |
|---|---|
| [../README.md](../README.md) | Install + usage + overview |
| [../README.zh.md](../README.zh.md) | Chinese version of above |
| [../HANDOFF.md](../HANDOFF.md) | Successor-session continuity doc with credentials placeholders, ship workflow, 15 tripwires, open work list |
| [../CHANGELOG.md](../CHANGELOG.md) | Full release history 0.1 → current |
| [../ROADMAP.md](../ROADMAP.md) | What's planned next |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | How to add a detector, code style, testing |
| [../SECURITY.md](../SECURITY.md) | Security policy and responsible-disclosure contact |
| [../CITATION.cff](../CITATION.cff) | Cite this software |
| [../paper/JOSS_SUBMISSION.md](../paper/JOSS_SUBMISSION.md) | JOSS submission walkthrough |

---

## 🔗 External

| | URL |
|---|---|
| Source | https://github.com/exergyleizhou-ux/PaperGuard |
| PyPI | https://pypi.org/project/paperguard/ |
| Live demo | https://huggingface.co/spaces/exergyleizhou/paperguard-demo |

---

*Index last refreshed: 2026-05-21, PaperGuard 2.1.13*
