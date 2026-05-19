# PaperGuard

> Statistical anomaly screener for tabular research data.
> **Flags anomalies, not fraud.** Every finding includes possible innocent explanations.

![status](https://img.shields.io/badge/status-2.0.0-blue)
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

- ✅ Detects suspicious **terminal-digit distributions** (Mosimann 1995)
- ✅ Detects **first-digit / Benford** deviations on wide-dynamic-range columns
- ✅ Detects **inter-column arithmetic relations** (constant difference / ratio)
- ✅ Detects **decimal-fraction consistency** anomalies
- ✅ Runs the **GRIM** test on reported means (Brown & Heathers 2017)
- ✅ **Recomputes reported p-values** (statcheck-style: t, F, χ², r, z) and flags decision reversals
- ✅ Performs **file-metadata forensics** on .xlsx / .docx / .pdf
- ✅ Extracts tables from **.docx / .pdf**; classifies free-text numbers (p-values, percentages, mean±SD)
- ✅ Cross-checks **DOI metadata** via OpenAlex, **retractions** via CrossRef, and **public concerns** via PubPeer
- ✅ **Batch mode** to scan many files at once; **HTML / JSON** report exports

## What This Tool Does **NOT** Do

- ❌ **No plagiarism / text reuse detection**
- ❌ **No peer-review fraud signals**
- ❌ **No image-forensics beyond perceptual hash** (no internal-rotation
  detection, no splicing detection à la Bik 2016 manual review)
- ❌ **No ORI sanctions cross-check** (planned)
- ❌ Not a substitute for **journal editors, institutional integrity offices,
  or expert review**.

## Epistemic Position

The tool reports **statistical anomalies**, not misconduct. The vocabulary
"fraud", "fabrication", "misconduct" does not appear in any PaperGuard report.
Every finding carries:

- A `p_value` (where applicable) with BH–FDR correction across all findings
- A list of `innocent_explanations` — at least three plausible non-fraudulent causes
- An `academic_reference` to the underlying method

A flag is an invitation to look more carefully. It is not a conclusion.

## Installation

```bash
git clone <repo>
cd PaperGuard
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

pip install -e ".[dev]" types-openpyxl
cp .env.example .env   # edit to set your email (used for API polite pools)
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

## Roadmap

See [`ROADMAP.md`](ROADMAP.md). Highlights:

- **0.2.0** — A2 Benford detector, PubPeer integration, .docx inline-number extraction
- **0.3.0** — B4 statcheck (recompute p-values from manuscript text), full PDF table extraction
- **0.4.0** — C1 Carlisle test, F1 image-duplication (perceptual hash)
- **0.5.0** — Full Retraction Watch database integration, HTML report exports

Pull requests welcome. New detectors should follow the `A1` template — see
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[MIT](LICENSE).
