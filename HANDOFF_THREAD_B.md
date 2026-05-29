# PaperGuard — Thread B (Coordinator) Handoff

> **Your role: coordinator / reviewer / shipper.** Thread A writes
> the heavy code. You read their PRs, run gates, audit privacy,
> tag, push, upload to PyPI, create GitHub releases, manage the
> JOSS / JORS submission state, refresh paper / docs, and keep
> the user informed.
>
> **You do NOT write large new features.** If a Thread-A task is
> stuck, request changes in PR comments. Do not start a parallel
> implementation in this thread.
>
> Read this in full before doing anything.

---

## 1. Why two threads

Earlier in this conversation we ran a single thread that did
everything: design + implementation + paper + JORS portal triage +
release ship. By 2.6.1 the session had accumulated ~$850 of API
cost and prompt-cache misses were getting expensive. The user split
the work:

| | Thread A | Thread B (you) |
|---|---|---|
| Heavy code | ✅ writes | ❌ reviews only |
| W1-W10 features | ✅ implements | ❌ does not |
| Plan C Colab notebook | ✅ writes | ❌ does not |
| 3-gate + privacy audit on PR | ✅ before opening PR | ✅ again before merge |
| Version bump + CHANGELOG | sometimes in PR | ✅ always verifies |
| Commit to main | ❌ uses feature branches | ✅ merges + tags |
| PyPI upload | ❌ | ✅ |
| GitHub release notes | ❌ | ✅ |
| JOSS / JORS portal state | ❌ | ✅ |
| paper/* refresh on ship | ❌ | ✅ when warranted |
| User Q&A / progress reports | ❌ (focused on task) | ✅ primary channel |
| HANDOFF.md continuity | ❌ | ✅ |

The split exists to: (a) keep this thread's token cost low so user
interaction stays cheap, (b) give Thread A the long focused
context budget it needs, (c) decouple "writing code" from
"shipping it" so reviews stay honest.

---

## 2. Project identity

| | |
|---|---|
| Name | PaperGuard |
| Author | Lei Zhou, ORCID `0009-0000-9073-1349` |
| Repo | https://github.com/exergyleizhou-ux/PaperGuard |
| Current version | **2.7.0** |
| Local path | `<project-root>/PaperGuard` — Lei substitutes his real Windows username / folder. |
| Python venv | `.venv/Scripts/python.exe` |
| Iron rule | No verdict language in detector output. See `HANDOFF_THREAD_A.md` § 1. |

---

## 3. Current state snapshot (2026-05-25, `878e916`)

- **545 tests** passing (3 deselected for network)
- ruff clean, mypy --strict clean on 104 source files
- privacy grep clean
- **40 detectors**, F7 latest (2.7.0)
- 13 published empirical-calibration studies
- PyPI: 2.7.0 live
- GitHub release: v2.7.0 published
- Docker GHCR: multi-arch built
- HF Space: live but showing 2.6.1 banner — sync needed next ship
- JOSS: rejected 2026-05-24 (6-month history rule)
- JORS: ready to submit, blocked on Lei's browser reCAPTCHA

---

## 4. Your day-to-day workflow

### When Thread A opens a PR

1. **Read the PR description.** It should link to spec section in
   `HANDOFF_THREAD_A.md` § 5 or § 6. If missing, ask for it.
2. **Check out the branch:**
   ```bash
   cd <project-root>/PaperGuard
   git fetch origin
   git checkout <branch-name>
   ```
3. **Read the diff.** Look for:
   - Iron-rule violations (forbidden words anywhere, even in
     negation context — the iron-rule test is a raw substring check)
   - Privacy-token leaks (the canonical banned-token regex lives in
     HANDOFF.md §5; do not inline it here)
   - Missing innocent_explanations (≥ 3 minimum; F/T-family ≥ 4)
   - Missing test coverage for new code paths
4. **Run 3-gate + privacy** — use the canonical block from
   HANDOFF.md §5 ("Reproducible 3-gate command"). It contains:
   - `__pycache__` cleanup
   - pytest / ruff / mypy
   - the privacy-token regex grep
   Do not paste the privacy regex literally into this file; refer
   out to HANDOFF.md to keep this brief grep-clean.
5. **Two outcomes:**
   - **All green + no findings** → approve, merge, ship.
   - **Anything red** → PR comments with specific lines. Don't
     push fixes yourself.

### After approving — the ship

If PR's version bump + CHANGELOG entry are present and correct:

```bash
git checkout main
git merge --no-ff <branch-name>
git push origin main

# Verify the bump
NEW=$(.venv/Scripts/python.exe -c "import paperguard; print(paperguard.__version__)")
echo "New version: $NEW"

git tag -a "v$NEW" -m "$NEW — <one-line summary>"
git push origin "v$NEW"

# Build + PyPI
rm -rf dist/ build/ *.egg-info src/*.egg-info
.venv/Scripts/python.exe -m build
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m twine upload \
  --username __token__ --password "$PYPI_TOKEN" "dist/paperguard-${NEW}*"

# Verify PyPI
curl -sS "https://pypi.org/pypi/paperguard/$NEW/json" | \
  python -c "import sys,json; d=json.load(sys.stdin); print('PyPI:', d['info']['version'])"

# GitHub release — copy CHANGELOG section as notes body
gh release create "v$NEW" --title "v$NEW — <title>" \
  --notes "$(awk "/## \[$NEW\]/,/^## \[/" CHANGELOG.md | sed '$d' | sed '$d')"
```

If version bump or CHANGELOG missing/wrong, request fix in PR
comments; don't merge.

### When Thread A asks a non-code question

Examples:
- "Should F8 default to NOTE or CONCERN?"
- "Should W7 cache PDFs forever or 30 days?"

You handle by **asking the user** (Lei) — short Yes/No or A/B/C
question. Don't decide for them.

---

## 5. What Thread B does without Thread A interaction

### 5.1 JORS / JOSS portal state
- JORS portal CAPTCHA blocker: walk Lei through next steps.
  Materials under `paper/`.
- JOSS re-invite (after 6 months): respond per
  `paper/JOSS_SUBMISSION.md`; offer to draft.

### 5.2 paper/* refresh after a ship

| Change | Refresh paper.md? |
|---|---|
| New detector (F7 etc.) | ✅ update count + table |
| Bug fix only | ❌ no |
| New empirical study | ✅ add to § 3 Quality control |
| Threshold re-tune | ✅ update calibration paragraph |
| CLI improvement | ❌ no |

After paper refresh, regenerate DOCX:

```bash
.venv/Scripts/python.exe -c "
import pypandoc
pypandoc.convert_file(
    'paper/paper_jors.md','docx',
    format='markdown+yaml_metadata_block',
    extra_args=[
        '--citeproc',
        '--bibliography=paper/paper.bib',
        '--metadata=link-citations:true',
        '--metadata=author:Lei Zhou (ORCID 0009-0000-9073-1349)',
        '--standalone',
    ],
    outputfile='paper/paper_jors.docx',
)"
```

Commit both files with message `paper(jors): refresh for version X.Y.Z`.

### 5.3 HF Space sync

Sync when a new detector ships or version bump is meaningful:

```bash
# Update examples/hf_space_app.py if banner text needs change, then:
"<project-root>/PaperGuard/.venv/Scripts/hf.exe" upload \
  exergyleizhou/paperguard-demo \
  "<project-root>/PaperGuard/examples/hf_space_app.py" \
  app.py --repo-type space \
  --commit-message "X.Y.Z sync: refresh banner"
```

Poll runtime stage = `RUNNING` via `hf.exe spaces logs`.

### 5.4 HANDOFF.md continuity

`HANDOFF.md` (4th-revision continuity doc) lives for fresh-session
handoffs not splitting between threads. Refresh when:
- Major release ships (2.7 → 2.8 → 3.0)
- W1-W10 backlog meaningfully shifts
- New strategic decision made (e.g. new venue beyond JORS)

The Thread-A/B briefs are **stable** — they describe the split
mechanism. Small updates only when the mechanism changes.

---

## 6. Communication with Thread A

Mirror of Thread A § 10:
- Thread A opens PRs to main on feature branches.
- You review on PR; merge + ship if green; request changes if not.
- One in-flight PR at a time. If Thread A opens a second, comment
  "waiting for previous PR to merge first" and pause.
- Long sync questions → `docs/notes_<topic>.md`.

---

## 7. Cost discipline

This thread tends to handle user questions ("目前进度?", "JORS 卡了"),
which are bursty. Each user reply costs $5-15 by the time you read
prompt + reply.

Stay cheap:
- Use TaskList / TaskGet instead of re-running git log
- Don't re-read large files — trust HANDOFF + prior context
- Defer big context reads to Thread A
- When user asks "what's next", point at `HANDOFF_THREAD_A.md` § 5

If your session cost exceeds **$300**, suggest a fresh Thread B
with `HANDOFF_THREAD_B.md` for continuity.

---

## 8. W1-W10 backlog state

| ID | Status | Shipped | Branch |
|---|---|---|---|
| W1 | ✅ merged | v2.13.0 (2026-05-25) | feat/w1-scan-name |
| W2 | ✅ merged | v2.14.0 (2026-05-25) | feat/w2-ocr-tables |
| W3 | ✅ merged | v2.9.0 (2026-05-25) | feat/w3-small-n-relaxed |
| W4 | ✅ merged | v2.15.0 (2026-05-25) | feat/w4-chinese-scholar |
| W5 | ✅ merged | v2.8.0 (2026-05-25) | feat/w5-pdf-auto-images |
| W6 | ✅ merged | v2.10.0 (2026-05-25) | feat/w6-statcheck-multidiscipline |
| W7 | ✅ merged | v2.12.0 (2026-05-25) | feat/w7-scan-author |
| W8 | ✅ merged | v2.7.1 (2026-05-25) | fix/w8-w9-cli-improvements (bundle) |
| W9 | ✅ merged | v2.7.1 (2026-05-25) | fix/w8-w9-cli-improvements (bundle) |
| W10 | ✅ merged | v2.11.0 (2026-05-25) | feat/w10-orcid-helper |

**Status: 10 / 10 closed.** Thread A completed the W-backlog in a
single intensive session, 9 PRs from 2.7.1 through 2.15.0. Test
count rose 545 → 609 (+64). PyPI 2.15.0 live; HF Space synced.

### W1-W10 ship log
- 2026-05-25 v2.7.1 — W8 (Windows GBK) + W9 (multi-file CLI) bundle
- 2026-05-25 v2.8.0 — W5 (PDF auto-image extraction for F1-F7)
- 2026-05-25 v2.9.0 — W3 (small-n graceful degradation: NOTE-cap at n ≥ 10)
- 2026-05-25 v2.10.0 — W6 (statcheck multi-discipline regex)
- 2026-05-25 v2.11.0 — W10 (ORCID public-API disambiguation helper)
- 2026-05-25 v2.12.0 — W7 (`paperguard scan-author <orcid>` CLI)
- 2026-05-25 v2.13.0 — W1 (`paperguard scan-name <name>` auto-fetch)
- 2026-05-25 v2.14.0 — W2 (OCR table extraction for scanned PDFs)
- 2026-05-25 v2.15.0 — W4 (Chinese / multilingual paper search via Semantic Scholar)

### Remaining big backlog
- **Plan C** — BERT Colab notebook (`notebooks/train_t9_bert_llm_detector.ipynb`).
  ✅ **Notebook delivered 2026-05-29 `710d1a7`** (spec = `HANDOFF_THREAD_A.md` §6).
  Self-contained, resumable, ships a drop-in `t9_distilbert.py` detector template.
  **Remaining (needs Lei's GPU):** run on free Colab T4 → download model to
  `~/.paperguard/models/t9/` → add the T9 detector → ship 3.0.0 (detector 41).

---

## 9. Other open items

| Item | Owner | Status |
|---|---|---|
| JORS portal registration (reCAPTCHA bug) | Lei | blocked on browser; backup = email Ubiquity Press |
| JORS submission (after unblock) | Lei | files ready under `paper/` |
| JOSS resubmission (after 6 months) | Lei | scheduled ~2026-11 |
| Scientific Data dataset paper | Lei | gated on first DOI |
| Sun Liping authorship scan | (paused) | iron-rule-compliant procedure documented; needs explicit user OK |

---

## 10. First-message template (paste when starting fresh Thread B)

> Read `HANDOFF_THREAD_B.md`. Current state: PaperGuard 2.7.0,
> 40 detectors, 545 tests, no open Thread-A PR yet. My role is
> coordinator / reviewer / shipper. Standing by for Thread A PRs
> or user instructions.
>
> User: anything urgent? Otherwise I'll wait for the first
> Thread A PR (expected: W8+W9 bundle as 2.7.1).

---

## 11. What this file is NOT

- Not the project README (`README.md`)
- Not the CHANGELOG (`CHANGELOG.md`)
- Not the long-form continuity doc (`HANDOFF.md`, 4th revision)
- Not the Thread A brief (`HANDOFF_THREAD_A.md`)
- **It is**: a coordinator's brief making this thread productive
  with minimal token cost.
