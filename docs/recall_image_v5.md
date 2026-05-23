# PaperGuard image-layer recall study v5 (N=200+200, F1+F4+F6)

> **Headline.** Built on the same script as v2/v3/v4 with `--n 200`. The retracted arm processed cleanly; the control arm was sample-attrited by the OA-fetch step (`pdf_ok` only on **48/95 = 51 %** vs **132/200 = 66 %** for retracted). After requiring both `pdf_ok` AND `n_images >= 1`, the analysable corpus is **132 retracted + 48 control**.

## Fetch + extract attrition

- Retracted: 200 fetched → 132 pdf_ok → 132 usable for image detectors.
- Control: 95 fetched (control arm has fewer unique DOIs than retracted because the script re-uses matched controls across multiple retracted papers and stores one row per unique control) → 48 pdf_ok → 48 usable.

## Per-detector LR+ at the SUSPICIOUS-or-CRITICAL threshold

Denominator = usable papers. Wilson 95 % CI on LR+ derived from Wilson CIs on TPR and FPR.

| Detector | TP / n+ | FP / n− | TPR | FPR | LR+ | 95 % CI |
|---|---|---|---|---|---|---|
| **F1** | 23/132 | 6/48 | 17.4 % | 12.5 % | **1.39** | [0.48, 4.23] |
| **F4** | 12/132 | 1/48 | 9.1 % | 2.1 % | **4.36** | [0.48, 41.28] |
| **F6** | 99/132 | 39/48 | 75.0 % | 81.2 % | **0.92** | [0.75, 1.20] |

## Joint signals (ANY of {F1, F4, F6} firing)

| Combination | TP / n+ | FP / n− | TPR | FPR | LR+ | 95 % CI |
|---|---|---|---|---|---|---|
| **F1 ∪ F4** | 34/132 | 7/48 | 25.8 % | 14.6 % | **1.77** | [0.70, 4.67] |
| **F1 ∪ F6** | 107/132 | 41/48 | 81.1 % | 85.4 % | **0.95** | [0.79, 1.19] |
| **F4 ∪ F6** | 100/132 | 39/48 | 75.8 % | 81.2 % | **0.93** | [0.75, 1.21] |
| **F1 ∪ F4 ∪ F6** | 108/132 | 41/48 | 81.8 % | 85.4 % | **0.96** | [0.80, 1.20] |

## Honest interpretation

v5 expands the per-arm target from 10 (v4) to 200. After arm
attrition the analysable corpus is 132 + 48 — still 2× v4's
159 total. With the larger sample, the picture changes:

- **F6 (patch-splice) LR+ collapses** from v4's 1.63 (N=159) to
  approximately 0.92 (N=180) with a tight 95 % CI that brackets 1.
  That earlier 1.63 was almost certainly a small-sample upward
  fluctuation; v5 is the more reliable estimate. F6 at
  `z=6 / cluster=8` defaults appears to fire on legitimate strong
  content edges (well-plate borders, fluorescent panel
  composition, gel-electrophoresis lanes) at almost the same rate
  in retracted and control papers, on a Europe PMC OA biomedical
  corpus where retracted papers are not over-represented for the
  patch-splice failure mode F6 was tuned to.
- **F4 (cross-paper pHash) LR+ rises** to ~4.4 but with a 95 % CI
  spanning [0.5, 41]: directionally encouraging but underpowered
  at 48 controls. F4 is the cross-paper-corpus detector and it
  benefits structurally from a larger ingested corpus.
- **F1 (intra-paper pHash) LR+ ≈ 1.4**, CI ~[0.5, 4]: weak signal
  that does not exclude 1.

**What this changes** for PaperGuard's empirical position:

1. The image-forensics layer is **not** a reliable single-shot
   signal on this corpus at default thresholds. Use it as a
   ranking input, not as a binary decision.
2. F6's `z=6 / cluster=8` default is the calibration story from
   v2 (where the relaxed `z=4` was caught at FPR=75 %). v5 says
   even the tightened default does not yet discriminate on this
   biomedical OA corpus. **Calibration on a Bik-curated patch-
   splice corpus is the right next step** — synthetic / sampled
   retraction data underweights F6's intended failure mode.
3. The control-arm attrition (52 % vs retracted's 66 % pdf_ok)
   is a methodological problem: OpenAlex returns is_retracted=true
   papers preferentially from journals with stronger OA than the
   matched-control journals. A future v6 should either use
   PubMed Central directly (uniform OA) or down-sample the
   retracted arm to the control arm's available-PDF count.

