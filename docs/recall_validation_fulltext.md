# Full-text recall validation on retracted papers (2026-05-29)

First test that exercises detectors on **full text** (via Europe PMC OA), not
just abstracts. This is a diagnostic for the "firepower" roadmap: it locates
exactly where recall is missing.

## Method
- 40 retracted (`PUB_TYPE:"Retracted Publication"`, OA, in-EPMC) + 40 control
  (OA research-articles, in-EPMC, not retracted, 2018–2023).
- Detectors run on full text, flag = severity ≥ CONCERN: B4 statcheck,
  T4 tortured phrases, T6 lexical, T9 classifier.
- Reproduce: `python scripts/validate_recall_fulltext.py --n 40`

## Results

| Detector | recall % (retracted) | FP % (control) | LR+ |
|---|---|---|---|
| **T4 tortured phrases** | 10.0 | 5.0 | **2.00** |
| B4 statcheck | 0.0 | 2.5 | 0.00 |
| T6 lexical | 0.0 | 0.0 | — |
| T9 classifier | 50.0 | 52.5 | 0.95 |
| any | 50.0 | 60.0 | 0.83 |

## Diagnosis — where the firepower is missing
1. **T4 is the only discriminating detector (LR+ 2.0).** The paper-mill
   tortured-phrase signal is real but modest; worth strengthening.
2. **B4 statcheck recall = 0** — caught no retracted paper. Either statistic
   extraction from JATS-stripped full text is failing, or this retraction
   sample is not "statistical-error" type. **Highest-priority gap to fix:**
   statcheck should be a primary fabrication catcher.
3. **T9 is non-discriminative on full text (50 % vs 52 %).** Root cause: T9
   takes the *max* segment probability; over a many-segment full paper the max
   is almost always high (a multiple-comparisons artifact). T9 was calibrated
   for abstract-length text. **Fix: density/fraction-based aggregation for long
   documents, not max.**
4. **The strongest anti-fabrication families were not exercised here:** numeric
   recompute (GRIM/GRIMMER/SPRITE/Carlisle on reported means/SDs/tables) and
   image forensics (F1–F7 on figures). These need table/figure extraction, the
   next pipeline to build.

## Firepower roadmap priorities (from this diagnostic)
1. Fix T9 full-text aggregation (density, not max) → restore discrimination.
2. Investigate + strengthen statcheck recall on full text.
3. Build figure/data extraction so image + numeric detectors can run on full
   papers (where real data fabrication lives).

Aggregate only; no per-paper or per-author verdicts.
