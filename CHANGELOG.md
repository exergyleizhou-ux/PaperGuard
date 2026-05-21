# Changelog

All notable changes to PaperGuard are documented in this file. Format follows
[Keep a Changelog](https://keepachangelog.com/) and the project adheres to
[Semantic Versioning](https://semver.org/).

## [2.1.16] — 2026-05-22 — WebUI scan-result cache (SHA-keyed Redis)

### Added
- **`src/paperguard/webui/scan_cache.py`** — `ScanResultCache` facade
  with `InMemoryCache` + `RedisCache` backends. SHA-256-keyed; default
  5-minute TTL. Same auto-detection pattern as `ratelimit.py`
  (`PAPERGUARD_REDIS_URL` → Redis, otherwise in-memory).
- `/projects/{project_id}/scan` now consults the cache before running
  detectors. Duplicate upload of the same exact file (same sha256)
  within TTL returns the cached audit payload instead of re-running
  the full 34-detector pipeline.
- Fail-open semantics: cache backend errors log warnings and return
  `None` (re-scan path). Never serve stale wrong data because Redis
  is flaky.
- 16 new tests in `tests/test_scan_cache.py` covering InMemory TTL,
  Redis hit/miss, backend failures, malformed entries, autodetect.

### Why this matters
Editorial workflows re-submit the same PDF multiple times (author
revision → second editorial pass → reviewer download → re-upload).
Each duplicate save previously cost a full 34-detector run. The
cache amortizes that to near-zero CPU on cache hit.

### Quality
- Tests: 427 (+16 from 411). Ruff clean. Mypy --strict clean. 93
  source files (was 92).

## [2.1.15] — 2026-05-22 — WebUI rate-limit + optional Redis backend (production-hardening)

### Added
- **`src/paperguard/webui/ratelimit.py`** — `RateLimiter` facade over
  two backends:
  - `InMemoryBackend` — process-local sliding-window counter using a
    timestamp-list per key + threading.Lock. Suitable for dev /
    single-process. Not safe across workers.
  - `RedisBackend` — Redis-sorted-set sliding-window counter that is
    safe across processes/workers/hosts. Selected automatically when
    `PAPERGUARD_REDIS_URL` env var is set; falls back to in-memory
    otherwise (with a warning at app start).
- `RateLimiter` defaults: **30 requests per 60 s per key**. The
  `/projects/{project_id}/scan` endpoint is now gated by
  `scan:user:{user.id}`. Over-cap requests get HTTP 429 with a
  proper `Retry-After` header.
- **Fail-open semantics**: any backend exception logs a warning and
  allows the request. We never block legitimate traffic because
  Redis is flaky.
- `paperguard doctor` gains a `webui_redis` check — `--ping-llm`-
  style live probe that hits the configured Redis URL once with
  `RedisBackend.hit("doctor-probe", ...)`. Reports GREEN /
  YELLOW (unset) / RED (unreachable).
- 15 new tests in `tests/test_ratelimit.py` (via `fakeredis`) plus 2
  new doctor tests covering the YELLOW (env unset) and GREEN
  (fakeredis-backed) cases.

### Dependency
- Added `redis>=4.0` and `fakeredis>=2.0` as optional `webui`-related
  install extras. The base install still works without them; the
  webui simply uses `InMemoryBackend` only.

### Quality
- Tests: 411 passed (+17). Ruff clean. Mypy --strict clean.
  92 source files (was 91).

## [2.1.14] — 2026-05-21 — Detector deep-dive pages for the 4 new detectors

### Added
- `docs/detectors/E1.md` — ICC Independence detector (Heathers 2024
  ICRP) — auto-generated, then enriched with calibration section.
- `docs/detectors/F6.md` — patch-splice detector (Bik 2016 mechanised)
  — auto-generated, then enriched with calibration history
  (2.1.7 default `z=4`/`cluster=4` → 2.1.9 calibrated `z=6`/`cluster=8`).
- `docs/detectors/T7.md` — perplexity proxy — auto-generated, then
  enriched with endpoint-limitation note and cross-link to the v9
  pre-wired re-analysis path.
- `docs/detectors/T8.md` — DetectGPT-style curvature — auto-generated,
  then enriched with the formal empirical N=20 finding (LR+ = 0 on
  cliproxy, two failure modes diagnosed).
- `docs/detectors/M1.md` — paper-mill graph (was missing).

### Changed
- `docs/detectors/README.md` — re-organised to **8 clusters**
  (added "Paper-mill graph"), lists all 34 detectors, marks the 4
  new ones with ⭐, embeds direct links to empirical-evidence docs
  (statcheck cross-validation, T6 recall_test_v10 first true
  positive, F6 recall_image_v2 calibration, T8 endpoint-limitation).
- Each new-detector page now has a "Calibration & empirical evidence"
  table summarising shipped-in version, default thresholds,
  opt-in flag, cost, and empirical LR+ where measured.

### Quality
No code changes. Tests: 394 / ruff clean / mypy --strict clean / 91
source files.

## [2.1.13] — 2026-05-21 — Continuity refresh (HANDOFF + docs/INDEX + README badges)

Pure docs / continuity release closing the 2.0.15 → 2.1.13 cycle.

### Changed
- **`HANDOFF.md`** rewritten from 2.1.5 to 2.1.13: ship history for
  all 17 versions (2.0.15 → 2.1.13), updated test count (372 → 394)
  and detector count (33 → 34), updated empirical-datasets table
  (added v10 / image_v2 / t8_controlled_benchmark with their
  headline numbers), open-work section reflecting that F6 is done
  and JOSS paper is ready, 15 tripwires (added GitHub secret-
  scanning trap from 2.1.5 push rejection), section 14 "headline
  numbers a fresh agent should not forget".
- **`README.md`** badges refreshed: status 2.0.1 → 2.1.12 (now
  reads from PyPI shield), tests 223 → 394, detectors 30 → 34,
  added "🤗 Live demo" badge, added doc-navigation header bar.
  New "What's new — 2.1.12" callout highlighting the v10 first
  true positive, F6 calibration, and JOSS-ready paper.

### Added
- **`docs/INDEX.md`** — central documentation directory listing all
  30+ docs by category (Start here / Detector reference / LLM-text
  family / Empirical studies / Methodology references /
  Operations / External). Single file users can land on to find
  any other doc.

### Quality
No code changes. Tests: 394 / ruff clean / mypy --strict clean / 91
source files.

## [2.1.12] — 2026-05-21 — Text-layer recall study v10 (N=200) — first true positive

### Added
- `scripts/recall_test_v10.py` — N=100+100 OpenAlex retracted /
  matched-control text-layer recall study. Resumable, 4× larger
  than v8.
- `scripts/recall_test_v10_results.json` — 159-record dataset
  (100 retracted + 59 matched controls).
- `docs/recall_test_v10.md` — 7-section analysis with the headline
  finding.

### Headline finding
At the default 0.003 threshold T6 remains 0 / 0 (consistent with
v8 / v9). But at a 0.001 threshold:

- **TPR = 1.37 %** (1 / 73 analysable retracted)
- **FPR = 0.00 %** (0 / 22 analysable controls)
- **LR+ = ∞** (no false positive observed in 22 controls)

The single true positive is `10.1371/journal.pone.0295951` — a 2024
"Improved SVM based on CNN-SVD for diabetic retinopathy" PLOS ONE
retraction with textbook paper-mill profile (post-ChatGPT, generic
ML on medical imaging, high-volume journal, subsequently retracted).
T6 density 0.00126 (4× the next-highest retracted, ∞× any control).

### Updated calibration position
The "T6 is a pre-submission tool" position from 2.0.16 holds for the
**default** threshold. At lower thresholds T6 is a **rare-event
high-precision** signal usable for editorial triage. Three threshold
profiles documented in `docs/recall_test_v10.md` § "Calibrated
interpretation".

### What's open
- Control PMC coverage was 37 % (22 / 59) due to OpenAlex subfield
  matching pulling non-PMC-indexed papers. A v11 should pre-filter.
- N=22 controls is small; "no FP" is honest but the 95 % Wilson
  upper bound is ≈ 15 %.
- T7 / T8 columns remain empty (cliproxy endpoint limitation; see
  `docs/t8_endpoint_limitation.md`).

### Quality
No code changes. Tests: 394 / ruff clean / mypy --strict clean.

## [2.1.11] — 2026-05-21 — JOSS-ready paper

### Changed
- `paper/paper.md` refreshed to current JOSS 2024 template format,
  reflecting 2.1.10 state: 34 detectors (was 33), F6 patch-splice
  documented in the families table, image-layer v2 N=18 study
  added to empirical-calibration section, T8 endpoint-limitation
  N=20 study added, B4 statcheck cross-validation N=41 study
  added, software-quality section with 394 test count and the
  `paperguard doctor` command, HF Space demo URL.
- Tags expanded with `image forensics` and `statcheck`.

### Added
- `paper/JOSS_SUBMISSION.md` — private submission walkthrough
  with pre-flight checklist, step-by-step instructions for
  https://joss.theoj.org/papers/new, anticipated reviewer
  checklist items, and what to do on rejection.

### What the user has to do
1. Register / look up ORCID at https://orcid.org/register and
   replace the `0000-0000-0000-0000` placeholder in `paper.md`.
2. Open https://joss.theoj.org/papers/new, paste the repo URL,
   choose branch `main` and version `v2.1.11`. Submit.
3. JOSS will auto-build the PDF from `paper/paper.md`.

### Quality
394 tests / ruff clean / mypy --strict clean / 91 source files.
No code changes from 2.1.10.

## [2.1.10] — 2026-05-21 — T8 endpoint limitation, formally demonstrated

The technical report (2.1.1) and the LLM-detection guide
(`llm_detection_v2.md`) both stated, on the basis of small-N probes,
that T7 + T8 cannot be meaningfully measured on the cliproxy
endpoint. This release provides the **formal empirical demonstration**.

### Added
- `scripts/t8_controlled_benchmark.py` — controlled 10 + 10 corpus
  (pre-2020 human academic methods prose vs LLM-marker-heavy AI
  prose), bypassing the PMC fetch overhead so the T8 signal itself
  can be isolated. Public, reproducible.
- `scripts/t8_controlled_benchmark_results.json` — raw run results
  on cliproxy `gpt-5.4-mini`.
- `docs/t8_endpoint_limitation.md` — 7-section report with the
  measurement protocol, per-sample scores, two-failure-mode
  diagnosis (paraphraser preserves LLM markers + naturalness rater
  is miscalibrated on technical prose), and the per-endpoint
  detector-compatibility matrix.

### Headline measurement
On cliproxy `gpt-5.4-mini`:

- **AI samples**: 9 / 10 hit SSL EOF mid-run; the 1 surviving sample
  scored 0.0 (all paraphrases rated 10/10, zero variance).
- **Human samples**: 10 / 10 completed but scores span [-6.0, +1.22]
  — pure noise. At the default SUSPICIOUS tier (`score < -0.5`),
  **50 % of human samples false-fire**.
- LR+ at SUSPICIOUS tier: **0** (worse than coin flip).

### Implication
The cliproxy endpoint can only meaningfully drive T6. T7 + T8
correctly return NOTE-level inconclusive findings rather than wrong
numbers, in line with the privacy iron rule. A GPT-4-class endpoint
with token logprobs is required to unlock live T7 + T8 LR+
measurement; the v9 dataset is pre-wired for that re-analysis.

No code changes. Tests: 394 / ruff clean / mypy --strict clean.

## [2.1.9] — 2026-05-21 — F6 default threshold calibration applied

The 2.1.8 release published the empirical finding that F6 at
`z=4, cluster=4` had FPR ≈ 75%. This release applies that finding.

### Changed
- `PatchSpliceInput` defaults: `z_threshold` 4.0 → **6.0**;
  `min_cluster_size` 4 → **8**. These are the "triage tier" from
  `docs/recall_image_v2.md`. Empirical effect on the same N=18
  corpus: LR+ 0.93 → 1.12; FPR 75 % → 62.5 %; TPR unchanged at 70 %.
- `docs/recall_image_v2.md` gains a calibration-grid table showing
  the full threshold sweep, including a grid-optimal cell
  (`z=6, cluster=20`, LR+ 1.20) that we deliberately do **not**
  make default because N=18 is too small to justify it.
- `scripts/recall_image_v2_calibrated.json` — annotated v2 results
  with the new-threshold severity recomputed deterministically.

### Compatibility
Users who want the prior (research-mode) behaviour pass
`PatchSpliceInput(z_threshold=4.0, min_cluster_size=4)` explicitly.
Existing F6 unit tests passed unchanged at the new defaults.

### Quality
394 tests / ruff clean / mypy --strict clean / 91 source files.

## [2.1.8] — 2026-05-21 — F6 empirical calibration (recall_image_v2)

### Added
- `scripts/recall_image_v2.py` — extends recall_image_v1 to run F6
  alongside F1 + F4 on N=10+8 OpenAlex post-2020 retracted/control
  papers. Per-paper outputs include `f6_max_z`, `f6_largest_cluster`,
  `f6_severity`, `f6_images_flagged`.
- `scripts/recall_analyze_image_v2.py` — analyser that computes
  single-detector LR+ at NOTE-and-CONCERN thresholds, joint LR+ for
  every F1/F4/F6 combination, and a per-paper table.
- `scripts/recall_image_v2_results.json` — raw run output.
- `docs/recall_image_v2.md` — interpretation with honest calibration:
  **F6 at default `z ≥ 4` is too sensitive for general use** (TPR 70 %,
  FPR 75 %). Recommendation: tune to `z ≥ 6` and `cluster ≥ 8` for
  triage use; defaults preserved for research / experimentation.

### Honest finding
F6's mechanism — per-channel histogram discontinuity — fires on any
image with strong content edges (well-plate borders, fluorescent
panel composition, micrograph tissue interfaces). At the default
threshold this overwhelms specificity. The doc adds a per-use-case
calibration table so users can pick the threshold matching their
precision / recall preference.

No code changes (F6 itself is unchanged from 2.1.7). Tests: 394 /
ruff clean / mypy --strict clean.

## [2.1.7] — 2026-05-21 — F6 patch-splice detector (Bik 2016 style)

### Added — F6 detector (built-in count: 33 → 34)
- `src/paperguard/detectors/f6_patch_splice.py` — **per-channel
  colour-histogram patch discontinuity** detector. Implements the
  signal Elisabeth Bik et al. (2016, *mBio*) used as their primary
  visual cue for splicing in their 20,000-paper screen.
- Algorithm: divide image into ``patch_size × patch_size`` patches
  (default 32 × 32, non-overlapping); per patch, compute three 16-bin
  per-channel histograms; for each patch compute Jensen-Shannon
  divergence to its 4-neighbours, summed across channels; robust
  z-score using median + MAD; flag patches with z ≥ 4; report
  largest 8-connected component of outliers.
- Severity tiers: z < 4 → no finding; 4 ≤ z < 6 (no cluster) → NOTE;
  z ≥ 6 OR cluster ≥ 4 → CONCERN; both → SUSPICIOUS.
- 12 new tests in `tests/test_f6_patch_splice.py`: synthetic clean
  vs spliced images, tiny-image skip, JSD properties, connected-
  component edge cases, ≥ 4 innocent_explanations per finding,
  privacy iron rule (no verdict words).
- Registered as 34th built-in. Plugin entry-point system unchanged.

### Differs from F3
F3 already detects splicing via luminance mean/var/Laplacian
similarity. F6 captures a complementary signal — *colour-channel
discontinuity* — that catches grafts where the inserted region's
colour balance differs from the recipient even when luminance has
been corrected. F3 + F6 together catch a wider range of inserts
than either alone.

### Tests
- 394 passed (+12) / 0 failed / ruff clean / mypy --strict clean
- 91 source files (was 90, F6 module added)

## [2.1.6] — 2026-05-21 — `paperguard doctor` diagnostic command

### Added
- **`paperguard doctor`** — new CLI subcommand that runs an environment
  health check covering 19+ items: Python version, required + optional
  dependencies, detector registry (≥ 33 expected), entry-point plugin
  discovery, cache directory writability, dynamic T6 dictionary state,
  F4 image-corpus presence, and LLM endpoint configuration.
- `--ping-llm` flag adds a live 1-token API probe (off by default).
  Reports back the endpoint's `logprobs_supported` field so a user can
  tell at a glance whether T7 will work on that endpoint.
- `--json` flag for CI use; shape `{summary: {green, yellow, red},
  checks: [{name, status, detail}]}`.
- Exit codes: 0 = all green, 2 = at least one yellow (non-fatal), 1 =
  at least one red. Use in CI as a pre-flight check.
- 10 new tests in `tests/test_doctor_cmd.py` including a privacy-rule
  assertion that the doctor never uses verdict words.

### Tests
- 382 passed (+10) / 0 failed / ruff clean / mypy --strict clean

## [2.1.5] — 2026-05-20 — Continuity polish

Pure docs / continuity refresh.

### Changed
- `README.zh.md` synced to 2.1.5: badges (was 2.0.0 / 30 detectors /
  223 tests → 2.1.5 / 33 detectors / 372 tests), detector list (added
  E1 / M1 / T6 dynamic / T7 / T8), HF Space link in header, new
  "实证标定" section with the honest LR+ numbers.

### Added
- `HANDOFF.md` — successor to the 2.0.14 handoff document. Captures
  2.1.5 state, credentials, cliproxy quirks, the 14 tripwires, ship
  workflow, and the 6 priority directions (8.A–8.F) for the next
  session. Pasting it whole brings the next agent up to speed without
  context loss.

No code changes. Tests: 372 / ruff clean / mypy --strict clean.

## [2.1.4] — 2026-05-20 — Docs polish

Pure docs refresh — closes out the 2.0 → 2.1 ship cycle.

### Changed
- `README.md` documentation table: added rows for the image-layer
  recall study, the B4 statcheck cross-validation, the JOSS paper
  draft, and the live HuggingFace Space demo URL. Corrected the
  CHANGELOG range from `0.1 → 2.0.2` to `0.1 → 2.1.3`.
- `ROADMAP.md`: marked all the 2.0 / 2.1-cycle items as shipped,
  added a new "2.2 — Next horizon" section listing real-GPT-4o
  T7/T8 measurement, Bik splice/wash extension, statcheck-R Cohen's
  κ comparison, F1/F4 expansion to N=100, Redis cache, and old
  `.doc`/`.docb` image extraction as the actual remaining work.

No code changes. Tests: 372 / ruff clean / mypy --strict clean.

## [2.1.3] — 2026-05-20 — Phase-8: B4 statcheck cross-validation + HF Space deployed

Two independent additions.

### Added — B4 statcheck cross-validation (option d)
- `scripts/crossval_statcheck.py` — N=41 ground-truth statistical-claim
  corpus with analytical scipy reference. Runs B4 against the corpus
  and measures TP / FP / FN / TN, recall, precision, decision-flip
  recall.
- `scripts/crossval_statcheck_results.json` — raw results.
- `docs/crossval_statcheck.md` — interpretation.
- **Headline**: recall 100 %, precision 64 %, decision-flip recall
  94.12 %. PaperGuard's B4 misses **no** materially inconsistent
  claims and catches the most consequential decision-flip class at
  near-perfect rate. The 9 "false positives" are all
  small-magnitude rounding inconsistencies that the original
  statcheck protocol also flags (consistent with Nuijten et al.
  2016 §2.3).

### Deployed — HuggingFace Space (option f)
- `examples/hf_space_app.py` synced to
  https://huggingface.co/spaces/exergyleizhou/paperguard-demo as
  `app.py`.
- `examples/hf_space_requirements.txt` synced as `requirements.txt`
  with `paperguard>=2.1.2` pin.
- Live demo lets visitors paste a DOI / upload a PDF / paste text
  and run the full T6 + T7 + T8 + LLM-review stack from a browser.

No detector-code changes. Tests: 372 / ruff clean / mypy --strict
clean.

## [2.1.2] — 2026-05-20 — Phase-5+: image-layer recall + T6 abstract-only + JOSS paper

Bundles three independent improvements:

### Added — F1 / F4 image-layer recall study (Phase 5)
First published LR+ measurement for the **image-content** detector
family — F1 (intra-paper pHash duplication) and F4 (cross-paper image
re-use). Closes one of the three "future work" items in the
technical report.
- `scripts/recall_image_v1.py` — N=30+30 image-layer study via
  OpenAlex retracted + subfield-matched controls, PMC/Unpaywall PDF
  fetch, F1+F4 over each paper. Resumable.
- `scripts/recall_analyze_image.py` — Markdown report generator with
  LR+ tables at CRITICAL / SUSPICIOUS / CONCERN, hamming-distance
  distribution per arm, joint F1 ∨ F4 row.
- `scripts/recall_image_v1_results.json` — raw study output.
- `docs/recall_image_v1.md` — human-readable report including
  discussion of why population-LR+ under-counts F1/F4's value on
  targeted forensic use cases.

### Added — T6 abstract-only mode (Phase 7)
Empirically motivated by recall_test_v8: full-text T6 has LR+ ≈ 0
on Nature-tier retracted papers because copy-editing removes lexical
LLM markers from Methods / Results / Discussion. The abstract +
introduction is the author-written zone least touched by copy-editing.
- New env var `PAPERGUARD_T6_ABSTRACT_ONLY=1` and CLI flag
  `--t6-abstract-only` on `scan` and `scan-pmc`.
- New helper `paperguard.detectors.t6_ai_text_heuristic._extract_unedited_zone`
  slicing the input from "Abstract" to "Methods" header (or 6000 chars).
- Drops `MIN_WORDS` to 150 in abstract-only mode (abstracts are short).
- 10 new tests demonstrating abstract-only density > full-text density
  when LLM markers are concentrated in the abstract.

### Added — JOSS paper manuscript (Phase 6)
- `paper/paper.md` — JOSS-format manuscript (summary, statement of
  need, design, empirical calibration), citing the technical report
  for full methodology.
- `paper/paper.bib` — 10 references (Nuijten, Brown, Carlisle, Bik,
  Benjamini-Hochberg, Kobak, Cabanac, Mitchell, Gehrmann, Heathers).
- `.github/workflows/draft-pdf.yml` — GitHub Action using the
  `openjournals/openjournals-draft-action` to build paper.pdf on
  every push to `paper/**`.
- `CITATION.cff` updated to 2.1.2 with the LLM-detection keyword set.

### Tests
- 372 passed (+10 since 2.1.1) / 3 deselected.
- ruff + mypy --strict clean across 90 source files.

## [2.1.1] — 2026-05-20 — Technical report (Phase-4 docs)

Pure docs release.

### Added
- `docs/paperguard_technical_report.md` — 7-section technical
  report documenting methods, LLM-text family (T6/T7/T8), N=85
  empirical study, T6 calibration, and reproducibility.
- README links to the technical report and the LLM-detection guide.

No code changes. Tests: 362 / ruff clean / mypy --strict clean.

## [2.1.0] — 2026-05-20 — Phase-3: N=100 LR+ retest, T6/T7/T8 transparent dataset

Phase 3 (and final phase) of the LLM-detection deepening plan.
**Minor version bump** because the v9 dataset and the recall_analyze
machinery are new public artifacts the project commits to maintaining.

### Added — recall_test_v9 N=100 study
- `scripts/recall_test_v9.py` — N = 100 retracted + 100 controls,
  year filter 2020+, optional T7 + T8 runs.
- `scripts/recall_analyze_v9.py` — produces `docs/recall_test_v9.md`
  with per-detector LR+ tables. When T7/T8 returned no scores
  (because the configured endpoint is weak), the report annotates
  that explicitly rather than computing meaningless numbers.
- `docs/recall_test_v9.md` — first version using cliproxy
  `gpt-5.4-mini`. T6 LR+ confirms the v8 finding at larger N.
  T7 / T8 outcomes documented as "no logprobs / no scores" pending
  GPT-4o-class endpoint access.

### Empirical headline
With cliproxy `gpt-5.4-mini`:
- T6 at default 0.003 CONCERN threshold: same direction as v8 —
  post-publication Nature-tier signal is near-zero. T6 is calibrated
  as a pre-submission / preprint screening tool.
- T7 / T8: not measurable on this endpoint. Code remains shipped
  and unit-tested; live LR+ awaits a logprobs-capable endpoint with
  a stronger paraphraser.

### Position of the project
PaperGuard's value proposition for the LLM-text layer is now
explicit: **detection is a triage signal, not a verdict**. The
N=100 v9 study is the dataset future detectors can be measured
against — re-run `scripts/recall_analyze_v9.py` on stronger
endpoints to extend the LR+ tables.

### Tests
- 362 passed (unchanged from 2.0.17 — Phase 3 adds dataset
  scripts, not core detector code).
- Ruff + mypy --strict clean.

## [2.0.17] — 2026-05-20 — Phase-2: HF Space demo app + deploy guide

Phase 2 of the 3-phase LLM-detection deepening plan. Pure devex /
docs release — no detector changes.

### Added — HuggingFace Space demo
- `examples/hf_space_app.py` — Gradio app with three opt-in detector
  toggles (T7 perplexity, T8 DetectGPT, LLM content review), DOI
  fetch via Europe PMC, raw-text paste mode, instant-demo example
  carousel of 3 public retracted DOIs.
- `examples/hf_space_requirements.txt` — pinned deps for the Space.
- Surfaces the empirical v8 recall finding to demo visitors so they
  understand T6 alone is a pre-submission screening signal, not a
  post-publication forensics signal.

### Deploy
Copy `examples/hf_space_app.py` → Space's `app.py`, copy
`examples/hf_space_requirements.txt` → `requirements.txt`, push.

## [2.0.16] — 2026-05-20 — Phase-1 batch: T8 DetectGPT, public dictionary, batch/notify flags, N=50 LR+ study

Phase 1 of the 3-phase LLM-detection deepening plan. Adds the T8
DetectGPT-style detector, the official phrase dictionary, opt-in flags
on batch/notify/scan-pmc, and the first empirical LR+ study against
real OpenAlex retraction data.

### Added — T8 DetectGPT detector
- New detector `T8` at `src/paperguard/detectors/t8_detectgpt.py`,
  registered in the default registry (33 built-ins now).
- Probability-curvature signal adapted to chat-completion APIs (no
  token logprobs required). Asks the LM to paraphrase the passage K
  times and to score original vs paraphrase naturalness on a 1-10
  scale; computes a z-style detection score from the gap.
- Opt-in via `--detectgpt-check` flag on `scan`, `scan-pmc`, `batch`,
  `notify`. Sets `PAPERGUARD_DETECTGPT_CHECK=1`.
- Severity tiers (defaults): score ≥ 0 → no finding;
  0 > score ≥ -0.5 → NOTE; -0.5 > score ≥ -1.5 → SUSPICIOUS;
  score < -1.5 → CRITICAL. ≥ 4 innocent explanations per finding.
- 12 new tests in `tests/test_t8_detectgpt.py`.

### Added — Official phrase dictionary
- `docs/dictionaries/llm_phrases_v1.json` — 103 phrases (GPT 40,
  Claude 24, Gemini 24, generic 15).
- New `paperguard refresh-ai-dict --official` shortcut and default
  `--source` URL pointing at the GitHub-hosted JSON. Running
  `paperguard refresh-ai-dict` with no flags now pulls the official
  dictionary.

### Added — `--perplexity-check` / `--detectgpt-check` on batch + notify
- The opt-in LLM-detector flags are now available on every command
  that runs the text-detector flow (scan, scan-pmc, batch, notify).
- T7 / T8 still default OFF; they require explicit opt-in to avoid
  surprising API costs.

### Added — recall_test_v8 empirical study
- `scripts/recall_test_v8.py` and `scripts/recall_analyze_v8.py`
  produce `docs/recall_test_v8.md`.
- N = 50 OpenAlex-retracted + N = 50 subfield-matched controls;
  Europe PMC full text where available (35 retracted, 9 controls
  resolved — Nature-tier subfields underrepresented in PMC).
- **Headline finding (T6 alone):** at the default 0.003 CONCERN
  density threshold, T6 fires on 0% of post-publication retracted
  Nature-tier papers and 0% of controls. T6 is therefore a
  **pre-submission / preprint-screening signal**, not a post-
  publication forensics signal — by the time a paper reaches a
  copy-edited Nature-tier journal, lexical LLM markers have largely
  been removed by editors.
- T7 / T8 live LR+ deferred to a future GPT-4o-class endpoint that
  exposes token logprobs and provides a paraphraser that drifts off
  the LLM-likelihood manifold (cliproxy gpt-5.4-mini does neither).

### Changed — T7 perplexity simplification
- Removed the generation-divergence fallback added in development —
  empirical probing showed the directional signal was inverted on
  weak-model proxies. T7 now returns only the logprobs perplexity or
  a NOTE-level "inconclusive" finding. T8 is the proper alternative
  for endpoints without logprobs.

### Tests
- 362 passed (+14 since 2.0.15) / 0 failed.
- Ruff + mypy --strict both clean.

## [2.0.15] — 2026-05-20 — LLM detection v2: dynamic T6 dictionary + T7 perplexity proxy

Two complementary additions deepen the LLM-text detection layer. Both
are additive — built-in detectors and existing recall numbers are
unchanged.

### Added — T6 dynamic dictionary (`paperguard refresh-ai-dict`)
- `src/paperguard/llm/dynamic_dictionary.py`: user-editable phrase
  dictionary at `~/.paperguard/ai_dictionary.json`, merged into T6 at
  detector load time.
- Refresh from a remote JSON file (`--source URL`) or extract candidate
  2- to 4-grams from a local corpus of suspected LLM output
  (`--corpus PATH`). Stopword + human-baseline filters prevent common
  English phrases from polluting the dictionary.
- `--dry-run` shows the set diff (added / removed phrases per provider)
  without writing.
- The user dictionary is **additive** — built-in phrases are never
  removed, so test fixtures and recall numbers remain reproducible.
- 17 new tests in `tests/test_dynamic_dictionary.py`.

### Added — T7 LLM perplexity detector (opt-in)
- New detector `T7` at `src/paperguard/detectors/t7_perplexity.py`,
  registered in the default registry (32 built-ins now).
- Continuation-perplexity proxy compatible with chat-completion APIs:
  asks the reference LM to continue the manuscript text and aggregates
  the per-token logprobs of its completion. Lower perplexity is a
  paraphrase-resistant signal of LLM authorship — complementary to
  T6's dictionary-tic approach.
- Opt-in via `--perplexity-check` flag on `paperguard scan` and
  `paperguard scan-pmc` (sets `PAPERGUARD_PERPLEXITY_CHECK=1`).
- Severity tiers (defaults, override via class attributes):
  perplexity ≥ 20 → no finding; 10–20 → NOTE; 5–10 → SUSPICIOUS;
  < 5 → CRITICAL. Each finding carries ≥ 4 innocent explanations
  (privacy iron rule).
- Honours `PAPERGUARD_LLM_BASE_URL` + `PAPERGUARD_LLM_MODEL` so the
  cliproxy / OpenRouter / team-pool path works out of the box.
- Failures never raise: missing API key / no logprobs / network error
  produce a NOTE-level "inconclusive" finding instead of crashing.
- 14 new tests in `tests/test_t7_perplexity.py`.

### Added — docs/llm_detection_v2.md
- Side-by-side comparison of T6 (lexical) and T7 (statistical), with
  guidance on when each is meaningful and how to combine them.

### Tests
- 348 passed (+31 since 2.0.14) / 0 failed.
- Ruff + mypy --strict both clean.

## [2.0.14] — 2026-05-20 — Math depth v3: T6 provider attribution + B6/E1/B5/C1/D1 upgrades + integrity index

Single biggest batch of statistical depth since 2.0. Seven separate
upgrades land together. All preserve back-compat; everything new is
**added** alongside existing detectors.

### Added — T6 provider attribution (GPT / Claude / Gemini)
- T6's phrase dictionary split into per-provider sub-dictionaries.
- New `_provider_attribution(text)` returns the most-likely LLM
  source given the phrase mix. Emits a NOTE-level finding when one
  provider dominates without crossing the global density threshold.
- 4 new test patterns covering each provider + neutral text.

### Added — B6 GRIMMER reverse sample reconstruction
- New `_enumerate_candidate_samples(...)`: SPRITE-style hill-climbing
  enumeration of integer samples consistent with reported (mean, SD,
  N, scale).
- New optional `reported_median / reported_min / reported_max` fields
  on `GRIMMERInput`. When provided, B6 compares them against the
  ranges spanned by reconstructed candidates and emits CRITICAL on
  mismatch. Heathers et al. (2018) SPRITE methodology.

### Added — E1 ICC repeated-measures independence detector (NEW)
- Brand-new detector covering Heathers (2024) ICRP pattern.
- Auto-detects subject/cluster column by name heuristic. Computes
  ICC(1) one-way random-effects. ICC < 0.05 with k≥3 repeats →
  SUSPICIOUS; ICC < 0.01 → CRITICAL. Targets fabricated-from-scratch
  repeated-measures data that forgot within-subject correlation.

### Added — B5 TIVA meta-analytic z (Stouffer + R-index + I²)
- TIVA's variance test now ships with three sibling statistics:
  Stouffer's combined Z, Schimmack R-index (success rate − median
  power), and Cochran Q + I² heterogeneity.
- Meta-signals fire when R-index < -0.35 (k≥6) or I² < 0.02 (k≥10),
  publication-grade thresholds informed by Schimmack 2016 + Higgins
  & Thompson 2002.

### Added — C1 Carlisle Bayes factor (BIC approximation)
- Adds `log10_bayes_factor` to every C1 finding evidence dict.
- BIC approximation: `log10(BF10) ≈ (k - 2·ln(p_combined)) /
  (2·ln(10))`. Strong evidence at log10(BF) > 2 (Kass & Raftery 1995).
- No new dependencies — pure scipy + math.

### Added — D1 Hurst exponent
- Rescaled-range (R/S) Hurst exponent on each column's value series.
- Pure numpy; no `pywt` dependency. H ≈ 0.5 = i.i.d. random; H > 0.75
  = over-smooth, classic Stapel signature.

### Added — Cross-detector Stouffer integrity index
- `AuditReport.integrity_z` and `integrity_score` populated by
  `combine_evidence`.
- Single-number summary across all finding p-values (BH-FDR adjusted)
  via Stouffer combination. Lower score / higher z = more concerning.
- Powers a one-glance integrity verdict over the 30+ detector
  ensemble.

### Quality
- 317 tests passing (was 299; +18 new in `tests/test_math_upgrades_v3.py`);
  mypy --strict + ruff clean.
- 32 built-in detectors now (was 30).
- New module `paperguard.detectors.e1_icc_independence`.

## [2.0.13] — 2026-05-20 — Math depth upgrades (A1 + A2 + A3)

Three statistical depth upgrades. Each adds new finding types on top
of the existing single-column tests, catching fabrication patterns
that pass the v0-2.0.12 statistics. See [docs/math_upgrades_v2.md](docs/math_upgrades_v2.md)
for the full mathematical justification.

### A1 — added Lag-1 autocorrelation
- Binomial test on `P(d_i = d_{i+1})` for the digit sequence of each
  column. Catches "I varied digits but avoided repeats" and "I used a
  template that produces positive autocorrelation".
- p < 1e-4 → SUSPICIOUS; p < 0.01 → CONCERN; N < 50 → skip.

### A1 — added joint multi-column entropy
- Bootstrap-based test on row-wise digit entropy across columns.
  Catches "I bashed in one row at a time and my row digits are
  correlated across columns".

### A3 — added multivariate OLS synthetic-combination detector
- For each column, regress on the others; flag if R² ≥ 0.99999 and
  σ_resid < 1e-5 (CRITICAL) or R² ≥ 0.9999 with sparse coefs
  (SUSPICIOUS).
- Catches `col4 = 2*col1 + col2 - 0.3` patterns that pair-wise A3
  cannot see.
- No scikit-learn dependency; sparsity is approximated as
  "coefs with |β| ≥ 1% of max|β|".

### A2 — added segment Benford stability
- Split column into N=3 ordered segments, compute Benford χ² for
  each, flag when variance < 0.5 (CONCERN). Catches "batch-generated
  from one template" patterns.

### Quality
- 299 tests passing (was 283; +16 new in `tests/test_math_upgrades_v2.py`);
  mypy --strict and ruff clean.
- All new tests fire correctly on synthetic fabrication, do not fire
  on the genuine fixture (golden anti-regression test still passes).
- New `docs/math_upgrades_v2.md` explains each statistic, the H_0,
  severity mapping, why thresholds are what they are, and what
  the upgrades *don't* solve.

## [2.0.12] — 2026-05-20 — PMC full-text + Slack/Discord notify + LLM proxy

### Added — `paperguard scan-pmc DOI`
- New CLI command that fetches the full JATS XML from Europe PMC
  (`paperguard.fetcher.europepmc`) and runs B4 / T3 / T4 / T5 / T6
  detectors over the *clean* text, no PDF parsing needed.
- Optional `--llm-review` flag wraps the LLM content reviewer
  around the PMC body, useful for scanning OA biomedical literature
  in bulk without managing PDF downloads.
- 7 new tests covering DOI→PMCID lookup, fullTextXML fetching, JATS
  parsing, network errors, and end-to-end pipeline.

### Added — `paperguard notify` for team daily digests
- New CLI command: `paperguard notify "papers/*.pdf"
  --webhook URL --min-severity SUSPICIOUS`. Scans every matched file
  and POSTs a single digest message to Slack or Discord (auto-
  detected by URL host) listing only papers meeting the severity
  threshold.
- No HTTP call when nothing crosses the threshold (silent days =
  silent webhook).
- Generic webhooks supported (sends both `{"text"}` and
  `{"content"}` keys).

### Added — Custom LLM base_url support
- `PAPERGUARD_LLM_BASE_URL` overrides the OpenAI endpoint, enabling
  team proxy pools (OpenRouter, CLI-proxy, self-hosted gateways).
- `PAPERGUARD_LLM_NO_JSON_MODE=1` for proxies that 400 on
  `response_format={"type": "json_object"}`.
- Verified live with a user-supplied team pool serving
  `gpt-5.4-mini`; LLM correctly flagged arithmetic / implausible-
  precision / stat-misuse issues end-to-end.

### Quality
- 283 tests passing (was 276; +7 new); mypy --strict and ruff clean.

## [2.0.11] — 2026-05-19 — Author retraction history + LLM content review

Two external-signal additions. v7 confirmed PDF-internal features
cannot distinguish retracted from non-retracted; both of these
exploit data *outside* the PDF.

### Added — Author retraction history scan
- `paperguard scan --doi X` now queries OpenAlex for each author's
  retraction history (≤ 200 most-recent works per author,
  is_retracted flag synced with Retraction Watch).
- Emits AUTHOR_HISTORY finding tiered by count:
  - 1-2 retracted works → `SUSPICIOUS` (could be honest)
  - 3+ retracted works → `CRITICAL` (Stapel / Fujii / Hwang pattern)
- Lists 4 innocent explanations including "high-volume authors have
  more absolute retractions at the same rate" and "may have been a
  low-level contributor on multi-author retractions".
- This is the cross-paper signal v7 specifically called out as the
  practical path to non-PDF-only detection.

### Added — Opt-in LLM content review
- New `paperguard scan --llm-review` flag. Requires
  `PAPERGUARD_LLM_PROVIDER` (openai / anthropic / ollama) + the
  matching API key.
- New `paperguard.llm.content_review.LLMContentReviewer` reads the
  manuscript text and asks the LLM to flag passages in 5 specific
  categories: **arithmetic** (numbers that don't add up),
  **contradiction**, **missing** (referenced but not described
  methodology / statistic / ethics), **implausible_precision**,
  **stat_misuse**.
- System prompt explicitly forbids verdict words ("fraud" /
  "misconduct" / "造假") and intent attribution.
- Output is gated through `issues_to_findings()` which severity-maps
  per category and adds 4 innocent explanations.
- Hallucination guard: any LLM-quoted "passage" not appearing in
  the input text is dropped.
- 9 new tests covering: disabled state, short-text guard,
  malformed-JSON drop, hallucinated-passage filter, invalid-category
  filter, 5-issue cap, severity mapping, innocent-explanations.

### Quality
- 276 tests passing (was 267; +9 new); mypy --strict and ruff clean.
- The library + CLI are now at **11 releases across the 2.0 line**
  with the precision-improvement work this session lands.

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
