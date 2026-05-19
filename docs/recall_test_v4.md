# Recall / precision study — v4 (T5 stylometry tightened)

v4 of the PaperGuard recall study. Same 56 PDFs as v2 and v3, same
methodology. The only change since v3 is **PaperGuard 2.0.5**, which
tightens the T5 stylometry detector so it stops emitting NOTE-level
findings on near-every biomedical paper.

The full methodology and original 200-paper sample is in
[`recall_test_v2.md`](recall_test_v2.md); the previous step's
recalibration is in [`recall_test_v3.md`](recall_test_v3.md).

## What changed in code

PaperGuard **2.0.5** retunes T5:

- Per-dimension thresholds raised:
  - methodology density: was `>30%` relative deviation → now `>100%`
  - certainty density: was `>50%` → now `>100%`
  - adjective density: was `>30%` → now `>70%`
- A finding now requires **at least 2 dimensions** to violate
  simultaneously (was 1).

Two new regression tests pin both directions:

- normal biomedical prose ⇒ zero T5 findings (was: near-universal NOTE)
- synthetic Stapel-style text ⇒ still flagged

## Numbers — v3 vs v4

Re-scanned same 56 PDFs.

### Overall severity is unchanged

| Metric | v3 | v4 |
|---|---|---|
| Recall @ sev ≥ 2 | 13% | 13% |
| FP rate @ sev ≥ 2 | 0% | 0% |
| LR+ | ∞ | ∞ |

This is **the expected result**. T5 only ever emitted findings at
`severity = 0 (NOTE)`, which by design does not count toward
`overall_severity` (the report-level rollup). So the tightening
cannot change recall or false-positive rate at the SUSPICIOUS or
CRITICAL thresholds.

### Detector firing totals (sum of findings across all scanned papers)

| Detector | v3 findings | v4 findings | Δ |
|---|---|---|---|
| T3 | 10 | 10 | 0 |
| T5 | ~ (NOTE noise on most papers) | **0** | full cleanup |

The T5 column is the one that matters: in v3 every retracted and
most control papers had at least one T5 NOTE finding cluttering the
JSON output. In v4 there are none. The detector still works (see
the `tests/test_t5_thresholds.py::test_t5_fires_on_stapel_like_text`
regression test where it does trigger on synthetic Stapel-style
text), it just refuses to opine on prose that doesn't actually
deviate meaningfully from the reference distribution.

## Why this matters even though the recall numbers didn't move

The user-facing payoff is **report cleanliness**, not classification
power. Three consequences:

1. **JSON consumers no longer have to filter out T5 noise.** Anyone
   piping `paperguard scan --output-json` into a triage workflow
   gets fewer spurious findings to ignore.
2. **HTML and terminal reports are shorter.** Each T5 NOTE was a
   full panel with four innocent explanations and an academic
   reference. Removing those when they shouldn't fire keeps the
   reader's attention on actual signal.
3. **T5 calibration drift is now self-disciplined.** The previous
   thresholds were tuned on English psychology prose (Markowitz &
   Hancock 2014) and were known to be miscalibrated on biomedical
   writing — but the detector was firing anyway. The new thresholds
   force the detector to stay silent except on genuine outliers,
   which is the correct behaviour when its reference distribution
   doesn't fit the input domain.

## What we did not do (still on the v5 roadmap)

- **PMC-first fetcher is not yet wired into the recall script.**
  The 2.0.5 library now ships `paperguard.fetcher.oa_pdf`, but the
  v2 recall script still uses the old Unpaywall-only resolution.
  Lifting download success rate (16% on controls in v2) is the next
  big-effect step before re-running a real N=100+100 with fresh
  downloads.
- **Subfield-specific T5 reference distributions.** The current
  thresholds are tight enough to stay silent on biomedical writing
  *and* trigger on synthetic Stapel-style text, but they're still
  global. A per-subfield calibration would let T5 work harder
  inside its domain of validity.
- **F1 / F2 / F3 / F4 image forensics on supplementary-data scans.**
  This is the use case PaperGuard's image detectors were really
  built for; the PDF body rarely contains the original figure
  bitmaps at the resolution they were submitted at.

## Reproducing v4

```bash
pip install paperguard==2.0.5

python scripts/rescan_existing.py \
  --in scripts/recall_test_v2_results.json \
  --pdf-dir /path/to/pg_recall_v2_<id> \
  --out scripts/recall_test_v4_results.json

python scripts/recall_analyze.py scripts/recall_test_v4_results.json
```

## Disclaimer

Same as everywhere else: PaperGuard flags **statistical anomalies,
not fraud**; every finding lists possible innocent explanations; a
flag is an invitation to look more carefully, never a conclusion.
This study covers a 56-PDF biomedical sample of the PDF-only use
case; PaperGuard's intended workflow is to scan supplementary data
files alongside the PDF.
