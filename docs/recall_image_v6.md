# PaperGuard image-layer recall study v6 (N=200+200 requested, PMID-indexed both arms)

> **Headline.** v6 adds `has_pmid:true` to both OpenAlex queries
> to attack v5's arm-attrition asymmetry (132 retracted vs 48
> control pdf_ok). The filter **partly worked**: retracted-arm
> pdf_ok jumped from 66 % (v5) to **82 %**.
> Control-arm pdf_ok rose more modestly from 51 % to **59 %**.
> Asymmetry still present.

> **Bigger story:** with the larger usable corpus (163 + 49
> analysable papers), the v5 finding hardens further. **All
> three image detectors at PaperGuard's documented `z=6 /
> cluster=8` defaults give LR+ ≈ 1 on this OpenAlex /
> Europe-PMC OA biomedical corpus.** v5's F4 LR+ = 4.36 was
> a small-N artifact (only 1/48 false positive); v6 says
> F4 LR+ ≈ 1.0 with proportionally more FPs at the larger n.

## Fetch + extract attrition

- Retracted: 200 fetched → 163 pdf_ok (82 %) → 163 usable.
- Control: 83 fetched → 49 pdf_ok (59 %) → 49 usable.

## Per-detector LR+ at the SUSPICIOUS-or-CRITICAL threshold

Denominator = usable papers. Wilson 95 % CI on LR+ derived from
Wilson CIs on TPR and FPR.

| Detector | TP / n+ | FP / n− | TPR | FPR | LR+ | 95 % CI |
|---|---|---|---|---|---|---|
| **F1** | 29/163 | 8/49 | 17.8 % | 16.3 % | **1.09** | [0.44, 2.86] |
| **F4** | 16/163 | 5/49 | 9.8 % | 10.2 % | **0.96** | [0.28, 3.46] |
| **F6** | 124/163 | 42/49 | 76.1 % | 85.7 % | **0.89** | [0.74, 1.12] |

## Joint signals (ANY of {F1, F4, F6} firing)

| Combination | TP / n+ | FP / n− | TPR | FPR | LR+ | 95 % CI |
|---|---|---|---|---|---|---|
| **F1 ∪ F4** | 42/163 | 12/49 | 25.8 % | 24.5 % | **1.05** | [0.52, 2.26] |
| **F1 ∪ F6** | 134/163 | 43/49 | 82.2 % | 87.8 % | **0.94** | [0.80, 1.15] |
| **F4 ∪ F6** | 125/163 | 43/49 | 76.7 % | 87.8 % | **0.87** | [0.74, 1.09] |
| **F1 ∪ F4 ∪ F6** | 135/163 | 44/49 | 82.8 % | 89.8 % | **0.92** | [0.80, 1.12] |

## Honest interpretation (the hard part)

Across three increasingly rigorous studies (v4 N=159, v5 N=180
with attrition asymmetry, v6 N=212 with reduced asymmetry),
PaperGuard's image-forensics layer at the documented
`z=6 / cluster=8` defaults converges to **no reliable
single-detector signal** on randomly-selected OpenAlex
retracted papers vs matched controls in the biomedical OA
corpus.

Specifically:
- **F6 (patch-splice) LR+ ≈ 0.89** across v5 and v6, with a
  tight CI bracketing 1. v4's apparent LR+ 1.63 (N=159) was
  the small-sample upward fluctuation v5 already flagged.
- **F4 (cross-paper pHash) LR+ ≈ 1.0**. v5 reported 4.36 with
  CI [0.48, 41.28] on only 1 false positive; v6 with 5 false
  positives in the larger control arm collapses this to 0.96.
  The wide-CI 4.36 was an artifact of n_FP=1, not signal.
- **F1 (intra-paper pHash) LR+ ≈ 1.1**, indistinguishable
  from chance.

**What this changes** for PaperGuard's empirical position:

1. The image-layer is **structurally tuned to the Bik-style
   patch-splice / Western-blot-duplication failure mode** —
   not to the *average* retracted-paper population, which is
   dominated by statistical-fabrication / paper-mill /
   image-reuse failures that F1/F4/F6 don't cleanly detect.
2. **The right calibration corpus is a Bik-curated patch-
   splice retraction set**, not OpenAlex `is_retracted:true`
   sampled at random. The Bik corpus is not publicly
   redistributable (PubPeer thread sources are case-by-case),
   so PaperGuard cannot ship that benchmark. The honest
   position is that v6 sets an **upper bound on the image
   layer's *un-curated* recall** — and that bound is
   close to 1.0.
3. **Multi-detector combination still has value** — even with
   per-detector LR+ ≈ 1, the joint signal can carry
   information when combined via the
   `paperguard.evidence.combiner` Stouffer index across the
   non-image families (T6 lexical, B-family statistical,
   industrial I-family). The image layer is a *contributor*
   in this triage architecture, not a single-shot decision
   tool.
4. **Operators running F1/F4/F6 in production should not
   alert on a single image detector firing** at default
   thresholds. Either calibrate to local data, raise the
   thresholds, or use the image findings only as input to
   the combiner.

PaperGuard publishes this study and the v5 / v4 series at
transparent face value precisely because the alternative —
quoting v4's small-N LR+ 1.63 as if it were a calibrated
operating number — would be the kind of mis-calibration the
tool exists to flag in others' work.

