# JOSS submission walkthrough

This file is private guidance for submitting PaperGuard to the
[Journal of Open Source Software](https://joss.theoj.org/).
Not part of the published software, not part of the paper.

## Pre-flight checklist (all ✅ before opening the JOSS form)

- [x] **`paper/paper.md`** exists with correct YAML metadata
      (title, tags, authors, affiliations, date, bibliography).
- [x] **`paper/paper.bib`** contains every cited reference (11 entries — Landis 1977 added in 2.2.7).
- [x] **GitHub Action `draft-pdf.yml`** builds the PDF on every push
      to `paper/**`. After the next push, the `paper` artifact will
      be downloadable from the workflow run page.
- [x] **Repo is public** at https://github.com/exergyleizhou-ux/PaperGuard
- [x] **License (MIT)** is present and JOSS-compatible.
- [x] **Tests** exist and pass in CI (`ci.yml`).
- [x] **README** has install + quickstart instructions.
- [x] **Tag a release** for the version being submitted — for JOSS
      reviewers to download a specific snapshot. Currently `v2.2.7`
      is the latest tag.

## ORCID

JOSS requires authors to have an ORCID. The current `paper.md` uses
the placeholder `0000-0000-0000-0000`. **Before opening the form,
register or look up your real ORCID at https://orcid.org/register
and replace the placeholder.**

## Step-by-step submission

1. Open https://joss.theoj.org/papers/new (sign in with GitHub).
2. Fill the form:

| Field | Value |
|---|---|
| Repository URL | `https://github.com/exergyleizhou-ux/PaperGuard` |
| Branch | `main` |
| Version | `v2.2.7` |
| Title | (copy from paper.md `title:`) |
| Abstract (≤ 250 words) | Use the "Summary" section from paper.md, lightly trimmed |
| Software paper PDF | Will be auto-generated from `paper/paper.md` — no upload needed |

3. JOSS picks an editor; you'll get an email within 1-7 days.
4. The editor pre-checks (license, repo public, paper builds, etc.).
5. If pre-check passes, JOSS opens a public review issue on
   `openjournals/joss-reviews`. Two volunteer reviewers from
   PaperGuard's domain are assigned.
6. Reviewers post a checklist on the issue
   (https://joss.readthedocs.io/en/latest/review_checklist.html);
   you respond to each item by improving the code/docs and replying
   on the issue.
7. After both reviewers tick all boxes, the editor accepts and JOSS
   mints a DOI.

## Realistic timeline

- Pre-check: 1-7 days
- Reviewer assignment: 1-4 weeks
- Iterative review: 2-8 weeks (depends on responsiveness)
- Acceptance and DOI: 1-3 days after final reviewer approval

**Median time-to-publication for accepted JOSS papers: 6-12 weeks.**

## Common review checklist items (anticipate ahead)

1. **Statement of need is clear.** Our `paper.md` `# Statement of
   need` section addresses this.
2. **Installation instructions are simple and successful.**
   `pip install paperguard` works on Linux/Mac/Windows.
3. **Tests are automated.** `ci.yml` runs them on push.
4. **Documentation is sufficient for new users.**
   `docs/quickstart.md` plus README cover this.
5. **Examples exist.** `examples/01_scan_fabricated.py` through
   `04_full_pipeline_demo.py` are runnable.
6. **The software is a substantial scholarly contribution.**
   38 detectors + 13 empirical studies + 31 PyPI versions of
   iteration through 2.2.7 demonstrates this.
7. **The paper acknowledges related work.** Statement of need cites
   statcheck, GRIM, Carlisle, SPRITE, Bik, Kobak, Cabanac.

## What to do if a reviewer asks for something

| Request | Response |
|---|---|
| "Add a comparison vs existing tool X" | Add a table to `paper.md` or a short note; if X exists in Python, run X on the same v8/v9 corpus |
| "Test on macOS / Windows" | Already in CI |
| "Increase test coverage" | Already at 506 tests; reply with the number |
| "Add a tutorial" | `docs/quickstart.md` already exists; link it |
| "Add benchmarks" | 5 published empirical studies; link `docs/recall_test_v8.md` etc. |
| "Add type hints" | Already mypy --strict clean |
| "Acknowledge limitations" | Already done in `docs/llm_detection_v2.md` and `docs/t8_endpoint_limitation.md` |

## After acceptance

- Update README badge: replace status to "[JOSS](https://joss.theoj.org/papers/...)" 
- Add the JOSS DOI to `CITATION.cff`
- Tag a `v2.x.x` release marking the JOSS-published snapshot
- Tweet / Mastodon / WeChat moment the DOI

## What to do if rejected

JOSS rejects roughly 10-15 % of submissions, most often for:
- "Not a substantial scholarly contribution" — PaperGuard easily
  passes this (38 detectors across 8 families, 13 empirical studies,
  31 PyPI versions).
- "Documentation insufficient" — fix the specific item and re-submit.
- "Out of scope" — JOSS scope is broad; PaperGuard is squarely
  in scope (open-source research-software for the research community).

If a "not in scope" rejection comes, SoftwareX (Elsevier) or
F1000Research are good next targets with similar requirements.
