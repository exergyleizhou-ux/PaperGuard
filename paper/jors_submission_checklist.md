# JORS submission portal — field-by-field checklist

Walk this top to bottom while filling
[https://openresearchsoftware.metajnl.com/about/submissions](https://openresearchsoftware.metajnl.com/about/submissions).
Copy-paste blocks below into the matching portal field.

---

## Portal step 1 — Section / Type

| Portal field | Value |
|---|---|
| **Submission section** | `Software Metapapers` |
| **Submission type** | New submission |
| **Language** | English |

---

## Portal step 2 — Submission requirements (checkboxes)

Tick all that apply:

- [x] The submission has not been previously published, nor is it
      before another journal for consideration. (✅ true — the prior
      JOSS submission was returned at pre-check on scope grounds,
      not peer review; this is acknowledged in the cover letter.)
- [x] The submission file is in DOCX, OpenOffice, or PDF format.
      (✅ `paper_jors.docx`)
- [x] Where available, URLs for the references have been provided.
      (✅ paper.bib has DOIs for every entry)
- [x] The text is single-spaced; uses a 12-point font; employs
      italics, rather than underlining (except with URL addresses);
      and all illustrations, figures, and tables are placed within
      the text at the appropriate points, rather than at the end.
      (✅ Pandoc default styling already satisfies this)
- [x] The text adheres to the stylistic and bibliographic
      requirements outlined in the
      [Author Guidelines](https://openresearchsoftware.metajnl.com/about/submissions#authorGuidelines).

---

## Portal step 3 — Title and abstract

### Title (paste verbatim)

```
PaperGuard: A 39-detector open-source pipeline for triage-stage statistical-anomaly screening in research-data integrity, with a non-verdict architectural design and 13 empirical-calibration studies
```

### Abstract (paste verbatim — 220 words)

```
Research-data integrity tooling has historically been a patchwork of single-signal procedures — statcheck for p-value recomputation, GRIM and SPRITE for summary-statistic reverse-reconstruction, the Carlisle procedure for randomised-trial baseline balance, Bik-style perceptual-hash workflows for image-duplication forensics — each living in a separate codebase with its own conventions and threshold choices. PaperGuard is a Python library, command-line tool, and multi-tenant Web UI that integrates Python re-implementations of these published procedures with thirty additional detectors across eight methodological families, including a four-detector industrial-process layer for which no direct prior art exists in the academic-integrity literature. The pipeline is architecturally non-verdict: every Finding emitted by every detector ships with at least three plausible innocent explanations, and verdict vocabulary (fraud, fabrication, misconduct) is forbidden at the codebase level by a static check. The software ships with thirteen public empirical calibration studies covering text-layer recall (N=200), image-layer recall (N=212 in the latest run), industrial-process recall (N=200 synthetic), B4-vs-R-statcheck cross-validation (κ=0.79 on N=41), and per-endpoint controlled benchmarks of the LLM-text family on five real chat-completion endpoints. Honest negative findings — including image-layer LR+ ≈ 1 on randomly-sampled retracted papers and continuation-perplexity direction inversion on RLHF-tuned OpenAI reference language models — are published at face value as a design choice.
```

### Keywords (paste, separated by `;` or `,` per portal)

```
research integrity; statistical forensics; LLM-text detection; image forensics; industrial-process data; GRIM; statcheck; SPRITE; Carlisle; DetectGPT; empirical calibration
```

---

## Portal step 4 — Author details

Only one author. Paste into the corresponding fields.

| Portal field | Value |
|---|---|
| **First name** | Lei |
| **Last name (family name)** | Zhou |
| **Email** | (use your real submission-correspondence email; the JORS portal will not surface this publicly) |
| **ORCID** | 0009-0000-9073-1349 |
| **Affiliation** | Independent |
| **Country** | United States (or your current residence per your earlier note that you are US-based) |
| **Role in submission** | Author |
| **Is corresponding author?** | Yes |

### Author bio (if portal asks — 1-2 sentences)

```
Lei Zhou is an independent open-source software developer and the sole author of PaperGuard, a Python library and Web UI for triage-stage research-integrity screening. PaperGuard composes Python re-implementations of statcheck, GRIM, SPRITE, the Carlisle procedure, and Bik-style image forensics with thirty additional detectors, and ships thirteen public empirical-calibration studies.
```

---

## Portal step 5 — File uploads

Upload in this order. JORS portal labels each file by "component":

| Component | File to upload | Path in repo |
|---|---|---|
| **Article text** (main paper) | `paper_jors.docx` | `paper/paper_jors.docx` |
| **Supplementary file — Cover letter** | `jors_cover_letter.docx` | `paper/jors_cover_letter.docx` |
| **Supplementary file — Recommended reviewers** | `jors_recommended_reviewers.docx` | `paper/jors_recommended_reviewers.docx` |
| **Supplementary file — Bibliography (BibTeX source)** | `paper.bib` | `paper/paper.bib` |
| **(Optional)** Markdown source of the manuscript | `paper_jors.md` | `paper/paper_jors.md` |

Download the four files locally from the repository:
- https://github.com/exergyleizhou-ux/PaperGuard/raw/main/paper/paper_jors.docx
- https://github.com/exergyleizhou-ux/PaperGuard/raw/main/paper/jors_cover_letter.docx
- https://github.com/exergyleizhou-ux/PaperGuard/raw/main/paper/jors_recommended_reviewers.docx
- https://github.com/exergyleizhou-ux/PaperGuard/raw/main/paper/paper.bib

---

## Portal step 6 — Comments for the editor (free-text box)

Most JORS submissions paste a 1-2-paragraph version of the cover letter here. Either upload the full `jors_cover_letter.docx` and write:

```
The full cover letter is attached as a supplementary file (jors_cover_letter.docx). One-paragraph summary follows:

PaperGuard is a Python library, command-line tool, and multi-tenant Web UI that integrates Python re-implementations of five well-established research-integrity procedures (statcheck, GRIM, SPRITE, the Carlisle method, perceptual-hash image forensics) with thirty additional detectors across eight methodological families, plus a four-detector industrial-process layer for which no direct prior art exists. The submission is heavy on empirical calibration (13 public studies) and reuse-potential evidence (5 documented axes) — exactly the material the JORS Software Metapaper format is designed to foreground. We earlier submitted a JOSS-format short paper that was returned at pre-check on the JOSS-specific six-month-public-history rule (JOSS #10600); the JORS manuscript is substantially expanded and restructured to the JORS five-section format, not a refile. No competing interests, no external funding, sole author. Looking forward to reviewer feedback.
```

---

## Portal step 7 — Suggested reviewers

JORS portal usually offers ≤5 reviewer slots. Paste from the table below — full justification is in `jors_recommended_reviewers.docx`.

| # | Name | Affiliation | ORCID (verify by clicking) | Best-fit reason |
|---|---|---|---|---|
| 1 | Michèle B. Nuijten | Tilburg University | [0000-0001-8472-0424](https://orcid.org/0000-0001-8472-0424) | statcheck B4 calibration |
| 2 | Nicholas J. L. Brown | Linnaeus University | [0000-0001-5604-6473](https://orcid.org/0000-0001-5604-6473) | GRIM B1 / GRIMMER B6 |
| 3 | James A. J. Heathers | Cipher Skin | [0000-0002-4377-0307](https://orcid.org/0000-0002-4377-0307) | SPRITE B8 |
| 4 | Elisabeth M. Bik | Independent | [0000-0002-1352-9551](https://orcid.org/0000-0002-1352-9551) | image-forensics F-family |
| 5 | Dmitry Kobak | University of Tübingen | [0000-0002-5639-7209](https://orcid.org/0000-0002-5639-7209) | LLM-text T-family |

**Reviewer email lookup process** (since I cannot pre-fill emails):

1. Click the ORCID link, confirm the profile is the right person.
2. Click "Websites and social links" or follow to the institutional
   page from the ORCID profile.
3. Most academics list email on their institutional page; some only
   on Google Scholar profile.
4. If you cannot find the email in 60 seconds, skip that reviewer
   and use one of the alternates from `jors_recommended_reviewers.md`
   (Cabanac, Epskamp, Lakens, Mitchell, Christopher, Ioannidis,
   Bouter).

---

## Portal step 8 — Competing interests / funding declarations

### Competing interests (paste verbatim)

```
The author declares no competing interests, financial or otherwise.
```

### Funding sources (paste verbatim)

```
No external funding supported the development of PaperGuard. The project is independently developed and maintained.
```

### Data availability statement (paste verbatim)

```
All software source code, empirical-study raw data, and analyser scripts are publicly available under the MIT License at https://github.com/exergyleizhou-ux/PaperGuard. Versioned snapshots are published on PyPI (https://pypi.org/project/paperguard/) and as multi-architecture Docker images on the GitHub Container Registry (ghcr.io/exergyleizhou-ux/paperguard). Archived versioned snapshots will be deposited on Zenodo with DOI assignment on publication acceptance.
```

---

## Portal step 9 — APC waiver request

JORS APC is currently around £500 (~ USD 650). Ubiquity Press grants waivers to authors without institutional funding.

When the portal asks "Will you apply for an APC waiver?", select **Yes** and paste this justification:

```
The corresponding author is an independent open-source developer with no external funding, no institutional support, and no employer-paid publication budget. PaperGuard is a fully self-funded volunteer project. We respectfully request a full APC waiver under JORS's standard policy for unfunded independent authors.
```

---

## Portal step 10 — Final review + confirmation

Before clicking **Submit**:

- [ ] All metadata in step 3 saved (title, abstract, keywords)
- [ ] Author details in step 4 saved (name, ORCID, affiliation, email)
- [ ] All four files uploaded in step 5
- [ ] Comments-to-editor box (step 6) filled
- [ ] 5 reviewer suggestions submitted (step 7)
- [ ] COI / funding / data-availability statements pasted (step 8)
- [ ] APC waiver request submitted (step 9)

Click **Submit**.

---

## What happens after Submit

1. **Within minutes:** automated confirmation email with a JORS
   submission tracking number.
2. **1-2 weeks:** an editor performs pre-check (scope fit + format
   compliance + APC waiver decision).
3. **4-8 weeks:** reviewer assignment + first-round reviews delivered
   on the JORS portal.
4. **4-8 weeks:** you upload revised manuscript + point-by-point
   response.
5. **2-4 weeks:** editor decision (accept / minor revision / major
   revision / reject).
6. **On acceptance:** DOI minted via Crossref. Typical end-to-end
   median for JORS Software Metapapers: ~12–20 weeks.

---

## What I (the agent) can do for you after submission

- Track the editor pre-check email — paste it to me, I will draft a reply.
- When reviewer reports arrive, paste them in — I will draft a point-by-point response and the code changes they request.
- If a reviewer asks for additional empirical evidence, I will run new benchmarks on the OpenAI key and document them.
- If they suggest a different journal, I will adapt the manuscript.

---

## Files at-a-glance

| File | Purpose |
|---|---|
| `paper/paper_jors.docx` | **Main manuscript** — upload as "Article text" |
| `paper/jors_cover_letter.docx` | **Cover letter** — upload as supplementary |
| `paper/jors_recommended_reviewers.docx` | **Reviewer suggestions** — upload as supplementary AND copy into portal form |
| `paper/paper.bib` | **Bibliography source** — upload as supplementary |
| `paper/jors_submission_checklist.md` | This file — your portal walkthrough |
