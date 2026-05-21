# PaperGuard

> Statistical anomaly screener for tabular research data.
> **Flags anomalies, not fraud.** Every finding includes possible innocent explanations.

[![CI](https://github.com/exergyleizhou-ux/PaperGuard/actions/workflows/ci.yml/badge.svg)](https://github.com/exergyleizhou-ux/PaperGuard/actions/workflows/ci.yml)
![status](https://img.shields.io/badge/status-2.0.1-blue)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![tests](https://img.shields.io/badge/tests-223%20passing-brightgreen)
![coverage](https://img.shields.io/badge/coverage-74%25-green)
![detectors](https://img.shields.io/badge/detectors-30-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![i18n](https://img.shields.io/badge/i18n-en%20%7C%20zh%20%7C%20es%20%7C%20ja%20%7C%20de-blue)
![wcag](https://img.shields.io/badge/WCAG-2.1%20AA-success)

## Status

**Stable (2.0.0)**. 30 built-in detectors + plugin system + opt-in
multi-tenant Web UI. Covers numeric forensics, statistical recomputation
(statcheck one- and two-tailed; GRIM/GRIMMER/SPRITE/TIVA/P-curve), Carlisle
baseline imbalance with multi-arm RCT support, image duplication (both
pHash cross-image, Bik-style intra-image ORB matching, splice/copy-move
forensics, persistent cross-paper pHash store), EXIF/rsid metadata
forensics, text similarity vs corpus, tortured phrases (150+ paper-mill
fingerprints), AI-text heuristics, stylometry, clinical-trial outcome
consistency, paper-mill citation-graph signatures, plus DOI / PubPeer /
Retraction-Watch / ORI cross-checks. WCAG 2.1 AA HTML reports. Optional
LLM-assisted explanation. See the Roadmap for what's still on deck.

## What This Tool Does

- ✅ Detects suspicious **terminal-digit distributions** (Mosimann 1995) and **last-digit 0/5 preference** (Geng method, 2025)
- ✅ Detects **first-digit / Benford** deviations on wide-dynamic-range columns
- ✅ Detects **inter-column arithmetic relations** (constant difference / ratio)
- ✅ Detects **decimal-fraction consistency** and **implausible values** (sentinel detection)
- ✅ Runs **GRIM** (Brown & Heathers 2017), **GRIMMER** (Anaya 2016), **SPRITE** (Heathers 2018) plausibility checks
- ✅ **Recomputes reported p-values** (statcheck for t/F/χ²/r/z/Q, one- and two-tailed) and flags decision reversals
- ✅ **TIVA** (Schimmack 2014), **P-curve** (Simonsohn 2014), **residual smoothness** (Stapel case), **missing-pattern** (Carlisle) tests
- ✅ **Carlisle baseline-imbalance** test for RCTs, with multi-arm support and auto-extraction of trial-registration IDs (NCT, ISRCTN, ChiCTR, ACTRN, EudraCT, DRKS)
- ✅ Image forensics: **cross-image pHash** (F1), **intra-image ORB+RANSAC** (Bik-style, F2), **splice/copy-move** statistical forensics (F3), **persistent cross-paper pHash store** (F4), **EXIF clustering** (F5)
- ✅ EXIF **temporal forensics** (G1), docx **rsid forensics** (G3), file-metadata **publisher-whitelisted** audit (G4)
- ✅ Text: **similarity** vs corpus (T1), **clinical-trial outcome consistency** (T2), **data availability + ethics + COI** audit (T3), **150+ tortured-phrase paper-mill fingerprints** (T4), **stylometry** (T5), **AI-text heuristic** (T6)
- ✅ **Paper-mill citation-graph signatures** (M1) — OpenAlex subgraph + 4 structural fingerprints
- ✅ Cross-checks **DOI metadata** (OpenAlex), **retractions** (CrossRef + Retraction Watch CSV), **public concerns** (PubPeer), **ORI sanctions** (local CSV)
- ✅ **Plugin system** — third-party detectors via entry-point group `paperguard.detectors`
- ✅ **Multi-tenant Web UI** (opt-in) — invite-only accounts, persistent projects, per-report visibility (private/org/public)
- ✅ **Batch mode**, HTML/JSON exports, **5-language i18n**, **WCAG 2.1 AA** reports, optional **LLM-assisted explanation**

## What This Tool Does **NOT** Do

- ❌ **No peer-review fraud signals** (no public data source)
- ❌ **No ML-trained image classifier** for Western-blot duplication (requires labeled corpus + GPU)
- ❌ **No full Cabanac PDCN model** (the M1 detector is the local-subgraph version)
- ❌ Not a substitute for **journal editors, institutional integrity offices, or expert review**

A flag is an **invitation to look more carefully**. It is never a conclusion.

## Epistemic Position

The tool reports **statistical anomalies**, not misconduct. The vocabulary
"fraud", "fabrication", "misconduct" does not appear in any PaperGuard report.
Every finding carries:

- A `p_value` (where applicable) with BH–FDR correction across all findings
- A list of `innocent_explanations` — at least three plausible non-fraudulent causes
- An `academic_reference` to the underlying method

A flag is an invitation to look more carefully. It is not a conclusion.

## Sample output

Running PaperGuard on `tests/fixtures/fabricated_geng_style.csv` (a
deliberately constructed Geng-method fabrication pattern):

```text
╭────────────────────── PaperGuard Audit Report ──────────────────────╮
│ Overall: CRITICAL                                                   │
│ File:    fabricated_geng_style.csv                                  │
╰─────────────────────────────────────────────────────────────────────╯

Total findings: 7 | CRITICAL: 2, SUSPICIOUS: 3, CONCERN: 1
Independent evidence clusters: 2

╭── A1 — Terminal Digit Distribution Analysis ───────────── CRITICAL ──╮
│ Column 'Cell_Count' last-digit distribution is non-uniform           │
│   χ²(9) = 148.29, p = 0.00e+00, FDR-adjusted p = 0.00e+00            │
│   Cramér's V = 0.485                                                 │
│   Digits 0 and 5 account for 52.9% (expected 20%)                    │
│                                                                      │
│ Possible innocent explanations:                                      │
│   • Instrument quantisation (e.g. balance with 0.05 step display)    │
│   • Manual rounding to a specific precision at entry time            │
│   • Cultural digit preference in self-reported data                  │
│   • Derived values where the formula constrains the last digit       │
│                                                                      │
│ Reference: Mosimann et al. (1995). Data fabrication: Can people      │
│ generate random digits? Accountability in Research, 4(1), 31-55.     │
╰──────────────────────────────────────────────────────────────────────╯

╭── A3 — Inter-Column Arithmetic Relation ─────────────── SUSPICIOUS ──╮
│ Columns 'Control_OD' and 'Treatment_OD' differ by a constant         │
│ -0.3000 (precision σ = 2.19e-16)                                     │
│ … (4 innocent explanations and reference shown)                      │
╰──────────────────────────────────────────────────────────────────────╯

… 5 more findings …

DISCLAIMER: PaperGuard flags statistical anomalies, not fraud.
Every finding lists possible innocent explanations. Use the output as
a starting point for further inquiry, never as a conclusion.
```

Running it on `tests/fixtures/genuine_random.csv` (real i.i.d. data) is
boring on purpose:

```text
Overall: PASS — 0 findings across 30 detectors.
```

> **i18n note**. The sample above is curated for English readability.
> The current real CLI output uses an English framework (panels,
> headers, severity labels) plus per-detector body text in Chinese
> (the original implementation language). The 2.0.x line is honest
> about this partial state — `--lang en` switches headers and the
> disclaimer, not detector internals. Full per-detector i18n is on
> the v3.x roadmap.

> **Image detectors note**. F1 / F2 / F3 / F4 require **raster**
> images. Modern publisher PDFs (Springer, Nature, Lancet, etc.)
> store figures as vector graphics, which ``pymupdf`` cannot pull
> through ``page.get_images()``. As a result the image-forensics
> detectors fire mainly on **supplementary data files** and
> manuscript drafts (``.docx``), not on the typeset PDF. See
> [`docs/recall_test_v5.md`](docs/recall_test_v5.md) for the
> empirical confirmation.

## Installation

```bash
# from GitHub (current)
git clone https://github.com/exergyleizhou-ux/PaperGuard.git
cd PaperGuard
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

pip install -e ".[dev]"
cp .env.example .env   # edit to set your email (used for API polite pools)
```

Once a PyPI release lands you will also be able to just:

```bash
pip install paperguard          # CLI + library only
pip install paperguard[webui]   # adds FastAPI multi-tenant Web UI
```

## Usage

### Scan local data files

```bash
paperguard scan -f data.xlsx
paperguard scan -f manuscript.pdf --doi 10.1038/xxx --output-json report.json
paperguard scan -f manuscript.docx --output-html report.html
paperguard scan -f tests/fixtures/fabricated_geng_style.csv
```

### Batch mode

```bash
paperguard batch --glob 'papers/*.pdf' --out-dir reports/
# Produces reports/<file>.json + reports/<file>.html + reports/summary.json
```

### Web UI (anonymous, single-user)

```bash
pip install paperguard[webui]
paperguard webui --host 127.0.0.1 --port 8765
# Open http://127.0.0.1:8765/ — upload, pick language, get HTML report.
# JSON endpoint: POST /scan.json with multipart file=
# Introspection: GET /detectors
```

### Web UI (multi-tenant, opt-in)

PaperGuard 2.0 adds an **invite-only multi-tenant surface** at `/app/*`:
user accounts, persistent projects, stored scan reports with per-report
visibility (`private` / `org` / `public`), and an admin invite flow.

```bash
pip install paperguard[webui]

export PAPERGUARD_MULTITENANT=1
export PAPERGUARD_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
export PAPERGUARD_ADMIN_EMAIL="admin@your-org.example"
export PAPERGUARD_ADMIN_PASSWORD="$(python -c 'import secrets;print(secrets.token_urlsafe(24))')"

paperguard webui --host 127.0.0.1 --port 8765
# Sign in at http://127.0.0.1:8765/app/login
```

Multi-tenant mode activates **only** when `PAPERGUARD_DB_URL` or
`PAPERGUARD_MULTITENANT=1` is set; otherwise behaviour is identical to
1.x. Backed by SQLAlchemy async (SQLite by default, PostgreSQL/MySQL via
URL). Sessions live in HttpOnly signed cookies — no JWT, no OAuth, no
third-party identity provider. See
[`docs/webui_multitenant.md`](docs/webui_multitenant.md) for the full
architecture, env-var reference, invite flow, visibility semantics, and
production checklist.

### Language

Reports can be rendered in `en` or `zh-CN`:

```bash
paperguard scan -f data.csv --lang zh-CN
# Or via environment:
PAPERGUARD_LANG=zh-CN paperguard scan -f data.csv
```

### Writing a plugin detector

Third-party packages can register detectors via the `paperguard.detectors`
entry-point group:

```toml
# In your plugin's pyproject.toml:
[project.entry-points."paperguard.detectors"]
my_detector = "my_pkg.detectors:MyDetector"
```

`MyDetector` must be a `BaseDetector` subclass with `id` set. It will be
auto-loaded by `DetectorRegistry().register_default()`. See
[`examples/03_custom_detector.py`](examples/03_custom_detector.py) for the
detector template.

On Windows, ensure UTF-8 stdout when you have CJK content:

```powershell
$env:PYTHONIOENCODING="utf-8"
```

### Search papers by author

```bash
paperguard search --author "Watson J"
paperguard search --author "George Church" --year-from 2015 --limit 30
```

## Detection Methods

| ID | Name | Type | Academic Basis |
|----|------|------|----------------|
| A1 | Terminal Digit Distribution | numeric forensics | Mosimann et al. (1995) |
| A2 | Benford First-Digit | numeric forensics | Benford (1938); Nigrini (2012) |
| A3 | Inter-Column Arithmetic Relation | numeric forensics | Independent-measurement noise principle |
| A5 | Decimal Fraction Consistency | numeric forensics | Discreteness of fabricated continuous data |
| A6 | Implausible Value Check | data quality | Anaya, van der Zee, Brown (2017); Wansink case |
| A7 | Last-Digit 0/5 Preference | numeric forensics | Geng Hongwei (2025); Mosimann (1995) |
| B1 | GRIM Test | summary-statistic consistency | Brown & Heathers (2017) |
| B4 | Statcheck (p-value recomputation) | statistical reporting | Nuijten et al. (2016) |
| B5 | TIVA (z-variance) | statistical reporting | Schimmack (2014) |
| B6 | GRIMMER (mean+SD+N) | statistical reporting | Anaya (2016); Allard (2018) |
| B7 | P-Curve (publication bias) | statistical reporting | Simonsohn, Nelson & Simmons (2014) |
| B8 | SPRITE plausibility | summary-statistic consistency | Heathers, Anaya, van der Zee & Brown (2018) |
| C1 | Carlisle Baseline-Balance | RCT integrity | Carlisle (2017) |
| D1 | Residual Smoothness | variance structure | Stapel report (Levelt et al. 2012) |
| D2 | Missing-Data Pattern | variance structure | Carlisle (2017); Buyse et al. (1999) |
| F1 | Image Duplication (pHash) | image forensics | Bik et al. (2016); standard perceptual hashing |
| F2 | Internal Image Duplication (ORB+RANSAC) | image forensics | Bik et al. (2016); Brown & Lowe (2003) |
| F3 | Splice / Copy-Move (statistical patches) | image forensics | Cozzolino & Verdoliva (2015) Splicebuster |
| F4 | Cross-Paper Image Duplication | image forensics | Masliah (NIH 2024); Hwang (2005) |
| F5 | EXIF Cross-Image Clustering | image forensics | Standard digital forensics; ORI image audit |
| G1 | Image EXIF Temporal Forensics | digital forensics | Standard EXIF forensics; ORI image audit |
| G3 | Docx rsid Forensics | digital forensics | OOXML ECMA-376 §17.15.1.55 |
| G4 | File Metadata Forensics | digital forensics | NIST SP 800-101; ORI toolkits |
| M1 | Paper-Mill Citation Graph | network forensics | Cabanac et al. (2025) JDIS PDCN |
| T1 | Text Similarity (n-gram shingling) | text forensics | Brin et al. (1995); Schleimer et al. (2003) |
| T2 | Clinical-Trial Outcome Consistency | trial integrity | Goldacre et al. (2019) |
| T3 | Data Availability + Ethics Audit | compliance | ICMJE; Gabelica et al. (2022); FAIR principles |
| T4 | Tortured Phrases (paper-mill signature) | text forensics | Cabanac et al. (2021); PPS |
| T5 | Stylometry (Stapel linguistic fingerprint) | text forensics | Markowitz & Hancock (2014) PLOS ONE |
| T6 | AI-Generated Text Heuristic | text forensics | Cabanac et al. (2024); Kobak et al. (2025) |

## Output Severity

| Level | Meaning |
|-------|---------|
| PASS | No anomalies |
| NOTE | Minor curiosity, archived for reference |
| CONCERN | Worth checking (single detector p < 0.01) |
| SUSPICIOUS | Multiple detectors flag across independent assumption clusters |
| CRITICAL | Contains a CRITICAL finding OR ≥ 3 cross-cluster CONCERN+ |

Escalation logic in [`src/paperguard/evidence/combiner.py`](src/paperguard/evidence/combiner.py).

## Tests & Development

```bash
pytest -m "not network" -v     # skip network-dependent tests (default for CI)
pytest -v                      # run everything
ruff check src/ tests/
mypy src/
```

## Project Layout

```
src/paperguard/
├── cli.py                  # click CLI entrypoints (scan / search)
├── config.py               # pydantic-settings (env-driven)
├── core/                   # Severity, Finding, AuditReport, BaseDetector, Registry, AuditLog
├── detectors/              # A1, A3, A5, B1, G4
├── evidence/combiner.py    # BH-FDR + severity escalation
├── extractor/              # Excel/CSV/PDF/docx-tables/metadata
├── fetcher/                # OpenAlex / CrossRef / Unpaywall
├── reporter/               # Rich terminal report + JSON export
└── utils/                  # SHA-256, float helpers
tests/
├── fixtures/               # Two paired CSVs (fabricated vs genuine) + generators
└── test_*/                 # Detector, combiner, extractor, e2e, fetcher tests
```

## Documentation

| Document | What it covers |
|---|---|
| [docs/paperguard_technical_report.md](docs/paperguard_technical_report.md) | **Technical report** — methods, the LLM-text family (T6 / T7 / T8), N=85 empirical study, calibration of T6's role |
| [docs/quickstart.md](docs/quickstart.md) | **5-minute walk-through** — install, scan a fabricated CSV, scan a real retracted PDF (Wansink 2015), read the report |
| [docs/llm_detection_v2.md](docs/llm_detection_v2.md) | **LLM-text detection guide** — T6 lexical + T7 perplexity + T8 DetectGPT, with the calibrated empirical position |
| [docs/recall_test_v8.md](docs/recall_test_v8.md) | **2.0.16 — N=50 LR+ study (T6 only)** — first focused LR+ measurement against post-publication retraction data |
| [docs/recall_test_v9.md](docs/recall_test_v9.md) | **2.1.0 — N=30 retest + transparent T7/T8 dataset** — extends v8 with T7/T8 columns annotated for cliproxy endpoint limitations |
| [docs/recall_image_v1.md](docs/recall_image_v1.md) | **2.1.2 — image-layer LR+ study** — first F1/F4 empirical numbers on a curated retracted-image-reuse corpus |
| [docs/crossval_statcheck.md](docs/crossval_statcheck.md) | **2.1.3 — B4 statcheck cross-validation** — N=41 ground-truth corpus, B4 recall 100% / decision-flip recall 94% |
| [paper/paper.md](paper/paper.md) | **JOSS-formatted paper draft** with bibliography (`paper/paper.bib`) — ready for submission to the Journal of Open Source Software |
| [docs/recall_test_v2.md](docs/recall_test_v2.md) | **N=100+100 recall/precision study** — quantifies that PDF-only scanning is *not* a reliable retraction detector; explains why and what to do instead |
| [docs/recall_test_v3.md](docs/recall_test_v3.md) | **2.0.4 follow-up** — single-rule recalibration takes LR+ from 0.77 (worse than coin flip) to ∞ (zero false positives) at the cost of dropping recall from a fake 68% to an honest 13% |
| [docs/recall_test_v4.md](docs/recall_test_v4.md) | **2.0.5 follow-up** — T5 stylometry tightening removes near-universal NOTE noise from reports while preserving recall/FP at the v3 level (T5 was only ever NOTE-level so it didn't drive overall severity anyway) |
| [docs/recall_test_v5.md](docs/recall_test_v5.md) | **2.0.6 follow-up (in progress)** — PMC-first OA fetcher lifts download success rate from ~28% (v2) to ~60% in the partial sample, by routing through Europe PMC before Unpaywall and OpenAlex |
| [README.md](README.md) | This file — overview, usage, install |
| [README.zh.md](README.zh.md) | 中文版 |
| [CHANGELOG.md](CHANGELOG.md) | Full release history 0.1 → 2.1.3 |
| **[HuggingFace Space demo](https://huggingface.co/spaces/exergyleizhou/paperguard-demo)** | **Live browser demo** — paste DOI / upload PDF / paste text, get a full PaperGuard report |
| [docs/detectors/](docs/detectors/) | Auto-generated per-detector deep-dive (30 pages + index) |
| [docs/fraud_case_studies.md](docs/fraud_case_studies.md) | 9 real-world cases (Stapel, Fujii, Hwang, Schön, Macchiarini, Wansink, Masliah, Geng-style, Bik 2016) mapped to detectors |
| [docs/webui_multitenant.md](docs/webui_multitenant.md) | Multi-tenant Web UI architecture, env vars, invite flow, production checklist |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to add a detector, code style, testing |
| [SECURITY.md](SECURITY.md) | Security policy and responsible-disclosure contact |
| [CITATION.cff](CITATION.cff) | Cite this software |
| [ROADMAP.md](ROADMAP.md) | What's planned next |

## Roadmap

Shipped through 2.0.1. Still open (see [`ROADMAP.md`](ROADMAP.md) for detail):

- Full Cabanac 2025 PDCN model on a 5M-node citation graph (M1 is the local-subgraph variant)
- ML-trained Western-blot specific image classifier (requires labelled corpus + GPU)
- Reviewer-fraud signal extraction (no public data source yet)
- Web UI 2.x: password reset, project-level shared membership, audit-log UI

Pull requests welcome. New detectors should follow the `A1` template — see
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## Citation

If PaperGuard helped your work, please cite the software entry in
[`CITATION.cff`](CITATION.cff) (GitHub renders a "Cite this repository"
button on the right sidebar).

## License

[MIT](LICENSE).
