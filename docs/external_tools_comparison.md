# PaperGuard vs other research-integrity tools

> What PaperGuard is, what it is **not**, and what the adjacent tools
> in this space do that PaperGuard either incorporates, deliberately
> avoids, or has yet to integrate. Honest comparison, no marketing.

PaperGuard sits in a small but growing field. This document compares
it to four other public efforts so users can pick the right tool for
the job and so PaperGuard contributors can see which ideas are worth
absorbing (and which are not).

## Quick table

| Tool | What it is | Detector count | Language | License | Maintained | Output stance |
|---|---|---|---|---|---|---|
| **PaperGuard** | Python library + CLI + Web UI + 39 detectors + 13 empirical studies | 39 | Python | MIT | active | Non-verdict; ≥3 innocent explanations per Finding |
| **statcheck** (Nuijten et al. 2016) | R package — recompute p-values from text | 1 | R | GPL-3 | active | Lists inconsistencies; no verdict |
| **GRIM / SPRITE / GRIMMER** (Heathers, Brown, Anaya) | Standalone scripts for granularity / reconstruction tests | 3 procedures | R/Python | mixed | active | Anomaly flags; explicit "not proof of fraud" |
| **`geng-academic-fraud-detector`** ([wooly99 2026](https://github.com/wooly99/geng-academic-fraud-detector)) | Claude prompt-template skill (~12 KB, no code) | 6 hand-curated prompts | Markdown prompt | MIT | passion-project | "实锤"-tier verdict language, names targets, includes "辣评" |
| **Bik et al. pHash image-forensics workflow** (private corpus) | Hand-curated dataset + manual pHash workflow | 1 procedure | manual | not redistributable | Bik personally | Per-image flags; published in PubPeer threads |

## What PaperGuard incorporates from each

### statcheck (Nuijten et al. 2016) — **fully incorporated**

- PaperGuard's **B4 statcheck detector** is a Python re-implementation
  of the published statcheck protocol.
- Cross-validation against the R `statcheck` package on a 41-paper
  ground-truth corpus shows **Cohen's κ = 0.79** (Landis-Koch
  "substantial agreement"), with **recall = 100 %** and decision-flip
  recall = 94.12 %. See [`docs/crossval_statcheck.md`](crossval_statcheck.md)
  and [`docs/crossval_statcheck_kappa.md`](crossval_statcheck_kappa.md).
- We do not claim equivalence beyond the κ — there are edge cases
  where R-statcheck and PaperGuard-B4 disagree, and the κ documents
  the disagreement rate honestly.

### GRIM / SPRITE / GRIMMER (Heathers, Brown, Anaya) — **fully incorporated**

- **B1 GRIM**, **B6 GRIMMER**, **B8 SPRITE** are direct
  implementations of the published procedures.
- The original papers' authors are cited in each detector's
  `academic_basis` class attribute and in the per-detector docs at
  [`docs/detectors/`](detectors/).

### `geng-academic-fraud-detector` ([wooly99 2026](https://github.com/wooly99/geng-academic-fraud-detector)) — **selectively absorbed (2.4.0)**

The "六式" prompt checklist overlaps PaperGuard's existing detector
family extensively. After a 2026-05-23 review of the SKILL.md
contents:

| Geng-skill "式" | Already covered in PaperGuard? | Absorbed in 2.4.0? |
|---|---|---|
| 第一式 image reuse | F1 intra-paper pHash, F4 cross-paper pHash, F6 patch-splice | ✅ existing |
| 第二式 constant inter-column differences | A3 inter-column arithmetic | ✅ existing |
| 第二式 SD all integers / fixed decimals | A5 decimal-fraction consistency | ✅ existing |
| 第二式 GRIM-style impossible means | B1 GRIM | ✅ existing |
| 第三式 Western blot splice | F3 splice forensics | ✅ existing |
| 第四式 p-hacking distribution | B7 p-curve | ✅ existing |
| 第四式 reported t/F vs reported df mismatch | B4 statcheck | ✅ existing |
| 第五式 production rate / co-author graph | M1 paper-mill graph | ✅ existing |
| **第六式 reagent cited with a year postdating the paper** | **— not previously covered —** | **✅ G5 new in 2.4.0** |

The honest "absorb / do not absorb" decision:

**Absorbed (the technique):**
- The reagent-year-vs-paper-year consistency check is concrete,
  testable, and additive. Implemented as the new **G5
  ReagentTemporalDetector** with NOTE-level severity and four
  innocent explanations per Finding. See
  [`src/paperguard/detectors/g5_reagent_temporal.py`](../src/paperguard/detectors/g5_reagent_temporal.py).

**Deliberately NOT absorbed (the framing):**
- The verdict-tier vocabulary (`实锤` / `打假` / `学术不端`). PaperGuard's
  iron rule is that detector output never uses fraud-verdict language;
  every Finding is presented as an anomaly worth a reviewer's attention,
  not a conclusion about misconduct.
- The "辣评" (witty roast) section. PaperGuard reports are written for
  editors and integrity officers, not for entertainment.
- Naming specific targets. The geng-skill's example report lists real
  authors, real DOIs, real journals by name with verdict labels.
  PaperGuard never does this; the
  [`docs/fraud_case_studies.md`](fraud_case_studies.md) reference set
  covers cases that **have already been formally retracted or
  investigated**, and discusses the public-record findings, not
  PaperGuard's own verdict.
- The "建议向作者机构举报" action items. PaperGuard is a triage tool,
  not a referral pipeline; the responsibility for further action lives
  with the journal editor or institutional integrity officer.

**Why these matter:** the geng-skill's framing presupposes its target
is a guilty party. PaperGuard's framing — and the entire reason its
findings ship with ≥3 innocent explanations — is that the same
detection signal can have benign causes (instrument quirks,
copy-editor formatting, honest mistakes), and a screening tool that
forgets this becomes a defamation generator. The two tools have
different theories of who their users are: the geng-skill is for
people who already believe they have caught a fraudster; PaperGuard
is for people deciding whether the paper deserves a closer look.

### Bik et al. pHash image-forensics workflow — **partially incorporated; corpus not redistributable**

- PaperGuard's **F1 / F2 / F3 / F4 / F6** detectors reproduce the
  *technique* family (perceptual hashing, ORB matching, per-channel
  histogram patch-splice) that Bik's published PubPeer threads
  document.
- Bik's actual curated corpus is **not publicly redistributable** and
  PaperGuard does not reproduce it. The
  [v3 / v4 / v5 image-recall studies](recall_image_v5.md) use OpenAlex
  retracted papers + matched controls instead, which under-represents
  the patch-splice failure mode F6 was tuned to detect. This is
  documented honestly in the v5 writeup and motivates the proposed v6
  PubMed-Central-only control source.

## What PaperGuard does that no other tool does

- **A non-verdict architectural design.** Every Finding ships with
  three to four `innocent_explanations`. The CLI has a static check
  that rejects any detector output containing the words `fraud /
  造假 / misconduct / cheating / 学术不端`. This is structural, not
  policy.
- **Joint detector evidence combination.** The
  [`paperguard.evidence.combiner`](../src/paperguard/evidence/combiner.py)
  module aggregates per-detector p-values via Benjamini-Hochberg FDR
  + a Stouffer-style integrity index. Single-detector tools cannot do
  this.
- **A four-detector industrial layer** (I1 mass-balance / I2 SCADA
  timestamps / I5 batch-repetition / I6 trend over-smoothness) plus
  12 domain templates (wastewater / waste-gas / pharmaceutical /
  semiconductor / food / environmental / agricultural / biopharma /
  biocomputation / distillation / chemical / medical). No prior art
  in the academic-integrity literature.
- **13 empirical studies** including per-detector likelihood ratios
  with Wilson 95 % confidence intervals (added in 2.3.1), and a
  per-endpoint compatibility matrix for the LLM-text detectors
  documenting *which endpoint classes the underlying methods are
  mathematically valid on*. See
  [`docs/llm_detection_real_endpoints.md`](llm_detection_real_endpoints.md).
- **Plugin entry-point system.** Third-party detectors can register
  via `paperguard.detectors` entry point without forking. No other
  tool in this space supports this.

## What PaperGuard does **not** do that other tools or workflows do

- **No live human review.** Bik's workflow is fundamentally
  human-in-the-loop pixel inspection. PaperGuard's F1/F4/F6 detectors
  cannot replace a trained human eye on a single contested image.
- **No publisher-side ingestion pipeline.** Crossref iThenticate and
  related plagiarism systems sit at the journal-submission gate.
  PaperGuard is a post-hoc and pre-submission triage tool, not a
  submission-gate filter.
- **No verdict.** Not now, not ever. This is the design constraint
  from which all of the above design choices derive.

## Citation suggestions

If you use PaperGuard in published research, please cite the JOSS
software paper (DOI pending submission — currently
[`paper/paper.md`](../paper/paper.md)) and, for the empirical-corpus
contribution specifically, the forthcoming Scientific Data data
descriptor (outline at [`paper/dataset_paper.md`](../paper/dataset_paper.md)).
The original statcheck, GRIM, SPRITE, GRIMMER, Carlisle, and Bik
references are listed in [`paper/paper.bib`](../paper/paper.bib) and
should be cited directly when their specific methods are central to
the analysis.
