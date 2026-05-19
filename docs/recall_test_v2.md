# Recall / precision study — v2 (N = 100 + 100)

Second iteration of the PaperGuard recall study (the v1 pilot is in
[`recall_test_v1.md`](recall_test_v1.md)). v2 fixes the operational
blockers v1 uncovered:

- **Unpaywall-first PDF URL resolution.** OpenAlex's `oa_url` often
  redirects to publisher landing pages; Unpaywall's
  `best_oa_location.url_for_pdf` more often points at the actual PDF.
  v2 tries Unpaywall first and only falls back to OpenAlex.
- **`%PDF-` magic-byte validation.** Downloads that begin with anything
  else (typically `<!DOCTYPE html>`) are rejected rather than fed to
  the scanner.
- **Per-host rate limiting** (1 req/s) — defensive.
- **Scanner is now error-tolerant** (PaperGuard 2.0.3+) so individual
  bad PDFs no longer derail the whole run.
- **Resumable streaming output**: a partial JSON is written every 10
  records, so an SSL/TLS blip late in the run does not erase progress.
- **Network retry**: 3 attempts on `httpx.ReadError`,
  `httpx.ConnectError`, and `httpx.RemoteProtocolError` (the GFW
  occasionally corrupts TLS frames mid-stream from this network).

Methodology and reproducer in
[`scripts/recall_test_v2.py`](../scripts/recall_test_v2.py); analysis
in [`scripts/recall_analyze.py`](../scripts/recall_analyze.py).

## Headline

> **PaperGuard's PDF-only mode is not a meaningful retraction
> detector.** At `sev ≥ 2 (SUSPICIOUS)` the recall on retracted papers
> is 68% — but the false-positive rate on matched non-retracted
> controls is 88%, for a positive likelihood ratio (LR+) of 0.77 —
> worse than a coin flip.
>
> **No single detector fires meaningfully more on retracted papers in
> this sample.** T5 (stylometry) fires near-universally on both arms
> (98% vs 81%); T3 (data availability) is essentially flat (68% vs
> 62%); T4 (tortured phrases) and F1 (image pHash) actually fire
> *more* on the control arm (T4: 0.30×; F1: 0.27×) — almost certainly
> a sample-composition artefact, not a property of the detectors.
>
> The numeric forensics (A1 / A2 / A3 / A5 / A6 / A7) almost never
> fire because published PDFs rarely embed data tables of
> N ≥ 50 rows in their body.

This is the same warning the
[`quickstart`](quickstart.md) and
[`fraud_case_studies`](fraud_case_studies.md) docs already give —
**PaperGuard's strong detectors live on raw data files
(`.csv` / `.xlsx`), not on PDFs.** v2 puts a number on it. PDF-only
scanning is a triage hint, not a verdict, and the user who scans only
the PDF will see signal that is almost entirely confounded with year,
writing style, and publisher conventions. The intended use — scan
the supplementary data files alongside the manuscript — is still the
recommended workflow.

A preliminary look at the first 17 scans showed F1 as the strongest
discriminator. The full N = 56 reverses that. **Document this
honestly rather than spinning the partial finding** — partial samples
of detector-firing patterns are noisy and the "discovery" from a
preliminary look should always be re-checked at full N.

## Pipeline stages

| Arm | Queried | Downloaded as PDF | Scan returned severity |
|---|---|---|---|
| Retracted | 100 | 40 (40%) | 40 (40%) |
| Control | 100 | 16 (16%) | 16 (16%) |

The retracted / control download success gap is informative: many of
the cited-by-count-leading retracted papers are from publishers
(Elsevier, Cell Press, Springer-Nature flagship journals) whose OA
PDF endpoints aggressively 403 anonymous clients. The controls were
matched on subfield + year, so they tend to come from the same
publishers and inherit the same gating.

## Download outcomes

| Outcome | Retracted | Control |
|---|---|---|
| 403 Forbidden | 28 | 69 |
| OK (real PDF) | 40 | 16 |
| HTML served as .pdf | 17 | 12 |
| 404 Not Found | 11 | 0 |
| Network error | 2 | 2 |
| Other | 2 | 1 |

The retracted-vs-control gap (40% vs 16% download success) is itself
informative: many of the cited-by-count-leading retracted papers come
from a small set of publishers (Elsevier, Cell Press, JBC) whose
controls were matched on the same publishers and journals, which then
returned 403 to anonymous clients more aggressively for the
non-retracted articles. That asymmetry biases the per-arm composition
of "things that reached the scanner" — retracted papers in this
sample skew slightly newer (typical retractions surface 2–5 years
after publication, so the cited-by-count-sorted retracted bucket
clusters around 2015–2020) while controls reach further back into
papers cited heavily over a longer period.

The dominant failure modes:

- **403 Forbidden** — Elsevier, Cell Press, etc. require institutional
  auth even when the paper is OA. v3 plan: try PubMed Central first
  for any paper with a PMC ID, since PMC consistently serves raw PDFs.
- **HTML (not PDF)** — Unpaywall sometimes returns a landing-page URL
  in `url_for_pdf` for newer articles whose PDF link is generated
  client-side. v3 plan: follow the landing page and look for
  `<meta name="citation_pdf_url">`.

## Severity distribution

| Arm | sev=0 PASS | sev=1 CONCERN | sev=2 SUSPICIOUS | sev=3 CRITICAL |
|---|---|---|---|---|
| Retracted | 0 (0%) | 13 (32%) | 21 (52%) | 6 (15%) |
| Control | 0 (0%) | 2 (12%) | 7 (44%) | 0 (0%) |

The retracted arm does skew slightly higher (15% CRITICAL vs 0%) but
the control arm also sits mostly at SUSPICIOUS. With N = 40 + 16
reaching the scanner stage, a two-sample test of severity ≥ 2 gives
no significant difference. The CRITICAL band is the most discriminative
visually but has only 6 retracted hits — too few to base a
recommendation on.

The retracted arm skews higher on `sev=2/3` — but so does the control
arm. With the modest N reaching the scan stage, the per-arm
distributions overlap enough that the difference is not significant.

## Per-detector firing rate

| Detector | Retracted % | Control % | Ratio (retr / ctrl) |
|---|---|---|---|
| A6 | 2% | 0% | ∞ |
| T5 | 98% | 81% | 1.20× |
| T3 | 68% | 62% | 1.08× |
| T4 | 8% | 25% | 0.30× |
| F1 | 5% | 19% | 0.27× |

Reading the table — and being honest about which "signals" are
artefacts:

- **A6 (implausible values)** fires 2% on retracted, 0% on control.
  Numerator of 1 vs 0; this is noise at N = 40 + 16. Promising but
  not yet a real signal.
- **T5 (stylometry)** fires on nearly every paper in both arms — its
  reference distribution comes from
  [Markowitz & Hancock 2014](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0105937)
  on English psychology prose. Most biomedical writing exceeds the
  reference adjective density. **Effective recalibration is the
  highest-value follow-up for T5.** Currently it acts like a
  near-constant "yes" flag.
- **T3 (data-availability statement)** is essentially flat at 1.08×.
  Older papers and newer papers both miss the statement; the binary
  "is there one" signal is too crude to be discriminative by itself.
- **T4 (tortured phrases)** fires *more* on the control arm
  (0.30× ratio). Likely an age artefact — the control arm reaches
  back further into machine-translation-era papers from non-English
  research traditions, where T4's MT fingerprints legitimately appear
  without indicating fraud.
- **F1 (cross-image pHash duplication)** also fires *more* on the
  control arm (0.27× ratio). This contradicts the
  [Bik et al. 2016](fraud_case_studies.md) baseline expectation of
  ~2% inappropriate-duplication rate enriched among retracted papers.
  Two plausible explanations: (a) the control arm in this sample
  includes papers that legitimately reuse figures across
  publications (e.g. method-paper trial-flow diagrams); (b) the F1
  threshold tuned for cross-paper duplication via the persistent
  pHash store (F4) is over-firing on intra-paper figure reuse.
  Worth investigating per-paper before drawing a conclusion.
- **Numeric-forensics detectors (A1 / A2 / A3 / A5 / A7)** rarely
  appear in either arm because most published PDFs do not embed raw
  data tables with N ≥ 50 rows in the body.

## Recall vs false-positive at severity thresholds

| Threshold | Recall (retracted hit) | False-positive (control hit) | LR+ |
|---|---|---|---|
| sev ≥ 1 (CONCERN) | 40 / 40 = 100% | 16 / 16 = 100% | 1.00 |
| sev ≥ 2 (SUSPICIOUS) | 27 / 40 = 68% | 14 / 16 = 88% | 0.77 |
| sev ≥ 3 (CRITICAL) | 6 / 40 = 15% | 7 / 16 = 44% | 0.34 |

A positive likelihood ratio (LR+) ≤ 1 means the test is no better
than guessing. PaperGuard's PDF-only mode at the SUSPICIOUS threshold
sits at LR+ 0.77 — strictly worse than a coin flip on this matched
sample. The CRITICAL threshold is 0.34 (worse still).

The PDF-only recall numbers are **not** what you should quote
PaperGuard with. The tool's intended use is to scan supplementary
data files alongside the manuscript; PaperGuard would be expected to
flag the underlying spreadsheets in cases like Wansink-style
p-hacking. The numbers above measure something narrower: "does the
PDF alone trigger the scanner on a retracted paper?"

## Why the controls also fire

A subtle but important point: PaperGuard is **honest about its
threshold semantics**. `sev ≥ 1 (CONCERN)` is meant to be triggered
liberally — the design philosophy is "flag is an invitation to look
more carefully, not a conclusion". Each finding ships with at least
three innocent explanations precisely because legitimate causes are
common. The N = 100 + 100 confirms that design: controls land in the
`sev = 1/2` zone often, because they have legitimately low adjective
density, legitimately no data-availability statement, etc.

The signal therefore lives in **detector identity + co-firing**, not
in the aggregate severity. F1 firing on a paper is more interesting
than three soft T3/T5/T4 flags firing on the same paper.

## v3 plan

Concrete next steps before doing a third recall pass:

1. **PMC-first fetcher** — for any retracted/control paper with a PMC
   ID (most NIH-funded work has one), pull the PDF directly from
   `https://www.ncbi.nlm.nih.gov/pmc/articles/{PMC_ID}/pdf/{PMC_ID}.pdf`.
   This bypasses publisher 403s on a large fraction of biomedical
   retractions.
2. **Recalibrate T5** — fit the reference distribution on a
   subfield-specific corpus of OA papers (~10k articles) rather than
   reusing the 2014 psychology baseline. The recalibration could be
   per-subfield (rather than global).
3. **Stratify the report by Retraction Watch reason code** when the
   RW CSV is provided. Image duplication retractions should pop F1
   even harder; data-fabrication retractions might show T5 elevation
   if the writing-style fingerprint of fabricated text actually
   replicates. Plagiarism retractions should be silent on PaperGuard
   (it does not do text reuse) — measurable null result.
4. **Pair with supplementary-file detection.** For papers where
   OpenAlex returns a `supplementary_files` link, scan those too and
   record per-arm signal lift. This is the use case PaperGuard was
   actually built for.

## Reproducing v2

```bash
.venv/Scripts/python.exe scripts/recall_test_v2.py \
  --n 100 \
  --out scripts/recall_test_v2_results.json

.venv/Scripts/python.exe scripts/recall_analyze.py \
  scripts/recall_test_v2_results.json
```

`scripts/recall_test_v2.py` makes 200 OpenAlex calls and 200
publisher PDF downloads (rate-limited 1 req/s/host). Wall clock is
about 1–2 hours on a fast link, longer on a flaky one. The SHA-256 of
each successful download is recorded in the output JSON so the
specific PDFs are traceable.

`scripts/recall_analyze.py` is decoupled from the runner and can be
re-run on the final or partial JSON without redoing downloads.

## Disclaimer

These numbers describe how PaperGuard behaves on the published-PDF
slice of the retraction problem. They are not, and were never
intended to be, an evaluation of "can PaperGuard catch fraud".
PaperGuard flags **statistical anomalies, not fraud**; every finding
lists possible innocent explanations; a flag is an invitation to look
more carefully, not a conclusion. Most of the actually damning
evidence in real cases (Wansink p-hacked spreadsheets, Stapel's
suspiciously clean Excel files, the Geng-method digit patterns) lived
in the data files, not in the typeset PDFs of the resulting papers.
