# PaperGuard 终极交接文档 v2.1.5

> **2026-05-20 — successor to the 2.0.14 handoff at the top of session "go 期 1-3"**
>
> Pasting this entire file into a fresh Claude Code session gives the next agent
> everything it needs to continue without context loss.

## 1. Project identity

| | |
|---|---|
| Name | **PaperGuard** — research-data integrity triage |
| Current version | **2.1.5** (local = origin = PyPI = release tag, all in sync) |
| Local root | `C:\Users\USER\Desktop\PROJECT_DIR\PaperGuard` |
| Python venv | `.venv/Scripts/python.exe` |
| CLI entry | `.venv/Scripts/paperguard.exe` |
| GitHub | https://github.com/exergyleizhou-ux/PaperGuard |
| PyPI | https://pypi.org/project/paperguard/ |
| HF Space (live) | https://huggingface.co/spaces/exergyleizhou/paperguard-demo |
| Detector count | **33 built-in** + plugin entry-point support |

## 2. Quality state (verified 2026-05-20)

```
PYTEST    372 passed (+ 3 deselected for network)
RUFF      All checks passed
MYPY      Success: 90 source files (--strict)
COMMITS   46 on main
TAGS      v2.0.1 → v2.1.5 (22 releases, no gap)
PRIVACY   ✅ grep [REDACTED-INST]|[REDACTED-NAME]|[REDACTED-DOI-1-PREFIX]|[REDACTED-DOI-2-PREFIX] → 0 hits
LOCAL=ORIGIN ✅ git status -s empty
```

## 3. Credentials (held by user, not in this file)

> Tokens are **not** committed to the repo. The user has them on hand
> and pastes them when needed. Placeholders below.

```
PYPI_TOKEN     = [PYPI_TOKEN — full-account scope, ask user]
HF_TOKEN       = [HF_TOKEN — see private session credentials]
TEAM_LLM_BASE  = https://cliproxy.eqing.tech/v1
TEAM_LLM_KEY   = [TEAM_LLM_KEY — see private session credentials]
TEAM_LLM_MODEL = gpt-5.4-mini   (cliproxy's standard model)
GIT_LOCAL_USER = exergyleizhou-ux
GIT_LOCAL_EMAIL = exergyleizhou@gmail.com
GH_AUTH        = authenticated (token in Windows Credential Manager)
HF_USER        = exergyleizhou
```

⚠️ **cliproxy quirk** — does NOT return `logprobs` field. Set
`PAPERGUARD_LLM_NO_JSON_MODE=1`. T7 / T8 cannot do live LR+ measurement
on this endpoint; they unit-test fine but return NOTE-level inconclusive
on real text. **Move to a GPT-4o-class endpoint with token logprobs for
live T7/T8 LR+.**

⚠️ **PyPI token has full-account scope** and was exposed in this session
window across multiple messages. User explicitly **declined** to revoke
("那个安全操作别让我做了 你继续做"). New session should use it sparingly.

## 4. What was shipped in the 2.0.14 → 2.1.5 cycle (this session)

| Ver | Date | What |
|---|---|---|
| 2.0.15 | 2026-05-20 | T6 dynamic dictionary + T7 perplexity proxy detector (32 detectors) |
| 2.0.16 | 2026-05-20 | T8 DetectGPT detector (33) + dictionary JSON + batch/notify `--*-check` flags + v8 N=50 |
| 2.0.17 | 2026-05-20 | HF Space Gradio demo (`examples/hf_space_app.py`) |
| 2.1.0 | 2026-05-20 | v9 N=30 retest + transparent T7/T8 dataset |
| 2.1.1 | 2026-05-20 | `docs/paperguard_technical_report.md` (7-section technical report) |
| 2.1.2 | 2026-05-20 | Image-layer F1/F4 recall (`recall_image_v1`) + JOSS paper draft + T6 abstract-only mode |
| 2.1.3 | 2026-05-20 | B4 statcheck cross-validation + HF Space deployed (live) |
| 2.1.4 | 2026-05-20 | README + ROADMAP refresh |
| 2.1.5 | 2026-05-20 | README.zh.md sync + this HANDOFF doc |

## 5. Reproducible 3-gate command

```bash
cd "C:/Users/USER/Desktop/PROJECT_DIR/PaperGuard"
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -m "not network" -q
.venv/Scripts/python.exe -m ruff check src/ tests/ examples/
.venv/Scripts/python.exe -m mypy src/
```

Privacy gate (must be clean before every release):
```bash
find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} +
grep -rlnE "[REDACTED-INST]|[REDACTED-CODENAME-1]|[REDACTED-CODENAME-2]|USER|PROJECT_DIR|[REDACTED-NAME]|[REDACTED-NAME-EN]|[REDACTED-DOI-1-PREFIX]|[REDACTED-DOI-2-PREFIX]" \
  src/ tests/ examples/ docs/ scripts/ README.md README.zh.md \
  CHANGELOG.md ROADMAP.md CONTRIBUTING.md SECURITY.md LICENSE \
  CITATION.cff pyproject.toml HANDOFF.md
```
Expected empty.

## 6. The 33 detectors (verified count, 2.1.5)

| ID | Name | Source |
|---|---|---|
| A1-A7 | Digit-distribution + arithmetic + bounds | a*.py |
| B1, B4-B8 | GRIM / statcheck / TIVA / GRIMMER / p-curve / SPRITE | b*.py |
| C1 | Carlisle baseline | c1_carlisle.py |
| D1, D2 | Residual smoothness / Missing pattern | d*.py |
| E1 | ICC Independence (new in 2.0.14) | e1_icc_independence.py |
| F1-F5 | Image forensics | f*.py |
| G1, G3, G4 | EXIF / docx rsid / file metadata | g*.py |
| M1 | Paper-mill graph | m1_paper_mill_graph.py |
| T1-T8 | Text + LLM family | t*.py |

**LLM-text family (T6/T7/T8) is the major addition this cycle:**
- T6: lexical phrase signature + dynamic user dictionary at `~/.paperguard/ai_dictionary.json`
- T7: continuation-perplexity proxy (needs logprobs-capable endpoint)
- T8: DetectGPT-style curvature via paraphrase + LM scoring

## 7. Empirical datasets in the repo

| File | What | LR+ result |
|---|---|---|
| `scripts/recall_test_v8_results.json` | N=50+50 OpenAlex retracted/control, PMC text, T6 only | T6 LR+ ≈ 0 at default threshold |
| `scripts/recall_test_v9_results.json` | N=30+30 retest, T6 columns filled + T7/T8 slots open | (T7/T8 await real GPT-4o key) |
| `scripts/recall_image_v1_results.json` | N=15+15 image corpus, F1/F4 | see `docs/recall_image_v1.md` |
| `scripts/crossval_statcheck_results.json` | N=41 ground-truth, B4 vs scipy ref | recall 100%, decision-flip 94% |
| `scripts/recall_test_v5_results.json` (legacy) | Full-pipeline N=100+100 | see `docs/recall_test_v5.md` |

## 8. Open work (priority order for next session)

### 8.A — Real GPT-4o T7/T8 LR+ (blocked on credentials)

The most-valuable single thing left undone. When the user provides a
real OpenAI key (sk-…), run:

```bash
cd "C:/Users/USER/Desktop/PROJECT_DIR/PaperGuard"
OPENAI_API_KEY="sk-REAL" \
PAPERGUARD_LLM_MODEL="gpt-4o-mini" \
PYTHONIOENCODING=utf-8 \
.venv/Scripts/python.exe scripts/recall_test_v9.py \
    --n 30 --year-min 2020 \
    --run-t7 --run-t8 \
    --out scripts/recall_test_v9_results.json \
    --resume
.venv/Scripts/python.exe scripts/recall_analyze_v9.py \
    scripts/recall_test_v9_results.json > docs/recall_test_v9_with_t7t8.md
```

The v9 script already has `--run-t7 --run-t8 --resume` wired and only
populates the empty `t7_*` / `t8_*` columns in the JSON — T6 work is
preserved. Cost estimate: ~200 OpenAI API calls, < $0.50 on `gpt-4o-mini`.

### 8.B — JOSS submission

`paper/paper.md` + `paper/paper.bib` are ready. To actually submit:
1. `.github/workflows/draft-pdf.yml` already exists — it builds the
   JOSS PDF on every push. Verify it runs.
2. Open issue at https://github.com/openjournals/joss-reviews
3. Submit via https://joss.theoj.org/papers/new with the GitHub repo URL.

### 8.C — F1/F4 N=50+50 expansion

Image recall study is currently N=15+15. To get tight CI, expand:
1. `python scripts/recall_image_v1.py --n 50 --resume`
2. The script is idempotent and will skip records already in the
   `.partial.json`.

### 8.D — statcheck-R Cohen's κ

When R is available in CI:
```r
install.packages("statcheck")
library(statcheck)
results <- statcheck("crossval_corpus.txt")
```
Then compute κ between B4 output and statcheck-R output on the same
N=41 corpus. Expected κ > 0.85.

### 8.E — Bik splice/wash detection at patch level

F3 currently does block-statistic splice detection. Bik 2016 used
per-channel histogram analysis at the **patch** level — finer grain.
A new detector `F6` could implement this. ~1-2 days of work.

### 8.F — Multi-tenant Web UI production hardening

`src/paperguard/webui/` exists and works in dev. Production needs:
- Redis cache backend (currently in-memory)
- HTTPS termination guidance in deploy docs
- Rate-limiting on `/scan` endpoint
- Audit-log shipping (currently file-based)

## 9. Tripwire / gotchas (encountered in this session)

| # | Trap | Workaround |
|---|---|---|
| 1 | Windows `__pycache__` has compile-time absolute paths → grep "USER" false-positive | `find . -name __pycache__ -exec rm -rf {} +` before every privacy grep |
| 2 | `paperguard.exe` Chinese output garbled in PowerShell GBK | `$env:PYTHONIOENCODING="utf-8"` |
| 3 | git LF/CRLF warning on every commit | Normal Windows behavior, **leave alone** |
| 4 | diskcache cross-test contamination | Test decorator: unique `uuid.uuid4().hex` namespace |
| 5 | networkx/opencv/pymupdf/biopython have no stubs | `# type: ignore[import-untyped]` (not `[no-untyped-call]`) |
| 6 | Pydantic mypy plugin | `pyproject.toml` has `plugins = ["pydantic.mypy"]` — don't remove |
| 7 | D1 monotonic-index false positive | Detector has a monotonic-skip rule — don't remove |
| 8 | G4 publisher allowlist | Springer/Elsevier/Wiley/LaTeX 30+ entries pre-whitelisted |
| 9 | PDF image size filter | F1/F2/F3 inputs must pass `extract_pdf_images` (≥200×200, ≥8KB) |
| 10 | subprocess Unicode on Windows | Use `text=False` + manual `utf-8` decode |
| 11 | F1 raster fallback slow on long PDFs | Default `raster_max_pages=5`, timeout 600s — don't bump |
| 12 | twine upload progress bar crashes on GBK | `PYTHONIOENCODING=utf-8` before upload |
| 13 | cliproxy doesn't return logprobs | T7 returns NOTE inconclusive; need real OpenAI key |
| 14 | cliproxy paraphraser preserves LLM markers | T8 z-score collapses; same fix as above |

## 10. User behaviour pattern

**User says "go / 做 / 全做 / 继续"** = green light, **only batch action then**.

**User says "目前进度 / 现在呢"** = **green-light count exhausted**. Each
such question burns a tool call. Strategy: 1-2 Bash calls max, then
**explicitly tell user "离开键盘 X 分钟"**.

**User is in China (10.205.x.x)**: GitHub / OpenAlex / Europe PMC /
Unpaywall / PyPI all work, occasional TLS jitter (`fetch()` has 3 retries).
HuggingFace works. cliproxy works.

**User occasionally pastes sensitive info**: Gmail passwords / tokens
have appeared. Warn but don't leak. The PYPI_TOKEN above has full account
scope and was exposed many times this session — the user knows.

## 11. Privacy iron rule (violation = serious)

PaperGuard output **never** uses "fraud / 造假 / misconduct / cheating /
学术不端". Every Finding must have ≥3 `innocent_explanations` (4 for T7).
[redacted-institution] papers / [REDACTED-NAME] / DOI [REDACTED-DOI-1] / [REDACTED-DOI-2] must
**never** appear in any repo file. Verification command in §5.

## 12. Standard ship workflow

When a feature/fix is ready:
1. **3-gate** (§5) — all green
2. **Privacy grep** — clean
3. Bump version in `pyproject.toml` + `src/paperguard/__init__.py` + `CITATION.cff`
4. Add CHANGELOG entry above the previous version's `## [...]` heading
5. `git add ...` (specific files, **not** `git add -A`)
6. `git commit -m "X.Y.Z — summary" -m "details + Co-Authored-By"`
7. `git tag -a vX.Y.Z -m "..."`
8. `git push origin main && git push origin vX.Y.Z`
9. `rm -rf dist/ build/ *.egg-info && python -m build`
10. `PYTHONIOENCODING=utf-8 twine upload --username __token__ --password <PYPI_TOKEN> dist/paperguard-X.Y.Z*`
11. `gh release create vX.Y.Z --title "..." --notes "..."`

## 13. First message in next session

After pasting this file, the agent's first reply should be:

> Read the 2.1.5 handoff doc. Current state: 372 tests / 33 detectors /
> 2.0.15 → 2.1.5 all shipped / local = origin = PyPI = tag synced /
> HF Space live.
>
> Open priority work: **8.A real GPT-4o T7/T8 LR+** (one command if you
> give me a real OpenAI key). Other directions: 8.B JOSS submission, 8.C
> F1/F4 expansion, 8.D statcheck-R κ, 8.E F6 patch splice, 8.F multi-tenant
> Web UI prod hardening.
>
> Tell me which.

Then wait for user direction.

---

**Doc end.** Paste this entire file in next session to maintain continuity.
