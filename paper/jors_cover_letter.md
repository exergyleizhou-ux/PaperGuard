# Cover letter — Journal of Open Research Software submission

**Manuscript title:** PaperGuard: A 39-detector open-source pipeline
for triage-stage statistical-anomaly screening in research-data
integrity, with a non-verdict architectural design and 13
empirical-calibration studies

**Corresponding author:** Lei Zhou (ORCID
[0009-0000-9073-1349](https://orcid.org/0009-0000-9073-1349))

**Software repository:**
[https://github.com/exergyleizhou-ux/PaperGuard](https://github.com/exergyleizhou-ux/PaperGuard)

**Submitted version:** [v2.6.1](https://github.com/exergyleizhou-ux/PaperGuard/releases/tag/v2.6.1)

**Date:** 24 May 2026

---

Dear Editors,

Please find attached the manuscript "PaperGuard: A 39-detector
open-source pipeline for triage-stage statistical-anomaly screening
in research-data integrity..." for consideration as a Software
Metapaper in the *Journal of Open Research Software*.

## Why JORS

The manuscript describes a Python library, command-line tool, and
multi-tenant Web UI that integrates Python re-implementations of
five well-established research-integrity procedures (`statcheck`,
GRIM, SPRITE, the Carlisle method, perceptual-hash image forensics)
with thirty additional detectors across eight methodological
families, including a four-detector industrial-process layer for
which no direct prior art exists in the academic-integrity
literature. We submit to JORS specifically because the paper is
heavy on **empirical calibration (13 published studies)** and on
**reuse-potential evidence (5 documented reuse axes)** — exactly the
material the JORS Software Metapaper format is designed to
foreground. A short-form journal would force us to omit the honest
negative findings (image-layer LR+ ≈ 1 on randomly-sampled
retracted papers; T7 continuation-perplexity direction inversion
on RLHF-tuned OpenAI reference language models) that we consider
load-bearing for the tool's trustworthiness.

## Prior submission history

We earlier submitted a JOSS-format short paper of the same software
(2026-05-23, JOSS submission #10600). JOSS pre-check returned the
paper as out of editorial scope on the grounds that the project
lacked the JOSS-required six-month public-development history at
submission time — the underlying work spans more than six months
but the public-repository timeline did not. The editor (Daniel S.
Katz) explicitly suggested resubmission to one of JOSS's
recommended sister venues, of which JORS is the most natural fit
given our empirical-heavy content. The JORS manuscript is
substantially expanded and restructured to the JORS five-section
format; it is not a refile of the JOSS short-form text.

## Confirmations

- The submitted software is original work of the corresponding
  author; no portion is published or submitted elsewhere; no
  portion is under consideration at another peer-reviewed venue.
- The repository is MIT-licensed and publicly available; all 13
  empirical-calibration studies are reproducible from raw data
  and analyser scripts shipped under `scripts/` and `docs/`.
- The corresponding author declares no competing interests,
  financial or otherwise. The project is independently developed
  and has received no external funding.
- I am the sole primary author and am happy to handle review
  correspondence directly.

## Author contributions

Lei Zhou (sole author): conceptualisation, implementation of all
39 detectors, design and execution of all 13 empirical-calibration
studies, manuscript preparation. Third-party contributions are
welcomed via the GitHub pull-request flow but no such contributions
were merged into the codebase at the time of this submission.

## Note to editors on the manuscript's honest negative findings

Several sections of the manuscript (§3 Quality control in
particular) report *negative* empirical results — most notably that
the image-forensics layer's likelihood ratio at default thresholds
is statistically indistinguishable from chance on a randomly-
sampled biomedical OA retraction corpus, and that the T7
continuation-perplexity detector's direction inverts on
RLHF-tuned OpenAI reference language models. We have chosen to
publish these at face value rather than suppress them. The
alternative — quoting earlier small-sample favourable numbers
(e.g. v4's F6 LR+ = 1.63 at N=159) as if they were calibrated
operating points — would be exactly the kind of mis-calibration
the tool is designed to flag in others' work. We hope the
reviewers will read this as the design choice it is rather than
as a weakness.

Thank you for your time and for the JORS open-science mission. I
look forward to the reviewers' feedback.

Sincerely,

**Lei Zhou**
ORCID: 0009-0000-9073-1349
Repository: https://github.com/exergyleizhou-ux/PaperGuard
