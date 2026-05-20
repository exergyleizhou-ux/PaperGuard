# Changelog

All notable changes to PaperGuard are documented in this file. Format follows
[Keep a Changelog](https://keepachangelog.com/) and the project adheres to
[Semantic Versioning](https://semver.org/).

## [2.0.10] — 2026-05-19 — PubPeer commentary as a finding + F4 auto-corpus

Two enhancements that move PaperGuard beyond "PDF-content-only" into
the **external-signal layer**. v7 recall study confirmed PDF-internal
features cannot distinguish retracted from non-retracted; external
signals (PubPeer, cross-paper image reuse) are where the real
discriminative power lives.

### Added — PubPeer commentary as a Finding
- When `paperguard scan --doi X` already calls PubPeer (since 0.2.0).
  2.0.10 now **emits a Finding** so PubPeer commentary counts toward
  `overall_severity`.
- Tier mapping informed by post-publication-review patterns:
  - 1-2 comments → `CONCERN` (routine discussion)
  - 3-9 comments → `SUSPICIOUS` (sustained concern thread)
  - 10+ comments → `CRITICAL` (typical Bik-flagged pre-retraction)
- Lists 4 innocent explanations including "anonymous commentary may
  be from competitors with non-integrity motives" and "high comment
  count can reflect topical importance".

### Added — F4 auto-corpus
- `paperguard scan` on a PDF/docx now automatically feeds extracted
  images into a persistent SQLite pHash corpus at
  `~/.paperguard/image_corpus.db`, and at the same time queries the
  corpus for cross-paper matches.
- No flag required. Corpus is **per-user**, never shared.
- The signal accumulates over time: scan paper A then paper B; if
  paper B reuses a figure from paper A (different DOIs), F4 fires
  SUSPICIOUS or CRITICAL depending on hamming distance.
- Previously F4 only ran when callers explicitly constructed the
  ``CrossPaperImageInput``. The auto-corpus path now exposes the
  Masliah-style cross-publication image-duplication signal that the
  v2-v7 studies could not catch (because each scan was isolated).

### Quality
- 267 tests still passing; mypy --strict and ruff clean.
- No breaking changes; auto-corpus is opt-in by virtue of running
  scan multiple times (single-scan users see no F4 findings).

## [2.0.9] — 2026-05-19 — Raster cap default 40 → 5 pages

### Changed
- `extract_pdf_images(raster_max_pages=5)` default down from 40. The
  v7 background recall run timed out at 300 s/paper on a single
  ~40-page review article because rendering 40 pages at 150 DPI is
  slow. Article figures live almost entirely in the first 5 pages
  (abstract / intro / results), so capping there gives ≥ 90% of the
  signal at ~1/8 the cost. Override per-call if needed.

### Quality
- 267 tests still passing; mypy --strict and ruff clean.

## [2.0.8] — 2026-05-19 — Three precision-improving changes

This is the biggest single PaperGuard release for detection accuracy
since 1.0. Three things land together:

### Added — `--paper-year` plumbed through to T3 (Step 4)
- `paperguard scan --paper-year YYYY` now flows through to the T3
  detector's year-stratified severity logic (added in 2.0.7).
- When `--doi` is given, `paper_year` is auto-filled from OpenAlex
  metadata.
- `_scan_single_file(file_path, seed, paper_year=None)` exposes the
  same plumbing for headless callers (Web UI, batch scripts).

### Added — Page-as-raster fallback for vector-figure PDFs (Step 2)
- `extract_pdf_images` now renders each page via `pymupdf.get_pixmap`
  when fewer than 2 embedded raster bitmaps are found. Modern
  Springer / Nature / Lancet / Cell-Press PDFs store figures as
  vector graphics that `page.get_images()` cannot see; this
  fallback makes F1/F2/F3 actually fire on those PDFs for the first
  time. Knobs: `raster_dpi=150`, `raster_threshold=2`,
  `raster_max_pages=40`.
- 5 new regression tests covering vector-only PDFs, raster cap, dpi
  scaling, and explicit disable.

### Added — Live ClinicalTrials.gov NCT verification (Step 1)
- During scan, every extracted NCT id is verified against the
  ClinicalTrials.gov v2 API.
- 404 → SUSPICIOUS T2 finding: "Claimed trial registration {NCT}
  does not exist in registry" — fabricated trial IDs in published
  papers are a documented fraud pattern (Goldacre et al. 2019 COMPare).
- 3 new tests covering the 200 / 404 / non-NCT-format paths (mocked
  API).

### Quality
- 267 tests passing (was 259; +8 new); mypy --strict and ruff clean.
- All three steps are part of the **v3.x roadmap** I documented in
  the v5 study; this release is the first cut where PDF-only scans
  have a meaningfully strengthened signal layer.

## [2.0.7] — 2026-05-19 — T3 year-stratified severity

### Changed
- **T3 `paper_year` input** + year-aware severity tiers:
  - **Data Availability statement missing**: silent on papers before
    2018 (ICMJE only made the statement mandatory that year);
    CONCERN at 2018+.
  - **Clinical-trial paper without an NCT/ISRCTN/ChiCTR/EudraCT
    registration ID**: silent before 2005 (NCT registry did not
    exist), CONCERN 2005-2009 (early ICMJE adoption), SUSPICIOUS
    2010+ (strict enforcement).
- This is driven by the v5 recall study (N=200): T3 was firing at
  89% on the matched-control arm, almost entirely on pre-policy
  papers that legitimately predate the mandates. Year-stratifying
  the rule should bring T3's false-positive rate down dramatically
  on older biomedical samples.
- Backward-compatible: when `paper_year` is None (the default for
  text-only inputs), the detector applies the strictest tier — same
  behaviour as 2.0.6.

### Added
- 11 new regression tests (`tests/test_t3_year_stratification.py`)
  pinning the three-tier policy and pre-policy silence behaviour.

### Quality
- 259 tests passing; mypy --strict and ruff clean.

## [2.0.6] — 2026-05-19 — CLI refactor + diagnostic notes

### Changed
- **CLI refactored**: the detector flow is now a single function
  `_run_detectors_on_file` instead of being duplicated across the
  `scan` command and the `_scan_single_file` helper (used by the
  multi-tenant Web UI). The two had drifted over four release
  cycles, with 2.0.3 having to patch the same PDF-crash bug in
  both places. Single source of truth means future bug fixes only
  have to land once. No behavioural change: 248 tests still pass.
- **T5 detail text updated** to reflect the 2.0.5 tightened
  thresholds. The old text described single-dimension Stapel
  signatures; the new text correctly says "since 2.0.5 this
  detector requires at least two dimensions to deviate by ≥70-100%".
- **T5 module docstring** documents the per-subfield recalibration
  roadmap item.

### Diagnostics
- README now honestly documents two known limitations from the v2
  recall study:
  - **i18n**: CLI panels are English, detector body text is Chinese.
    `--lang en` switches the framework only. Full per-detector i18n
    is roadmap.
  - **Vector graphics**: F1 / F2 / F3 / F4 require raster images;
    modern publisher PDFs store figures as vector. This is why the
    image detectors did not fire in the v2/v3/v4 study and why
    PaperGuard's image forensics work better on supplementary data
    files and `.docx` drafts.

### Quality
- 248 tests passing; mypy --strict and ruff clean.

## [2.0.5] — 2026-05-19 — Tighten T5 stylometry + PMC-first OA fetcher

### Added
- **`paperguard.fetcher.oa_pdf`** — a PMC-first OA PDF fetcher.
  Tries Europe PMC / PubMed Central before Unpaywall before
  OpenAlex. Validates the `%PDF-` magic header on every download
  so HTML landing pages no longer slip through. 13 unit tests
  covering the fallback chain, header validation, and network
  failure modes.

### Changed
- **T5 stylometry thresholds tightened.** v2 found T5 fired on 98%
  of retracted and 81% of control papers — almost-universal noise.
  Single-dimension threshold raised to ≥100% relative deviation
  (methodology / certainty) or ≥70% (adjective), AND at least two
  dimensions must violate before any finding is emitted.
- The detector now stays silent on normal biomedical prose while
  still triggering on synthetic Stapel-style text (high
  methodology + high certainty + low adjective density). 4 new
  regression tests cover both directions.

### Quality
- 248 tests passing (was 231; +17 new); mypy --strict and ruff clean.
- Total: 30 detectors, 5 PyPI releases (2.0.0 → 2.0.5).

## [2.0.4] — 2026-05-19 — Recalibrate T3 ethics-statement severity

### Changed
- **T3 case-4 (no ethics statement on human / animal subjects research)
  severity SUSPICIOUS → CONCERN**. The v2 recall study
  (`docs/recall_test_v2.md`) showed this finding triggered at almost
  identical rates on retracted and matched non-retracted papers
  (~60-65% in both arms). The root cause is PDF extraction missing
  ethics statements buried in supplementary information or methods
  end-matter — not actual fraud signal. Real fraud papers usually
  include (often fabricated) ethics statements. The detector still
  flags the issue but no longer auto-escalates the overall report
  severity into "suspicious" territory on this signal alone.
- Findings without ethics statements now contribute to `CONCERN`
  along with the other T3 cases (missing data-availability statement,
  vague "available on request" without an accession). Clinical-trial-
  registration omission (T3 case-3) is unchanged — that one remains
  SUSPICIOUS because ICMJE has required pre-registration since 2005
  and the signal is much more specific.

### Quality
- 231 tests still passing; mypy --strict and ruff clean.
- The recalibration is documented and justified by N=100+100 data
  rather than a guess.

## [2.0.3] — 2026-05-19 — Scan errors on malformed PDFs no longer crash CLI

### Fixed
- `paperguard scan` no longer exits non-zero when ``pdfplumber`` or
  ``pymupdf`` raise on a malformed input (for example, an HTML
  landing page mis-served as `.pdf`, a truncated download, or a
  damaged xref table). Both `extract_pdf_tables` and `extract_pdf_text`
  are now called through `_safe_pdf_tables` / `_safe_pdf_text`
  wrappers in `cli.py`; an extraction failure is logged to the audit
  log + printed in yellow and processing continues with whatever
  detectors can still run on the remaining inputs.
- This was the most actionable finding from the v1 recall pilot,
  where 3 of 5 publisher OA "PDFs" were actually HTML landing pages
  that derailed the whole batch with `exit=1`.

### Added
- 8 new tests in `tests/test_cli_safe_extractors.py` covering HTML
  served as `.pdf`, empty files, truncated PDFs, and missing files.
- `scripts/recall_test_v2.py` — v2 of the recall study with
  Unpaywall-first PDF URL resolution, `%PDF-` header validation,
  per-host rate limiting, and resumable streaming output. Designed
  to run N = 100 + 100 unattended.

## [2.0.2] — 2026-05-19 — CLI `--version` reads from `__version__`

### Fixed
- `paperguard --version` was hard-coded to `"2.0.0-dev1"` in
  `cli.py`. It now reads from `paperguard.__version__` so a single
  bump in `__init__.py` keeps everything consistent. Found
  immediately after the 2.0.1 PyPI upload — installing from PyPI
  showed the right metadata but `paperguard --version` lied.

## [2.0.1] — 2026-05-19 — macOS arm64 CI fix

### Fixed
- **`greenlet>=3.0`** added explicitly to the `[webui]` and `[dev]`
  extras. SQLAlchemy 2.x needs `greenlet` for its async-to-sync
  bridge; it is normally a transitive dep on Linux and Windows, but
  the macOS arm64 wheel marks it optional in some versions, which
  caused all 20 multi-tenant tests to error on the macos-latest
  CI matrix. Local `pip install -e .[dev]` on macOS now pulls it in.
- No source-code changes; only the dependency declaration moved.

## [2.0.0] — 2026-05-19 — Paper-mill graph + Carlisle automation + multi-tenant Web UI

Second stable major. Folds in the two dev-1 shipped items (M1 paper-mill
citation-graph signatures; deeper Carlisle automation including multi-arm
RCT support and PDF→C1 trial-ID auto-extraction) and adds an opt-in
multi-tenant Web UI surface. 223 tests passing, mypy strict clean,
30 built-in detectors plus plugin entry-point.

### Added (multi-tenant Web UI)
- **`/app/*` invite-only multi-tenant surface** mounted on top of the
  existing anonymous `/scan` endpoints. Activated by setting
  `PAPERGUARD_DB_URL` or `PAPERGUARD_MULTITENANT=1`; otherwise no behaviour
  changes from 1.x.
- **User + InviteCode + Project + ScanReport ORM** (SQLAlchemy 2.0 async).
  SQLite by default; any async engine (PostgreSQL via `asyncpg`, MySQL via
  `aiomysql`) via `PAPERGUARD_DB_URL`.
- **Per-report visibility**: `private` / `org` / `public`. Public reports
  are listed at `/app/shared` and readable anonymously.
- **Admin invite flow**: admins mint single-use codes at
  `/app/admin/invites`; invitees redeem at `/app/redeem/{code}` with a
  password ≥ 10 characters.
- **Bootstrap admin from env**: `PAPERGUARD_ADMIN_EMAIL` +
  `PAPERGUARD_ADMIN_PASSWORD` create the first admin idempotently on
  startup.
- **Sessions** in HttpOnly, SameSite=Lax cookies signed with
  `itsdangerous` (key from `PAPERGUARD_SECRET_KEY`); 14-day TTL.
- **Passwords** hashed with `bcrypt` directly (no passlib; bcrypt 4.x/5.x
  compatible).
- New optional dependencies in `paperguard[webui]`: `sqlalchemy>=2.0`,
  `aiosqlite>=0.20`, `bcrypt>=4.0`, `itsdangerous>=2.2`.
- **24 new tests** covering bootstrap, auth, invite redemption (single-use,
  weak-password rejection, email binding), project isolation, visibility
  enforcement (private / org / public), legacy `/scan` survival,
  multi-tenant off-by-default, and session signing.
- New documentation: `docs/webui_multitenant.md` with architecture,
  env-var reference, invite flow, visibility semantics, and production
  checklist.

### Added (Carlisle automation deepening)
- **C1 multi-arm RCT support**: `BaselineVariable.arms` accepts any number
  of `(n, mean, sd)` arms. Pairwise Welch t between every arm pair;
  per-variable median pairwise p folded into the Stouffer combination.
  Backward-compatible (legacy `n1/mean1/sd1 + n2/mean2/sd2` still works).
- **Robust baseline-table parser**: handles 3+ arm tables, header-embedded
  N (`Treatment (n=42)`), categorical `n (%)` rows recorded separately,
  multiple table caption formats (`baseline`, `demographics`, `study
  population`, `participant characteristics`, `table 1/i`).
- **Auto-extract trial registration IDs** from PDF/docx text
  (`extractor/trial_ids.py`): supports NCT, ISRCTN, ChiCTR, ACTRN,
  EudraCT, DRKS. CLI surfaces found IDs in scan output.
- 14 new tests for multi-arm Welch, trial-ID extraction, arm-column
  identification, mean±SD / paren / categorical row parsing.

### Added (M1 paper-mill citation graph)
- **M1 — Paper-Mill Citation Graph Signatures** detector
  (`detectors/m1_paper_mill_graph.py`).
- **Citation-graph fetcher** (`fetcher/citation_graph.py`).
- **`--check-paper-mill` flag** on `paperguard scan`.
- 5 unit tests against synthetic citation subgraphs.
- New core dependency: `networkx>=3.0`.

### Planned for 2.x (still open)
- Full Cabanac 2025 PDCN model on a 5M-node citation graph (the M1
  detector is the local-subgraph version of the same signatures)
- Reviewer-fraud signal extraction (no public data source yet)
- ML-trained Western-blot specific image model (requires labeled corpus)
- Multi-tenant Web UI with shared scan history

## [1.0.0] — 2026-05-18 — First stable release

### Added (since 0.9.0)
- **PDF→C1 auto baseline extraction** (`extractor/baseline_tables.py`)
  — CLI now automatically scans PDFs for baseline characteristics tables
  and feeds them to C1 Carlisle.
- **Expanded T4 dictionary** — tortured phrases went from ~50 to **150+**
  curated entries covering CS/ML, statistics, optimization, biomedical,
  energy, common terms, and GPT-disguise phrases.
- **`paperguard server`** — production-mode daemon with X-API-Token auth,
  multi-worker, `/health` endpoint.
- **`docs/detectors/`** — 29 deep-dive markdown pages auto-generated from
  source (one per detector + index README).
- **`scripts/generate_detector_docs.py`** — regenerate detector docs from
  source metadata.
- **GitHub Actions enhancements**: codecov upload, dependabot config,
  release-please workflow.
- **Coverage badge** (73% on tracked source files).
- **`README.zh.md`** finalized.

### Changed
- Status promoted from Alpha to Beta in PyPI classifiers (the project
  is now stable enough for first-real-users).

### Decided NOT to do in 1.0
- **Extras split** (`paperguard[image]` / `paperguard[text]` / etc.) —
  current dependencies are all small enough that the additional
  packaging complexity doesn't pay for itself. May revisit in 2.0
  if dependency tree grows.

### Post-1.0 polish

- **Fetcher disk-cache** (`src/paperguard/fetcher/cache.py`) — OpenAlex
  / CrossRef / Unpaywall responses cached to `diskcache` for 7 days,
  reducing API load on repeat scans.
- **`paperguard list-detectors`** — table / json / ids output, optional
  `--cluster` filter.
- **`paperguard fetch-rw`** — downloads the Retraction Watch CSV.
- **`paperguard fetch-ori`** — writes a starter ORI sanctions template.
- **`docker-compose.yml`** — production reference deployment.
- **`MANIFEST.in`** — ensures docs and fixtures ship in the sdist.
- **`examples/plugin_example/`** — fully installable plugin template
  with entry-point wiring.
- **`paperguard.reporter.schema`** — emits a JSON Schema describing the
  audit-report shape.
- **Coverage** 73% → **74%** with 16 new boost tests (180 total).

## [0.9.0] — 2026-05-18 — Polish + 4 specialized detectors

### Added detectors (4 new, 25 → 29)
- **A7 Last-Digit 0/5 Preference (Geng method)** — Binomial test on
  P(末位 ∈ {0,5}) ≠ 0.2; specialized refinement of A1 χ², bidirectional
  (catches both excess and depression). Direct internalization of the
  2025 Geng Hongwei method.
- **B8 SPRITE plausibility** — Heathers et al. (2018) iterative
  reconstruction: given (mean, SD, N, scale_min, scale_max), tries to
  construct any valid integer sample; failure → SUSPICIOUS.
- **F5 EXIF Cross-Image Clustering** — multi-image consistency: span
  > 5 years, > 2 distinct camera models, or identical second-precision
  timestamps across ≥ 3 images.
- **T6 AI-Generated Text Heuristic** — two-layer detection:
  uncleaned LLM response leakage (CRITICAL) + AI-overused phrase
  density (Kobak 2025 word patterns).

### Added fetchers
- **`fetcher/openalex.py`** — new `get_author_retraction_rate(author_id)`
  using OpenAlex `is_retracted` flag (Retraction Watch–synced upstream).
- **`fetcher/pubmed.py`** — Biopython `Entrez` wrapper for PMID lookup
  and DOI→PMID resolution. Saves us re-implementing E-utils.

### Added documentation
- **`README.zh.md`** — 中文 README full translation.
- `docs/fraud_case_studies.md` (from 0.8.0) — cross-referenced.

### Tests
- **`tests/test_golden.py`** — anti-regression gate: golden findings
  count on the paired fixtures.
- 12 new tests for A7/B8/F5/T6.
- 164 total passing.

### Reused open-source components
- **biopython** for NCBI Entrez (vs hand-rolled E-utils HTTP).
- imagehash, pdfplumber, pymupdf, opencv-python-headless, PIL, piexif:
  all already in use. No new heavyweight dependencies in 0.9.0.

## [0.8.0] — 2026-05-18 — Real-world fraud case internalization

### Added (6 new detectors derived from real-case study)
- **A6 Implausible Values** — column-name-aware range checks + sentinel
  values (999 / -999) detection. Internalizes Wansink's "700 pizza slices".
- **B7 P-Curve** (Simonsohn 2014) — p-curve shape analysis; left-skew or
  near-α pile-up signals p-hacking. Internalizes Wansink's email-leaked
  data-mining patterns.
- **D1 Residual Smoothness** — block-variance stability check;
  internalizes the Stapel-case signature of "too clean" data.
- **D2 Missing-Data Pattern** — flags 0-missing datasets with low
  column-σ variation; internalizes Carlisle's RCT-fraud observation.
- **F4 Cross-Paper Image Duplication** — persistent SQLite pHash store
  for cross-paper image reuse. Internalizes Masliah (2024) and Hwang
  (2005) findings.
- **T5 Stylometry** — Markowitz-Hancock 2014 PLOS ONE linguistic
  fingerprint (methodology / certainty / adjective density ratios).
  Internalizes the Stapel-text findings.

### Documentation
- **`docs/fraud_case_studies.md`** — Stapel, Fujii, Hwang, Schön,
  Macchiarini, Wansink, Masliah, Geng-targets, Bik 2016: each case maps
  to specific detectors with honest "would catch" vs "cannot catch"
  assessment.

### Detector count
- Built-in: 25 (was 19). Added A6, B7, D1, D2, F4, T5.

### Tests
- 152 passing (was 138). Added 13 new tests for the 6 new detectors.

## [0.7.0] — 2026-05-18

### Added
- **B5 TIVA** (Schimmack 2014) — z-score variance test on a set of independent
  study p-values; insufficient variance → potential p-hacking / selective
  reporting.
- **B6 GRIMMER** (Anaya 2016; Allard 2018) — `(mean, SD, N)` triple-consistency
  test. Stricter than B1 GRIM (which only checks mean × N).
- **T4 Tortured Phrases** (Cabanac 2021) — 50+ machine-translation
  fingerprint phrases ("profound neural organization" → "deep neural network").
  Detects paper-mill / synonym-laundered text.
- **B4 statcheck upgrades** — added **Q-test** for meta-analysis heterogeneity;
  whole-text one-tailed scan (if "one-tailed/one-sided/单尾" anywhere in the
  manuscript, switch matching t/r/z to one-tailed when that gives consistency).
- **`paperguard selfcheck`** — runs internal fixtures through all detectors as
  a sanity check on installation.
- **`paperguard explain`** — LLM-explanation of a specific finding from a JSON
  report (needs `PAPERGUARD_LLM_PROVIDER`).
- **`paperguard diff before.json after.json`** — track changes between two
  scan reports.
- **Auto-OA-PDF download** — `paperguard scan --doi X` (without `-f`) now
  attempts to download the OA PDF via Unpaywall.
- **docs/** — `detectors.md` (per-detector reference) and
  `epistemic_position.md` (vocabulary rule, innocent-explanation rule).
- **examples/04_full_pipeline_demo.py** — exercise every detector class.

### Detector count
- Built-in: 19 (was 16). Added B5, B6, T4.

### Tests
- 138 passing (was 120). Added: T4 ×5, B5 ×4, B6 ×4, CLI extras ×5.

## [0.6.0] — 2026-05-18

### Added
- **T3 — Data Availability + Ethics Audit** detector. Flags missing data
  statements, vague "available on request" without verifiable accessions,
  missing IRB/IACUC, missing trial registration (NCT/ISRCTN/ChiCTR/EudraCT),
  missing competing-interests disclosure.
- **F3 — Splice / Copy-Move Forensics** detector. Patch-level statistical
  signatures (mean / std / Laplacian variance) with translation-vote
  consistency to find pixel-level cloning that ORB-based F2 misses.
- **CLI auto-runs T3** on extracted PDF/docx text.

### Fixed
- **PDF image extraction** now filters out tiny embedded bitmaps (math
  symbols, font glyphs) by size (≥ 200×200 px, ≥ 8 KB) and SHA-256-dedups,
  eliminating massive F1 false-positive cascades on typeset PDFs.
- **G4 publisher-creator whitelist** — Springer / Elsevier / Wiley / LaTeX /
  pdfTeX / Acrobat Distiller / Word / LibreOffice etc. no longer trigger
  the "creator not in authors list" CONCERN. This was a 100% false positive
  on every published PDF.

### Tested on
- 2 real Nature Communications papers (ecology, OA) — both correctly
  classified as PASS with 0 findings.

## [0.5.0] — 2026-05-18

### Added
- **F2 — Bik-style internal image duplication** detector. ORB keypoint
  self-matching + RANSAC affine consensus to find copy-pasted patches inside
  a single image. Rotation/scale tolerant.
- **T1 — Text similarity** detector. 5-gram word-shingling + Jaccard against
  a user-supplied corpus (no network). For self-plagiarism and re-use.
- **T2 — Clinical-trial outcome consistency** detector. Compares paper's
  reported primary outcomes to ClinicalTrials.gov v2 API registration.
  Catches outcome switching (Goldacre 2019).
- **ORI sanctions** local CSV lookup (`paperguard.fetcher.ori_sanctions`).
- **LLM explainer** (opt-in via `PAPERGUARD_LLM_PROVIDER`) — supports
  OpenAI / Anthropic / Ollama. Hard-coded system prompt forbids the LLM
  from claiming fraud or inventing evidence.
- **Statcheck one-tailed support** — recognizes "one-tailed / 单尾" in the
  reporting context.
- **i18n: es, ja, de** language packs (now 5 total).
- **WCAG 2.1 AA** for HTML reports: focus-visible outlines, ARIA roles,
  semantic header/main/footer, `prefers-reduced-motion`, severity colors
  re-tuned for ≥ 4.5:1 contrast on white.
- New dependency: `opencv-python-headless` (for F2).
- 21 new tests (133 total).

## [0.4.0] — 2026-05-18

### Added
- **Plugin system** — third-party packages can register detectors via
  `paperguard.detectors` entry-point group. `DetectorRegistry.load_plugins()`
  discovers and instantiates them with safe error handling.
- **i18n** — report framework now supports `en` and `zh-CN` via a lightweight
  dict-backed `t()` helper (no gettext / .po toolchain). `--lang` flag added
  to `scan`. `PAPERGUARD_LANG` env var also honored.
- **Web UI** (`paperguard webui`) — FastAPI app with upload form, language
  selector, `/detectors` introspection endpoint, and `/scan.json` for
  programmatic use. Available via the `paperguard[webui]` extras.
- 14 new tests (91 total): i18n, plugin loader (mocked entry points), and
  webui (TestClient).

### Changed
- `paperguard` package now exposes `__version__`.
- `register_default(load_plugins=True)` is the new default; pass `False`
  to opt-out (used in tests).

## [0.3.0] — 2026-05-18

### Added
- **C1 Carlisle** baseline-imbalance detector for RCTs (Welch t per variable + Stouffer combination).
- **F1 image-duplication** detector via perceptual hash (`imagehash` library).
- **G1 image EXIF temporal forensics** — flags shooting time before claimed experiment start, after submission, and Photoshop signatures.
- **G3 docx rsid forensics** — identifies python-docx / pandoc-generated files via missing or homogeneous `w:rsid` values.
- **Image extractors** for .docx (word/media/) and .pdf (via pymupdf).
- **Retraction Watch CSV loader** — local lookup against the official dataset (no network).
- Tests: 19 new (67 total).

## [0.2.0] — 2026-05-18

### Added
- **A2 Benford** first-digit detector with applicability gate (≥ 2 decades of range).
- **B4 statcheck** — recompute reported `t / F / χ² / r / z` p-values from
  manuscript text, flagging decision-reversals as SUSPICIOUS and numeric
  inconsistencies as CONCERN.
- **PubPeer** client — surfaces existing public comments on a DOI.
- **PDF text and table extraction** via pymupdf + pdfplumber.
- **Docx inline-number classification** — extracts and classifies numbers from
  prose (p-values, percentages, mean ± SD, generic decimals).
- **HTML report export** (`--output-html`) — self-contained styled HTML.
- **Batch mode** (`paperguard batch --glob 'papers/*.pdf'`) for many files at once.
- **Dockerfile** for containerized usage.
- Roadmap, contributing guide, security policy, GitHub Actions CI.

### Changed
- `clean-meta` subcommand removed from PaperGuard; moved to a separate
  standalone tool to keep this project narrowly scoped to detection.
- `scan` now auto-handles .xlsx, .csv, .tsv, .docx, .pdf — both table data and
  free-text run through detectors as appropriate.

### Removed
- `src/paperguard/utils/docx_meta_writer.py` and the `clean-meta` CLI command.
  Cleanup tooling lives in a separate private repo to avoid coupling
  detection with anti-detection in one shipped product.

## [0.1.0] — 2026-05-18

### Added
- Initial MVP release with five detectors: A1 (terminal digit), A3 (inter-column
  arithmetic), A5 (decimal consistency), B1 (GRIM), G4 (file metadata forensics).
- Click-based CLI with `scan` and `search` subcommands.
- Rich terminal report + JSON export + immutable audit log.
- OpenAlex, CrossRef, and Unpaywall clients (`scan --doi` integration).
- BH–FDR p-value correction and severity escalation (PASS → CRITICAL).
- 22 tests, full `mypy --strict` + `ruff` clean.
