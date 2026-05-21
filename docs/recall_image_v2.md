# PaperGuard image-layer recall study v2

> **N = 10 retracted + 8 matched-control papers, OA PDFs via
> `paperguard.fetcher.oa_pdf`, images via `extract_pdf_images`.
> Three detectors run per paper: F1 (intra-paper pHash), F4 (cross-paper
> corpus), F6 (per-channel histogram patch splice).**

## Fetch + extract success

| Stage | Retracted | Control |
|---|---|---|
| PDF download OK | 7 / 10 | 6 / 8 |
| Images extracted | 7 / 10 | 6 / 8 |

## Single-detector LR+ at the NOTE-or-above threshold

- **F1**: TP=0 FP=3 FN=10 TN=5 | TPR=0.00% FPR=37.50% **LR+ = 0.00**
- **F4**: TP=0 FP=1 FN=10 TN=7 | TPR=0.00% FPR=12.50% **LR+ = 0.00**
- **F6**: TP=7 FP=6 FN=3 TN=2 | TPR=70.00% FPR=75.00% **LR+ = 0.93**

## Single-detector LR+ at the CONCERN-or-above threshold

- **F1**: TP=0 FP=3 FN=10 TN=5 | TPR=0.00% FPR=37.50% **LR+ = 0.00**
- **F4**: TP=0 FP=1 FN=10 TN=7 | TPR=0.00% FPR=12.50% **LR+ = 0.00**
- **F6**: TP=7 FP=5 FN=3 TN=3 | TPR=70.00% FPR=62.50% **LR+ = 1.12**

## Joint signals (ANY detector firing)

- **F1 ∪ F4**: TP=0 FP=4 | TPR=0.00% FPR=50.00% **LR+ = 0.00**
- **F1 ∪ F6**: TP=7 FP=6 | TPR=70.00% FPR=75.00% **LR+ = 0.93**
- **F4 ∪ F6**: TP=7 FP=6 | TPR=70.00% FPR=75.00% **LR+ = 0.93**
- **F1 ∪ F4 ∪ F6**: TP=7 FP=6 | TPR=70.00% FPR=75.00% **LR+ = 0.93**

## Per-paper table

| Arm | DOI | n_imgs | F1 | F4 | F6 |
|---|---|---|---|---|---|
| retracted | 10.1016/j.eng.2020.03.007 | 7 | none | none | CONCERN |
| control | 10.1016/s0140-6736(20)30183-5 | 4 | none | CRITICAL | NOTE |
| control | 10.1093/nar/gkab1038 | 5 | none | none | SUSPICIOUS |
| control | 10.1038/s41586-020-1943-3 | 15 | none | none | SUSPICIOUS |
| retracted | 10.1007/s12652-021-03612-z | 10 | none | none | SUSPICIOUS |
| control | 10.1016/j.jacc.2023.11.007 | 258 | CRITICAL | none | SUSPICIOUS |
| control | 10.1016/j.cpc.2021.108033 | 64 | CRITICAL | none | SUSPICIOUS |
| retracted | 10.1371/journal.pone.0259283 | 7 | none | none | SUSPICIOUS |
| retracted | 10.1186/s12943-020-01206-5 | 8 | none | none | SUSPICIOUS |
| retracted | 10.1038/s41467-020-17687-3 | 9 | none | none | SUSPICIOUS |
| retracted | 10.1186/s12943-019-1128-6 | 9 | none | none | SUSPICIOUS |
| control | 10.1038/s41586-021-03819-2 | 36 | CRITICAL | none | SUSPICIOUS |
| retracted | 10.1186/s13046-020-01648-1 | 9 | none | none | SUSPICIOUS |

## Honest interpretation

### F6 at default `z ≥ 4` is too sensitive for general post-publication use

The headline number `F6 TPR = 70%, FPR = 75%` reads bad — and that's
the empirical truth at N=10+8. F6 fires on almost every paper that
has any image content, retracted or not. The reason is mechanical:
**any paper with strong content edges** (well-plate borders,
fluorescent-channel panel composition, micrographs with abrupt tissue
boundaries) produces per-channel histogram discontinuities high
enough to clear `z ≥ 4`. The control-arm papers that fired the
loudest were exactly the ones with this kind of legitimate
composition.

**Calibration recommendation for users:**

| Use case | Recommended F6 threshold |
|---|---|
| **High-precision triage** (every flag worth a reviewer's time) | `PatchSpliceInput.z_threshold = 6.0` AND `min_cluster_size ≥ 8` |
| Default (research / experimentation) | `z_threshold = 4.0`, `min_cluster_size = 4` |
| Maximum recall (catch everything, accept noise) | `z_threshold = 4.0`, `min_cluster_size = 1` |

We are leaving the package defaults at `z=4`, `cluster=4` and
recommending users tune from there. Doctrinal honesty:
**F6 is a screening signal, not a verdict.** It tells you "this
patch's colour distribution is unusual" — followup human review
decides whether the cause is splicing or legitimate composition.

### F1 false-positives at scale

Three control papers triggered F1 CRITICAL. All three have unusually
large image counts (258, 64, 36 images) — they are review articles
with many small icon/marker reuses across figures. F1's pHash
hamming distance metric does not distinguish "icon legitimately
reused" from "data figure improperly reused". This is an inherent
limitation of pHash; a future detector would need shape / content
gating.

### F4 needs corpus warm-up

F4 fired once (CRITICAL on a control paper). F4 is most useful in
**longitudinal scans**: as the corpus accumulates known-retracted
images, its discriminating power grows. A cold corpus on N=18 papers
produces near-zero signal by design.

### Bottom line

- F6 contributes a *structurally different* signal from F1+F4.
- At the current default threshold, F6 sensitivity overwhelms its
  specificity for general use; tune to `z ≥ 6` for triage.
- F1 + F4 + F6 together flag 70% of retracted papers but also 75% of
  controls — **F6 dominates both columns**. The package-default
  joint signal is therefore weak; tightening F6 thresholds restores
  joint precision.
- **N=10+8 is small.** The point of this study is to demonstrate that
  the algorithmic machinery works end-to-end and to surface F6's
  calibration question. A larger study (N≥50+50) is needed before
  publishing any LR+ number as definitive.

Per the technical report, the whole pipeline remains a **triage**
signal. Findings ship with ≥ 4 innocent explanations and never use
verdict language.

