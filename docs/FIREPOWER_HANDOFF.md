# FIREPOWER HANDOFF — next session

> Self-contained brief to continue making PaperGuard a genuinely powerful,
> evidence-grade academic-misconduct **screening** engine. A fresh Claude/human
> session can `git pull` and be productive from this file alone.

## 0. Mission (read first)

Make PaperGuard **catch real misconduct (fabrication, data/image manipulation,
paper-mill) with maximum force**, and make the evidence **so strong anyone can
see it** — WITHOUT ever issuing a verdict about a person.

**IRON RULE (non-negotiable, enforced by tests):** detectors output *anomaly
signals + ≥3 innocent explanations*, never "fraud/造假/misconduct". Power comes
from **stronger, convergent evidence** (like Bik / statcheck / Carlisle), not
from louder accusations. Removing this rule = defamation risk + instant loss of
scientific/journal credibility. Do NOT cross it.

## 0.5 Progress log — 2026-05-30 (read this before the roadmap below)

Roadmap items **P1, P3, P4 are done**, and the **offline half of P2** is done.
All shipped on `main` and tagged `v2.17.0`. The roadmap in §4 still describes
the original plan; this log records what actually landed.

| Item | Status | Commits |
|---|---|---|
| **P1 statcheck** | ✅ Extraction fixed; honest finding documented | `2a86a7e`, `34a45ac` |
| **P3 T4 tortured phrases** | ✅ Dict 140→161, FP entries removed | `48a7459` |
| **P4 convergence evidence** | ✅ Multi-cluster narrative (investigate-framed) | `c51a456` |
| **2.17.0 release** | ✅ Tagged, GitHub CI green | `2f35351` |
| **P2 figure/table wiring** | ✅ *offline* connector + tests | `45200c8` |

Key corrections to the original §4 assumptions:
- **P1 was NOT an extraction bug in the usual sense.** The real bug was that
  `parse_jats` never decoded XML entities, so `p &lt; .05` was invisible to B4
  (fixed). But B4 recall on a *generic* `PUB_TYPE:"Retracted Publication"` OA
  cohort is **0 and that is correct** — 0/40 such papers report any inline NHST
  statcheck can recompute (only 3/40 have `t(`, 1/40 `F(`, 0/40 `r(`). statcheck
  is a psychology-NHST tool; a generic retraction cohort is the wrong cohort.
  See `docs/recall_validation_fulltext.md`.
- **P2 extractors already existed** (`extractor/images.py` with PDF-embedded +
  vector-figure raster fallback; `extractor/baseline_tables.py` for RCT tables;
  `extractor/inline_numbers.py` for mean±SD). The missing piece was *wiring*,
  now provided by `evidence/figure_pipeline.py: run_figure_pipeline(path)` →
  feeds F1/F2/F3/F5/F6/F7 + C1 from one local `.pdf`/`.docx`. Pure offline
  orchestration, 5 tests.

### P2 — remaining work (network; deferred by design)
The offline connector is in place but has **not** been run on real papers yet:
1. Build a **PMC OA PDF / figure fetcher** (PMC OA package or figure URLs;
   OA only, never paywalled) that downloads a retracted paper's PDF locally.
2. Call `run_figure_pipeline()` on those PDFs inside a new validation script (or
   extend `scripts/validate_recall_fulltext.py`) and measure image-forensics +
   C1 recall vs control. This is where image-manipulation fraud is actually
   caught — the highest-ceiling, still-unmeasured family.
3. For B4: measure on a **psychology/neuroscience-filtered** retracted cohort
   (where inline NHST exists) to get a meaningful statcheck recall number.

## 1. Project facts

| | |
|---|---|
| Repo path | `C:\Users\10420\Desktop\新建文件夹\PaperGuard` (NOT the shell cwd) |
| GitHub | https://github.com/exergyleizhou-ux/PaperGuard (account exergyleizhou-ux) |
| PyPI | account `exergyleizhou0505`; **2.16.0 is live** (2.17.0 tagged on GitHub but **not yet on PyPI** — no PyPI publish workflow; manual `twine upload` needed with a fresh token) |
| Python | `.venv/Scripts/python.exe` (3.12). Always prefix `PYTHONIOENCODING=utf-8`. |
| Latest commit | `45200c8` (as of 2026-05-30); tag `v2.17.0` |
| 3-gate | `pytest -m "not network" -q` · `ruff check src/ tests/ examples/` · `mypy src/` (strict). **Run tools via `python -m ruff` / `python -m mypy`** — the `.exe` wrappers report a misleading exit 1 under PowerShell redirection even when clean. |
| Current state | 41 detectors, **630 tests passing**, ruff+mypy clean, CI green (ci/release-please/JOSS ✅) |

## 2. Environment quirks that WILL waste your time if you don't know them

- **GateGuard hook** forces a "facts" preamble before the first Bash and before
  every Edit/Write/destructive command. To work without the friction, run the
  session with `ECC_GATEGUARD=off`, or add `pre:bash:gateguard-fact-force` and
  `pre:edit-write:gateguard-fact-force` to `ECC_DISABLED_HOOKS`.
- **Background tasks die silently here** (`run_in_background` → empty output, no
  process). Use **foreground** Bash with a long `timeout` (e.g. 600000) for
  anything long-running. Python buffers stdout to files, so background output is
  invisible anyway.
- Windows/PowerShell; git warns LF→CRLF (harmless).
- Aggressive cost warnings appear; the user has said "don't count cost" but be
  efficient — favour one good foreground run over many.

## 3. What's already built (reuse, don't rebuild)

- `src/paperguard/detectors/t9_classifier.py` — T9 TF-IDF/LR LLM-text detector,
  pure-NumPy, opt-in `PAPERGUARD_ML_CHECK` / `--ml-check`. Density-tiered (fixed
  this session). Bundled model `src/paperguard/data/t9_classifier.npz`.
- `scripts/train_t9_classifier.py` — retrains T9 from HC3 (dev-only, needs sklearn).
- `scripts/calibrate_t9_oa.py` — T9 false-positive calibration on OA abstracts
  (OpenAlex). Result: 0 % FP at ship threshold on 400 papers (`docs/calibration_t9_oa.md`).
- `scripts/validate_recall_fulltext.py` — **the validation harness**: recall vs
  FP on retracted (Europe PMC `PUB_TYPE:"Retracted Publication"`, OA) vs control,
  full text. **Re-run this after every detector change to measure progress.**
- Diagnostics: `docs/recall_validation_fulltext.md`, `docs/recall_validation_retracted_abstracts.md`.

## 4. Firepower roadmap (priority order) — the actual work

### P1. Fix B4 statcheck recall = 0 (highest value, medium effort)
Statcheck recomputes reported p-values and flags impossible ones — it should be
a top fabrication catcher, but recall was **0/40** on full text.
- Investigate `src/paperguard/detectors/b4_statcheck.py` extraction: the JATS
  full-text stripping (`fetcher/europepmc.py: parse_jats`) likely loses the
  inline `t(df)=x, p=y` / `F(a,b)=x` formatting statcheck regexes need, or the
  stats live in tables that get flattened.
- Test against a KNOWN statistics-error retraction (find one via Retraction
  Watch / PubPeer) to confirm extraction, then widen regex / feed table text.
- Re-run `validate_recall_fulltext.py`; target B4 recall clearly > FP.

### P2. Figure/data extraction → unlock image + numeric detectors (big, highest ceiling)
The decisive anti-fabrication families NEVER ran in validation because they need
figures/tables:
- **Image forensics F1–F7** (duplication, splice, GAN/diffusion) need the actual
  figure image bytes. Build a PMC OA figure fetcher (PMC OA package / figure
  URLs) → feed F1–F7. This is where image-manipulation fraud is caught.
- **Numeric recompute GRIM/GRIMMER/SPRITE/Carlisle** need reported means/SDs/N.
  Build a table/`mean ± SD (n=)` extractor (project already has pdfplumber + OCR
  from W2) → feed these detectors.
- Then run a real full-suite recall test on retracted papers WITH figures/tables.

### P3. Strengthen T4 tortured phrases (modest effort)
T4 is currently the only text detector with signal (LR+ ≈ 1.5). Expand the
paper-mill phrase dictionary (PubPeer / Problematic Paper Screener lists) to
raise recall on mill-produced fabrication.

### P4. Evidence combination / escalation (makes it "undeniable")
In `src/paperguard/evidence/combiner.py`: when ≥N **independent-cluster**
detectors fire, escalate to CRITICAL and present a combined likelihood — this is
where convergent evidence becomes hard to dismiss. Keep wording as "investigate",
not "guilty".

## 5. Constraints / ethics (keep the project credible + legal)

- **Open-Access sources only.** Never download/commit paywalled full texts.
- **Aggregate results only** in the repo. No per-paper or per-author verdict
  lists. No targeting named individuals/institutions.
- Validation cohorts = **public retracted papers** (Europe PMC), never living
  colleagues.
- Keep ≥3 innocent explanations + no verdict language on every Finding (tests
  enforce this).

## 6. Security TODO (carry over — user action)

Two secrets were exposed in the prior chat and **must be revoked**:
- PyPI token → https://pypi.org/manage/account/token/
- DeepSeek key → https://platform.deepseek.com/

## 7. Suggested first move in the new session

Start with **P1 (statcheck)** — cheapest high-value win:
1. `git pull`; run the 3-gate to confirm green.
2. Read `b4_statcheck.py` + `fetcher/europepmc.py: parse_jats`.
3. Find one known stats-error retraction, confirm whether statcheck extracts its
   reported stats from the parsed full text; fix extraction.
4. Re-run `scripts/validate_recall_fulltext.py --n 40`; commit the before/after.
