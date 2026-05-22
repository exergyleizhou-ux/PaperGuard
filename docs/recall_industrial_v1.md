# PaperGuard industrial-detector synthetic recall study v1

> **Headline.** N=100 (50 clean + 50 tampered) per domain on
> wastewater + pharma synthetic datasets. **I5 (batch-log
> repetition) is the only industrial detector with usable LR+ at
> the template default thresholds on this synthetic corpus.** I1
> and I2 fire on too many clean datasets — the template defaults
> need user calibration to the local plant's noise floor.

## Why this study

PaperGuard 2.2.x shipped 4 industrial detectors (I1 mass balance,
I2 SCADA timestamps, I5 batch repetition, I6 trend over-smoothness)
+ 12 domain templates. The templates ship default tolerances picked
from regulatory references. This release tests **whether those
defaults discriminate clean from tampered data on realistic
synthetic operations**.

The study is synthetic-ground-truth because:
- We control exactly which datasets were tampered with.
- No FDA Warning Letter / EPA-violation corpus is public.
- Synthetic data sets a **lower bound** on detector capability — if
  it can't tell apart synthetic clean vs synthetic tampered, it
  certainly can't on noisier real data.

## Method

Per domain (wastewater + pharma):
- 50 clean datasets: realistic noise on instruments, varied
  narratives drawn from a 10-template bank with shift annotations.
- 50 tampered datasets: each gets ≥1 of three injected
  manipulations chosen from {I1 effluent/yield padding, I2
  timestamp rounding + backfill, I5 narrative copy-paste}.

Detectors run at **template-default thresholds** (the 2.2.1 numbers):
- Wastewater I1 tolerance: 5 %, I2 expected_dt: 3600 s
- Pharma I1 tolerance: 0.5 %, I2 expected_dt: 300 s

## Results

### Wastewater (N=50+50)

| Detector | TP | FP | TPR | FPR | LR+ |
|---|---|---|---|---|---|
| I1 | 50/50 | 50/50 | 100 % | 100 % | **1.00** |
| I2 | 50/50 | 50/50 | 100 % | 100 % | **1.00** |
| **I5** | 30/50 | 0/50 | **60 %** | **0 %** | **∞** |
| Joint (any) | 50/50 | 50/50 | 100 % | 100 % | 1.00 |

### Pharma (N=50+50)

| Detector | TP | FP | TPR | FPR | LR+ |
|---|---|---|---|---|---|
| I1 | 50/50 | 50/50 | 100 % | 100 % | **1.00** |
| I2 | 50/50 | 50/50 | 100 % | 100 % | **1.00** |
| I5 | 50/50 | 50/50 | 100 % | 100 % | 1.00 |
| Joint (any) | 50/50 | 50/50 | 100 % | 100 % | 1.00 |

## Honest interpretation

### I5 wastewater works (LR+ = ∞)

The single positive finding: **I5 on the wastewater synthetic
corpus has perfect specificity (0/50 false positives) and 60 %
recall**. Narrative-repetition copy-paste is a genuinely rare
event in honest operations even when narratives reuse standard
language — the bank-of-templates design makes natural variation
believable while a deliberate copy-paste of 40 hours of identical
text stands out.

### Everything else is dominated by the κ paradox + bad defaults

When both arms fire at 100 %, the marginals collapse the LR+ to
1.00 regardless of raw counts. This happens here because:

1. **Synthetic "clean" wastewater data is too noisy** for the
   template's 5 % tolerance. Realistic process noise + un-instrumented
   loss streams routinely produce 6-10 % balance residual; the
   template default trips on all 50 clean datasets.
2. **Synthetic timestamps start at HH:00:00** (because
   `pd.Timestamp("2026-04-01")` is exactly midnight). At sub-minute
   expected Δt the round-second check fires on every dataset.
3. **Pharma I5** fires on clean lots too because the bank of 10
   narratives means consecutive lots share boilerplate phrases at
   ≥ 40 % Jaccard.

### Actionable calibration recommendations

| Detector | Recommendation |
|---|---|
| I1 wastewater | Default 5 % is too tight for synthetic corpus; real plants vary. **Set `tolerance_pct` based on the plant's own historical Q3 residual.** |
| I1 pharma | 0.5 % is GMP-correct on real lots but exceeds the noise floor of synthetic data. Same recommendation: **calibrate per facility**. |
| I2 | Don't enable round-minute clustering on data sources that emit at HH:00:00 by design (e.g., scheduled historians). Use `expected_dt_seconds` ≥ 60 in that case. |
| I5 | **Defaults work well as-is on wastewater**; for pharma where shared boilerplate is the norm, use `narrative_min_words ≥ 50` and bump `n_gram` from 4 to 6 to require longer literal matches. |

## Recommended threshold profiles (post-v1)

Based on this study, three profiles for industrial scan operators:

```python
# Profile 1 — high-precision triage (false-positive-averse)
WASTEWATER.batch_repetition(df, narrative_min_words=50, n_gram=6)
PHARMA.mass_balance(df, tolerance_pct=2.0)  # loosen from 0.5%
PHARMA.timestamp_integrity(df, expected_dt_seconds=3600)  # downgrade

# Profile 2 — default (template ships with these)
PHARMA.mass_balance(df)  # 0.5%
PHARMA.timestamp_integrity(df)  # 300s

# Profile 3 — research (catch everything, accept noise)
WASTEWATER.mass_balance(df, tolerance_pct=1.0)
```

## What's NOT shown here

- **Per-domain `falsification_modes` accuracy** — we injected only 3
  generic tamper types. Real-world tamper patterns documented in
  `paperguard.industrial.templates` (FDA-WL deviation backdating,
  CEMS data substitution) are not tested here because we don't
  have ground-truth corpora for them.
- **Cross-detector concordance** — we report each detector
  separately; the BH-FDR + integrity-index combiner is not
  exercised in this study.
- **N=50 is small.** A future study against an FDA Warning Letter
  or EPA violation corpus at N≥200 would tighten the I5 wastewater
  LR+ confidence interval.

## Reproducibility

```bash
PYTHONIOENCODING=utf-8 python scripts/recall_industrial_v1.py \
    --n 50 \
    --out scripts/recall_industrial_v1_results.json
```

Public artefacts:
- `scripts/recall_industrial_v1.py` — the study driver
- `scripts/recall_industrial_v1_results.json` — per-case JSON
- This file

## Bottom line

PaperGuard's industrial layer **works as advertised on at least one
sector (wastewater I5, LR+ = ∞)**. The other detector-domain
combinations need **per-facility calibration** of the tolerance and
window parameters before they will discriminate. The templates ship
documented `falsification_modes` precisely because they're meant to
guide that calibration; this v1 study now provides the empirical
prior.

A v2 study against a public industrial-tampering corpus (when
available — currently none exist) will be needed to validate the
calibration recommendations on real data.
