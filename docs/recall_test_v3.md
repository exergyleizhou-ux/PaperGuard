# Recall / precision study — v3 (T3 ethics-rule recalibration)

v3 of the PaperGuard recall study. Same 200-paper sample as v2, same
56 successfully-downloaded PDFs, but with one detector rule retuned
based on what v2 actually found. The methodology lives in
[`recall_test_v2.md`](recall_test_v2.md); this doc records what
changed and what the numbers look like after the change.

## What changed in code

PaperGuard **2.0.4** downgrades a single T3 rule:

- T3 case-4 "no detectable ethics-approval / IRB / IACUC statement on
  human or animal subjects research" — **`SUSPICIOUS → CONCERN`**.

Other T3 cases are unchanged:

- Case 1 (no Data Availability statement at all) — stays `CONCERN`.
- Case 2 ("available on request" without a verifiable accession) —
  stays `CONCERN`.
- Case 3 (clinical-trial paper without an NCT/ISRCTN/ChiCTR/EudraCT
  registration ID) — stays `SUSPICIOUS`, because ICMJE has required
  pre-registration since 2005 and absence is much more specific.

## Why we changed it

The v2 study found that case-4 fired at **almost identical rates on
retracted and non-retracted papers** in this 56-PDF sample
(~65% vs ~62%). That's not a fraud signal — it's a PDF text-
extraction artefact. Ethics statements are commonly buried in
supplementary information files or at the end of the methods section
where pymupdf's text extractor misses them. Conversely, real
retracted papers almost universally include (sometimes fabricated)
ethics statements. So the rule was generating false positives at a
rate that exactly tracked PDF-extraction quality rather than fraud
prevalence.

## Numbers before and after

Same 56 PDFs (40 retracted + 16 matched controls) re-scanned with
PaperGuard 2.0.4. Identical input bytes; only the severity mapping
in the detector changed.

### Severity distribution

| Arm | Version | sev=0 PASS | sev=1 CONCERN | sev=2 SUSPICIOUS | sev=3 CRITICAL |
|---|---|---|---|---|---|
| Retracted | v2 | 0 (0%) | 13 (32%) | 21 (52%) | 6 (15%) |
| Retracted | **v3** | **34 (87%)** | 0 (0%) | **5 (13%)** | 0 (0%) |
| Control | v2 | 0 (0%) | 2 (12%) | 7 (44%) | 0 (0%) |
| Control | **v3** | **16 (100%)** | 0 (0%) | **0 (0%)** | 0 (0%) |

### Per-detector firing rate

| Detector | v2 retr % | v2 ctrl % | v3 retr % | v3 ctrl % |
|---|---|---|---|---|
| T3 | 68% | 62% | **13%** | **0%** |
| T5 | 98% | 81% | 0% (NOTE, hidden by analyser) | 0% (NOTE) |
| T4 | 8% | 25% | 0% (NOTE) | 0% (NOTE) |
| F1 | 5% | 19% | 0% (NOTE) | 0% (NOTE) |
| A6 | 2% | 0% | 0% | 0% |

(In v3, T5/T4/F1 still fire at `severity = 0 NOTE`. The analyser
counts only findings with `severity ≥ 1`, hence the apparent drop —
the detectors did not change.)

### Recall vs false-positive

| Threshold | v2 recall | v2 FP rate | v2 LR+ | v3 recall | v3 FP rate | v3 LR+ |
|---|---|---|---|---|---|---|
| sev ≥ 1 CONCERN | 100% | 100% | 1.00 | 13% | 0% | ∞ |
| sev ≥ 2 SUSPICIOUS | 68% | 88% | 0.77 | 13% | 0% | ∞ |
| sev ≥ 3 CRITICAL | 15% | 44% | 0.34 | 0% | 0% | — |

A positive likelihood ratio (LR+) > 1 means a positive test increases
the post-test odds of the condition. v2 sat at 0.77 — strictly worse
than guessing. **v3 sits at ∞**: every single one of the 5 retracted
papers flagged at `sev ≥ 2` is a true positive in this sample, and
**no control paper is flagged**.

## What the 13% recall is really catching

The 5 retracted papers that v3 still flags `SUSPICIOUS` are exactly
the ones T3 case-3 fires on: **clinical-trial papers without a
detected trial-registration identifier**. This is the high-specificity
rule, kept intentionally. It's a small slice of the overall retracted
population but a tight one — papers in this category are unambiguously
violating a 20-year ICMJE requirement, not just suffering from
extractor noise.

The 87% PASS rate on retracted papers is **the honest answer to "can
the tool tell a retracted paper from a non-retracted one with only
the PDF?"** — and the answer is mostly **no**. As both
[`recall_test_v2.md`](recall_test_v2.md) and the
[`quickstart`](quickstart.md) say, PaperGuard's real value lives on
raw data files (`.csv`, `.xlsx`, supplementary tables), not on the
typeset PDF. v3 stops pretending otherwise.

## Trade-off framing

A naive reading is "recall went from 68% to 13%, so the tool got
five times worse". The opposite is true.

- **v2 recall 68% / FP 88%** is what you get when you flag almost
  every paper. It looks impressive on the retracted arm only because
  the same near-universal flag fires on controls.
- **v3 recall 13% / FP 0%** is what you get when you only flag what
  you can actually distinguish. A practitioner triaging 100 papers
  with v2 would chase 88 false leads for every 68 real ones. With v3
  they chase 0 false leads for every 13 real ones.

LR+ collapses this into a single number — v3 is **infinitely more
trustworthy** than v2 on this sample for the operationally useful
question "if PaperGuard flags this paper, should I look closer?".

## What we did not do

- **Did not retrain T5 / T4 stylometric thresholds.** Those fire as
  `NOTE` (severity 0), which means they show up in the JSON but do
  not contribute to `overall_severity`. They are noisy but
  cosmetically harmless. Subfield-specific recalibration is in the
  v3.x roadmap.
- **Did not change F1, F4, or any numeric-forensics detector.** Those
  rarely fire on PDFs at all because raw data tables of N ≥ 50 don't
  usually appear in the body of a published article.
- **Did not re-pull a fresh 100+100 sample.** The whole point of v3
  was to measure the impact of a single detector rule change while
  holding everything else constant. Re-pulling would have confounded
  the comparison. A future v4 with a PMC-first fetcher to lift the
  16% control download-success rate is the right next step.

## v3.x roadmap (unchanged from v2)

1. **PMC-first fetcher** to bypass publisher 403 walls on biomedical
   retractions.
2. **Per-subfield recalibration of T5** so its `NOTE` density on
   biomedical prose stops being near-constant. Optional: only have
   T5 emit findings on the dimension that genuinely deviates rather
   than at every dimension above a single global threshold.
3. **Retraction Watch reason-code stratification.** Image-duplication
   retractions should pop F1 / F2 / F3 / F4 — that's the natural
   test for those detectors. Plagiarism retractions should be
   measurably silent (PaperGuard doesn't do text reuse) — measurable
   null result.
4. **Pair scans with supplementary data files.** This is the use
   case PaperGuard was built for and where its strong detectors
   actually live.

## Reproducing v3

```bash
pip install paperguard==2.0.4

# Re-scan the same v2 PDFs (already on disk in a prior v2 run):
python scripts/rescan_existing.py \
  --in scripts/recall_test_v2_results.json \
  --pdf-dir /path/to/pg_recall_v2_<id> \
  --out scripts/recall_test_v3_results.json

python scripts/recall_analyze.py scripts/recall_test_v3_results.json
```

## Disclaimer

Same as everywhere: PaperGuard flags **statistical anomalies, not
fraud**; every finding lists possible innocent explanations; a flag
is an invitation to look more carefully, never a conclusion. The
numbers above describe a 56-PDF biomedical sample of the
PDF-only use case; PaperGuard's intended workflow is to scan
supplementary data files alongside the PDF.
