# PaperGuard — Thread A (Builder) Handoff

> **Your role: heavy-lifting implementer.** You write new detectors,
> new features, big refactors, Plan C Colab notebook, the W1-W10
> field-test fixes. You commit to feature branches and open PRs;
> Thread B reviews, integrates, and ships.
>
> **Read this entire file before doing anything.** It is self-
> contained — a fresh Claude / human session can pick up and be
> productive without prior conversation context.

---

## 1. Project identity (immutable)

| | |
|---|---|
| Name | **PaperGuard** — research-data integrity triage tool |
| Author | Lei Zhou, ORCID `0009-0000-9073-1349`, independent, US |
| Repo | https://github.com/exergyleizhou-ux/PaperGuard |
| Current version (as of handoff) | **2.7.0** (PyPI live, GHA Docker built) |
| Local path | `<project-root>/PaperGuard` (Windows, GBK shell). Lei keeps the working copy at `C:\Users\USER\Desktop\PROJECT\PaperGuard` — substitute his real username / folder name when pasted into a shell. |
| Python venv | `.venv/Scripts/python.exe` (Python 3.12) |
| CLI entry | `.venv/Scripts/paperguard.exe` |
| License | MIT |
| Iron rule | **No verdict language** in any detector output. Every `Finding` must ship ≥ 3 `innocent_explanations`. Forbidden words: `fraud`, `fabrication`, `misconduct`, `造假`, `学术不端`. Enforced by CI grep. |

---

## 2. Current state (verified `878e916`, 2026-05-25)

```
PYTEST    545 passed (+ 3 deselected for network)
RUFF      All checks passed
MYPY      Success: 104 source files (--strict)
PRIVACY   ✅ clean (no banned tokens in tracked source)
TAGS      v2.0.1 → v2.7.0 (47 releases, no gap)
DETECTORS 40 built-in
EMPIRICAL 13 published studies under scripts/ + docs/
HF SPACE  RUNNING — gradio 5.34, py 3.11, banner displays v2.6.1 (sync needed for 2.7.0)
DOCKER    ghcr.io/exergyleizhou-ux/paperguard:latest (multi-arch)
```

### 40 detectors current roster

| ID | Family | What it does |
|---|---|---|
| A1, A2, A7 | Digit distribution | terminal-digit χ², Benford, last-digit 0/5 |
| A3, A5, A6 | Arithmetic/bounds | inter-column arithmetic, decimal consistency, plausible ranges |
| B1, B4-B8 | Statistical recompute | GRIM, statcheck, TIVA, GRIMMER, p-curve, SPRITE |
| C1 | Clinical trial | Carlisle baseline imbalance |
| D1, D2, E1 | Variance/independence | residual smoothness, missing-data, ICC |
| F1-F5 | Image forensics | pHash, ORB, splice, cross-paper, EXIF cluster |
| F6 | Image forensics | per-channel patch splice (Bik 2016 style) |
| **F7** | **Image forensics (new in 2.7.0)** | **GAN ridge + diffusion residual spectral signatures** |
| G1, G3, G4, G5 | Metadata | EXIF temporal, docx rsid, file metadata, reagent-year temporal |
| I1, I2, I5, I6 | Industrial | mass-balance, SCADA timestamp, batch-repetition, trend over-smoothness |
| M1 | Paper-mill | co-authorship graph |
| T1-T8 | Text/LLM | plagiarism, NCT, data avail, tortured phrases, stylometry, T6 lexical, T7 perplexity, T8 DetectGPT |

### Recent ship history (this session)

| Version | Date | What |
|---|---|---|
| 2.2.7 | 2026-05-22 | Honest scope statement for T7/T8 |
| 2.3.0 | 2026-05-23 | Web UI hardening |
| 2.3.1 | 2026-05-23 | Image recall v5 honest revision |
| 2.4.0 | 2026-05-23 | G5 reagent-temporal detector + first real-OpenAI T7/T8 LR+ |
| 2.4.1 | 2026-05-23 | T7 on gpt-4o LR+ = 8.0 inverted |
| 2.4.2 | 2026-05-23 | T7 inverted-threshold env var |
| 2.5.0 | 2026-05-23 | Audit log v1 |
| 2.5.1 | 2026-05-23 | 4-model T7 OpenAI study |
| 2.6.0 | 2026-05-23 | T7 endpoint-based auto-detect |
| 2.6.1 | 2026-05-23 | Image recall v6 (N=212) |
| **2.7.0** | **2026-05-25** | **F7 GAN/diffusion detector (40th detector)** |

---

## 3. JOSS rejection + JORS pivot (in-flight)

### What happened
- 2026-05-23: submitted to JOSS (issue #10600).
- 2026-05-24: JOSS editor Daniel S. Katz returned at pre-check — project lacks the JOSS-mandatory 6-month public-development history; suggested sister venue JORS.
- JOSS-version `paper/paper.md` (1307 words) is preserved for 2026-11+ resubmission.

### JORS submission package (ready)
| File | Status |
|---|---|
| `paper/paper_jors.md` (JORS 5-section, 3231 words) | ✅ |
| `paper/paper_jors.docx` | ✅ |
| `paper/paper.bib` (11 citations) | ✅ |
| `paper/jors_cover_letter.md` + `.docx` | ✅ |
| `paper/jors_recommended_reviewers.md` + `.docx` (Nuijten / Brown / Heathers / Bik / Kobak primary + 7 alternates) | ✅ |
| `paper/jors_submission_checklist.md` | ✅ 10-step portal walkthrough |

### Current blocker
- JORS portal registration: reCAPTCHA widget does not render in Lei's browser (network/extension filter). Backup: email `journals@ubiquitypress.com`.

---

## 4. The W1-W10 field-test weaknesses (your main backlog)

A sibling sub-thread ran a real-world authorship audit and produced
two reports. They may or may not yet be committed:

- `docs/field_test_zafu_2026.md` — narrative search log
- `docs/field_test_weaknesses_v1.md` — W1-W10 priority list

> **If those files are missing from your checkout** check
> `git status` for untracked `field_test*`. If absent, this section
> is your reliable source.

### Summary of the ten weaknesses

#### P0 (fatal — blocks the whole workflow)

**W1. No automatic paper-acquisition pipeline.**
User has to manually search and download every paper. Existing
fetchers cover only a fraction of OA biomedical content. No
`paperguard scan-author <name>` mode.

**W2. PDF table extraction unreliable.**
Most journals embed data tables as bitmap images. `pdfplumber`
cannot extract them. A1-A7 / B1 see no data on those papers.

#### P1 (high impact)

**W3. n ≥ 50 minimum-sample threshold misses summary tables.**
A1 / A2 / A7 / B5 / B7 skip papers whose data tables have 3-15 rows
— the most common form in published papers.

**W4. Zero Chinese-language scholarly database integration.**
CNKI / Wanfang / VIP not connected.

**W5. PDF scan does not auto-extract embedded images.**
F1-F7 skipped when scanning a PDF because no image paths are passed.

#### P2 (mid impact)

**W6. statcheck B4 only recognises psychology-format reporting.**
Chemistry / materials / ecology / biology notation slips through.

**W7. No batch author-level audit.**
Cannot scan all of one author's papers + cross-paper F4 + M1 in one call.

**W10. No author disambiguation.**
"Sun Liping" returns three different people; no ORCID-based pin.

#### P3 (small)

**W8. Windows GBK shell breaks PaperGuard output.**
`UnicodeEncodeError` on Chinese in CLI output.

**W9. CLI does not accept multiple files.**
`paperguard scan a.pdf b.pdf` errors.

---

## 5. Big-task implementation specs

These are the tasks Thread A executes. **Each task = one feature
branch + one PR + one Thread-B review cycle.**

### 5.W8 — Windows GBK fix (start here, ~30 min)

**Branch:** `fix/w8-windows-gbk`
**Files:** `src/paperguard/cli.py`
**Spec:**
- In `cli.py` top-level, call `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` and same for `sys.stderr` if `sys.platform == "win32"`.
- Add `os.environ.setdefault("PYTHONIOENCODING", "utf-8")` as belt-and-suspenders.
- Test in `tests/test_cli_extras.py` that monkeypatches platform = `win32`.
- ~10 lines code + 1 test. **Bundle with W9** → ship as 2.7.1.

### 5.W9 — Multi-file CLI (~1 hour)

**Branch:** `feat/w9-multi-file-cli`
**Files:** `src/paperguard/cli.py`
**Spec:**
- Change `scan` command's `file` argument to `nargs=-1`.
- Loop over each file, scan independently, accumulate `AuditReport` objects, emit combined HTML/JSON.
- Single-file case backward-compatible (cross-file summary suppressed when n_files == 1).
- Test in `tests/test_cli_extras.py::test_scan_multiple_files`.
- **Bundle with W8** → ship as 2.7.1.

### 5.W5 — Auto-extract images from PDF (~2-3 hours)

**Branch:** `feat/w5-pdf-auto-images`
**Files:** `cli.py`, `extractor/images.py`, `scanner.py`
**Spec:**
- When `paperguard scan paper.pdf` runs, auto-call `extract_pdf_images`, pass to F1-F7.
- Per-scan `tempfile.mkdtemp(prefix="pg_images_")`; cleanup in try/finally.
- Add `--no-image-extract` flag.
- Tests: scan fixture PDF with images, assert F1/F4/F6 results present.
- Ship as **2.8.0**.

### 5.W3 — Small-n graceful degradation (~2 hours)

**Branch:** `feat/w3-small-n-relaxed`
**Files:** `a1_terminal_digit.py`, `a2_benford.py`, `a7_last_digit_five_zero.py`, `b5_tiva.py`, `b7_pcurve.py`
**Spec:**
- Currently these return `applicable=False` when n < 50.
- New: still run test for 10 ≤ n < 50, cap severity at NOTE, add `low_power_note=True` to evidence.
- For n < 10, keep existing skip behaviour.
- Tests: n=15 produces NOTE-tier Finding.
- Ship as **2.9.0**.

### 5.W6 — statcheck multi-discipline format support (~3 hours)

**Branch:** `feat/w6-statcheck-multidiscipline`
**Files:** `b4_statcheck.py`
**Spec:**
- Add regex variants for chemistry (`r² = 0.X, n = N`), ecology (`χ² = X, df = N, p = Y`), materials (`R² = 0.XX`), biology (`t(df)=X, P<Y` capital P).
- One Finding per match.
- Fixture papers in `tests/fixtures/b4_multidiscipline/`.
- Ship as **2.10.0**.

### 5.W10 — ORCID disambiguation helper (~2 hours)

**Branch:** `feat/w10-orcid-helper`
**New module:** `src/paperguard/fetcher/orcid.py`
**Spec:**
- `disambiguate_author(name, affiliation=None) -> list[OrcidCandidate]` using public ORCID search API (no auth).
- CLI: `paperguard who <name> --affiliation X` prints a table.
- Mocked tests.
- Ship as **2.11.0**.

### 5.W7 — Batch author audit (~1 day)

**Branch:** `feat/w7-batch-author-audit`
**New CLI:** `paperguard scan-author <orcid_id>`
**Spec:**
- Reads ORCID's works via OpenAlex `author.orcid:...` filter.
- Per work with OA PDF, run full pipeline (reuse `_scan_single_file`).
- Aggregate findings + cross-paper F4 map + M1 graph signature.
- HTML per-author dashboard.
- End-to-end test with small ORCID corpus.
- Ship as **2.12.0** or **3.0.0** (combined scope decision).

### 5.W2 — OCR table extraction (~1-2 days)

**Branch:** `feat/w2-pdf-ocr-tables`
**New module:** `src/paperguard/extractor/pdf_ocr_tables.py`
**Spec:**
- `pytesseract` (cleaner) or `easyocr` (pure Python, larger dep) — pick one, document trade-off.
- Fallback only when `pdfplumber` returns < 3 text blocks on > 50%-image page.
- Tests with fixture image-only PDF.
- Add as `paperguard[ocr]` extras.
- Ship as **3.0.0**.

### 5.W1 — Author auto-fetch (~1 day, depends on W10 + W7)

**Branch:** `feat/w1-auto-fetch`
**Spec:**
- `paperguard scan-author` runs W10 disambiguation if input is a name.
- Add publisher-specific PDF fetchers (1 req/sec rate limit): arXiv (easy), PMC (done), Springer (with token, opt-in), Wiley/Elsevier (skip with "needs subscription" note).
- Cache fetched PDFs in `~/.paperguard/cache/pdfs/` keyed by DOI.
- HTTP-mocked tests.
- Ship as **3.0.0** (combined with W2).

### 5.W4 — Chinese database integration (lower priority, 1-2 weeks)

**Branch:** `feat/w4-chinese-databases`
**Notes:**
- **Do NOT scrape CNKI.** No public API + ToS risk.
- Wanfang paid API: skip unless user provides credentials.
- Realistic plan: OpenAlex Chinese-language filter + Europe PMC Chinese-author filter + clear "CNKI out of scope" docs.
- Ship as **3.1.0**.

---

## 6. Plan C — BERT Colab notebook (separate big task)

> **STATUS (2026-05-29 `710d1a7`): notebook DELIVERED.** The spec below was
> implemented as `notebooks/train_t9_bert_llm_detector.ipynb` (resumable,
> prints accuracy + LR+, exports to `~/.paperguard/models/t9/`, and embeds a
> drop-in `t9_distilbert.py` template). What remains is *running* it on Colab
> T4 and shipping the trained detector as 3.0.0 — see "After model lands".

> The user (Lei) registered Google Colab. Plan C is to train a
> small BERT-family LLM-text classifier on free Colab GPU.

**Deliverable:** `notebooks/train_t9_bert_llm_detector.ipynb`

**Notebook structure:**
1. Setup: `!pip install transformers datasets torch accelerate`
2. Mount Google Drive
3. Load HC3 dataset (`datasets.load_dataset("Hello-SimpleAI/HC3", "all")`)
4. DistilBERT-base-uncased tokenizer + 2-class classifier
5. Trainer; eval on held-out split; target 4-8 hours T4 GPU
6. Export `t9_model.pt` and `t9_tokenizer/` to Drive
7. Download instructions to `~/.paperguard/models/t9/`

**After model lands:**
- New `src/paperguard/detectors/t9_distilbert.py` loads lazily on first detect().
- Ship as **3.0.0** (combined with W2/W1) or as `3.0.0-rc1`.
- Detector count → 41.

**Notes for the notebook:**
- Cell 1: comment explaining Runtime → Change runtime → T4 GPU → Run all.
- Resumable — checkpoint to Drive every epoch; next run `from_pretrained(checkpoint_dir)`.
- Final cell prints accuracy + LR+ at SUSPICIOUS threshold; aim ≥ 0.85.

---

## 7. Ship workflow (run after every feature)

```bash
cd <project-root>/PaperGuard

# 3-gate
find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -m "not network" -q
.venv/Scripts/python.exe -m ruff check src/ tests/ examples/
.venv/Scripts/python.exe -m mypy src/

# privacy — see HANDOFF.md §5 for the canonical regex of banned tokens.
# Do not paste the regex literally into Thread-A docs; reference the script:
find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null
bash scripts/privacy_grep.sh   # if present; otherwise see HANDOFF.md §5
# expect zero matches

# bump version: pyproject.toml + src/paperguard/__init__.py + CITATION.cff
# add CHANGELOG entry above the previous version's ## heading

git add <specific files>
git commit -m "X.Y.Z — summary"
git tag -a vX.Y.Z -m "..."
git push origin main && git push origin vX.Y.Z

# build + PyPI
rm -rf dist/ build/ *.egg-info src/*.egg-info
.venv/Scripts/python.exe -m build
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m twine upload \
  --username __token__ --password $PYPI_TOKEN dist/paperguard-X.Y.Z*

# GitHub release
gh release create vX.Y.Z --title "..." --notes "..."
```

**Tag-push triggers GHA Docker build** to `ghcr.io/exergyleizhou-ux/paperguard:latest`.

---

## 8. Tripwires (do not repeat)

| # | Tripwire | Workaround |
|---|---|---|
| 1 | Windows `__pycache__` compile-time paths → privacy grep false-positive | `find . -name __pycache__ -exec rm -rf {} +` before every grep |
| 2 | Chinese CLI output GBK garbled | `$env:PYTHONIOENCODING="utf-8"` |
| 3 | git LF/CRLF warning | Normal Windows; leave alone |
| 4 | diskcache cross-test contamination | uuid namespaces |
| 5 | networkx/opencv/pymupdf no stubs | `# type: ignore[import-untyped]` — but mypy 1.18+ may flag the ignore as **unused** (recent F7 hit this); remove the ignore if mypy complains |
| 6 | Pydantic mypy plugin | Don't remove `pyproject.toml` `plugins = ["pydantic.mypy"]` |
| 7 | D1 monotonic-index false positive | Skip rule in D1 — don't remove |
| 8 | G4 publisher allowlist | 30+ pre-whitelisted; don't reset |
| 9 | F1-F3 image size filter | ≥ 200×200 and ≥ 8 KB |
| 10 | subprocess Unicode on Windows | `text=False` + manual utf-8 decode |
| 11 | F1 raster fallback slow on long PDFs | `raster_max_pages=5`, timeout 600s |
| 12 | twine upload progress bar GBK crash | `PYTHONIOENCODING=utf-8` |
| 13 | cliproxy team-pool: no logprobs | T7 blocked there; use api.openai.com |
| 14 | DeepSeek-v4 / Qwen3-32B are reasoning models | `max_tokens ≥ 256` for T7; ≥ 500 score + ≥ 1500 paraphrase for T8. DeepSeek logprobs are fake all-zeros. T8 LR+ collapses on reasoning paraphrasers. |
| 15 | GitHub secret-scanning push protection | Never commit real tokens. HANDOFF placeholders only. |
| 16 | HF Space Py 3.13 default broke gradio 4.44 | Pin `python_version: "3.11"` + `sdk_version: 5.34.0` in Space README |
| 17 | Iron-rule grep audit forbids forbidden words even in negation context | Rephrase ("appropriate and disclosed use" not "is not fraud"). |
| 18 | OpenAI reasoning models reject logprobs | o1/o3-mini/o4-mini all HTTP 400. |
| 19 | OpenAI gpt-3.5/gpt-4/gpt-4o family has INVERTED T7 direction | Auto-detected since 2.6.0; `PAPERGUARD_T7_INVERT_THRESHOLD=1` env var also overrides. |
| 20 | Detector count assertion in tests/test_plugin_registry.py | Every new detector must bump the constant 40 → 41 → ... |

---

## 9. Credentials (placeholders — Lei has the real values)

```
PYPI_TOKEN     = pypi-AgEI...    (full-account scope; Lei pastes)
OPENAI_API_KEY = sk-proj-...     (real api.openai.com; ~$0.10 used)
GROQ_KEY       = gsk_...         (free-tier; only qwen3-32b has logprobs)
HF_TOKEN       = hf_...          (HuggingFace Space deploy)
CLIPROXY_KEY   = sk-...          (team-pool; reasoning-only, no logprobs)
GIT_USER       = exergyleizhou-ux
EMAIL          = exergyleizhou@gmail.com
ORCID          = 0009-0000-9073-1349
```

**Never commit any real token.** GitHub's secret-scanning blocks
pushes with known token prefixes.

---

## 10. Communication with Thread B

Thread B is **coordinator / reviewer / shipper**. Workflow:

1. **Thread A picks a task** from §5 or §6.
2. **Create feature branch** (`fix/w8-windows-gbk` etc.); commit
   incrementally.
3. **Run 3-gate locally** before opening PR.
4. **Open PR to main** with:
   - Title: `feat(WX): <one-line summary>`
   - Body: links to spec section in this file, tests added, pytest screenshot.
5. **Thread B reviews:** reads diff, runs full 3-gate + privacy
   grep on branch, either approves+merges+ships or requests changes.
6. **After ship, Thread A picks next task.**

**Sync points where Thread A should NOT proceed:**
- Before opening a PR while another PR is open. Thread B serialises
  reviews; parallel PRs cause `CHANGELOG.md` merge-conflict thrash.
- When Thread B requests blocking changes.

**Communication channel:** PR comments. Long discussions →
`docs/notes_<topic>.md`.

---

## 11. First-message template (paste this when starting Thread A)

> Read `HANDOFF_THREAD_A.md`. Current state: PaperGuard 2.7.0,
> 40 detectors, 545 tests, F7 just shipped. My role is heavy-lift
> implementer. Next task on the backlog is **W8 + W9** (Windows GBK
> + multi-file CLI, bundled as 2.7.1). I will create branch
> `fix/w8-w9-cli-improvements`, implement per spec §5.W8 + §5.W9,
> run 3-gate, open PR to main, and ping Thread B.
>
> Anything else I should know before starting?

---

## 12. What this file is NOT

- Not the project README — `README.md` is user-facing
- Not the CHANGELOG — `CHANGELOG.md` has every release
- Not the academic paper — `paper/paper_jors.md` is for JORS
- Not the field-test report — `docs/field_test_*.md` is separate
- **It is**: a builder's brief making Thread A productive without prior conversation history.
