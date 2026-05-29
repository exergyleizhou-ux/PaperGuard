---
title: PaperGuard Demo
emoji: 🛡️
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 5.34.0
python_version: "3.11"
app_file: app.py
pinned: false
license: mit
short_description: 40-detector screener — flags anomalies, not fraud
---

# PaperGuard Demo

Public demo for [PaperGuard](https://github.com/exergyleizhou-ux/PaperGuard) —
a statistical anomaly screener for tabular research data.
**41 detectors** (academic 37 + industrial 4) covering terminal-digit,
Benford, GRIM/GRIMMER/SPRITE, statcheck, Carlisle baseline balance,
image duplication (pHash), EXIF temporal forensics, docx RSID forensics,
file metadata forensics, AI-text heuristics, and more.

**Paste a DOI or manuscript text** → get back:

- A Markdown summary of all findings, grouped by severity
- A WCAG 2.1 AA HTML report (same one the CLI exports)
- The full machine-readable JSON

## What this is **not**

A fraud detector. Read the disclaimer in the app and the
[v10 recall study](https://github.com/exergyleizhou-ux/PaperGuard/blob/main/docs/recall_test_v10.md)
and [T7/T8 endpoint scope](https://github.com/exergyleizhou-ux/PaperGuard/blob/main/docs/llm_detection_real_endpoints.md)
for the honest performance characteristics.

## Source code

- Library + CLI: https://github.com/exergyleizhou-ux/PaperGuard
- Install locally: `pip install paperguard`
- This demo's `app.py` is a thin Gradio wrapper around the
  PaperGuard detector pipeline.
- **New in 2.16.0**: T9 learned TF-IDF/LR LLM-text classifier (offline,
  opt-in via `--ml-check`), bringing the detector count to 41.
- **In 2.15.0**: OCR table extraction for scanned PDFs,
  Chinese scholar search via Semantic Scholar, batch author audit,
  author name disambiguation, EXIF temporal forensics, docx RSID
  forensics, decimal consistency detector.

## License

[MIT](https://github.com/exergyleizhou-ux/PaperGuard/blob/main/LICENSE).

## Why these pins?

- `python_version: "3.11"` — HF Space default container moved to
  Python 3.13, which removed the stdlib `audioop` module that pydub
  (a gradio dependency) needs. Pin 3.11 to keep stdlib audioop.
- `sdk_version: 5.34.0` (gradio 5.x) — gradio 4.44 imports `HfFolder`
  from `huggingface_hub`, which was removed in huggingface_hub 1.x.
  Gradio 5.x uses the new API. (2026-05-22 ship learning.)
