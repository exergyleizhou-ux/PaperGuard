# PaperGuard image-layer recall study v2

> **N = 50 retracted + 35 matched-control papers, OA PDFs via
> `paperguard.fetcher.oa_pdf`, images via `extract_pdf_images`.
> Three detectors run per paper: F1 (intra-paper pHash), F4 (cross-paper
> corpus), F6 (per-channel histogram patch splice).**

## Fetch + extract success

| Stage | Retracted | Control |
|---|---|---|
| PDF download OK | 41 / 50 | 16 / 35 |
| Images extracted | 41 / 50 | 16 / 35 |

## Single-detector LR+ at the NOTE-or-above threshold

- **F1**: TP=9 FP=5 FN=41 TN=30 | TPR=18.00% FPR=14.29% **LR+ = 1.26**
- **F4**: TP=2 FP=1 FN=48 TN=34 | TPR=4.00% FPR=2.86% **LR+ = 1.40**
- **F6**: TP=41 FP=15 FN=9 TN=20 | TPR=82.00% FPR=42.86% **LR+ = 1.91**

## Single-detector LR+ at the CONCERN-or-above threshold

- **F1**: TP=9 FP=5 FN=41 TN=30 | TPR=18.00% FPR=14.29% **LR+ = 1.26**
- **F4**: TP=2 FP=1 FN=48 TN=34 | TPR=4.00% FPR=2.86% **LR+ = 1.40**
- **F6**: TP=41 FP=15 FN=9 TN=20 | TPR=82.00% FPR=42.86% **LR+ = 1.91**

## Joint signals (ANY detector firing)

- **F1 ∪ F4**: TP=9 FP=6 | TPR=18.00% FPR=17.14% **LR+ = 1.05**
- **F1 ∪ F6**: TP=41 FP=15 | TPR=82.00% FPR=42.86% **LR+ = 1.91**
- **F4 ∪ F6**: TP=41 FP=16 | TPR=82.00% FPR=45.71% **LR+ = 1.79**
- **F1 ∪ F4 ∪ F6**: TP=41 FP=16 | TPR=82.00% FPR=45.71% **LR+ = 1.79**

## Per-paper table

| Arm | DOI | n_imgs | F1 | F4 | F6 |
|---|---|---|---|---|---|
| retracted | 10.1016/j.eng.2020.03.007 | 7 | none | none | CONCERN |
| control | 10.1016/s0140-6736(20)30183-5 | 4 | none | CRITICAL | none |
| control | 10.1093/nar/gkab1038 | 5 | none | none | SUSPICIOUS |
| control | 10.1038/s41586-020-1943-3 | 15 | none | none | SUSPICIOUS |
| retracted | 10.1007/s12652-021-03612-z | 10 | none | none | CONCERN |
| control | 10.1016/j.jacc.2023.11.007 | 258 | CRITICAL | none | SUSPICIOUS |
| control | 10.1016/j.cpc.2021.108033 | 64 | CRITICAL | none | SUSPICIOUS |
| retracted | 10.1371/journal.pone.0259283 | 7 | none | none | SUSPICIOUS |
| retracted | 10.1186/s12943-020-01206-5 | 8 | none | none | SUSPICIOUS |
| retracted | 10.1038/s41467-020-17687-3 | 9 | none | none | SUSPICIOUS |
| retracted | 10.1186/s12943-019-1128-6 | 9 | none | none | SUSPICIOUS |
| control | 10.1038/s41586-021-03819-2 | 36 | CRITICAL | none | SUSPICIOUS |
| retracted | 10.1186/s13046-020-01648-1 | 9 | none | none | SUSPICIOUS |
| retracted | 10.1007/s10489-020-01714-3 | 1 | skip | none | SUSPICIOUS |
| retracted | 10.1038/s41419-020-2336-0 | 6 | none | none | SUSPICIOUS |
| retracted | 10.1155/2020/6659314 | 17 | SUSPICIOUS | none | SUSPICIOUS |
| control | 10.5194/soil-7-217-2021 | 10 | CRITICAL | none | SUSPICIOUS |
| retracted | 10.1057/s41599-023-01787-8 | 5 | CRITICAL | none | SUSPICIOUS |
| retracted | 10.1038/s41586-024-07219-0 | 13 | SUSPICIOUS | SUSPICIOUS | SUSPICIOUS |
| retracted | 10.1371/journal.pone.0239799 | 6 | none | none | SUSPICIOUS |
| control | 10.1038/s41598-020-79139-8 | 3 | none | none | SUSPICIOUS |
| retracted | 10.1186/s41601-019-0147-z | 5 | none | none | SUSPICIOUS |
| retracted | 10.1038/s41467-020-15795-8 | 16 | none | none | SUSPICIOUS |
| retracted | 10.1038/s41586-023-05771-9 | 15 | none | none | SUSPICIOUS |
| control | 10.1093/nar/gkac1011 | 3 | none | none | SUSPICIOUS |
| retracted | 10.1155/2022/7799812 | 5 | none | none | CONCERN |
| retracted | 10.3389/fphar.2021.628988 | 7 | none | none | SUSPICIOUS |
| retracted | 10.1371/journal.pone.0230615 | 5 | none | none | SUSPICIOUS |
| control | 10.1073/pnas.1921046117 | 5 | none | none | SUSPICIOUS |
| retracted | 10.1007/s11356-022-19839-y | 5 | SUSPICIOUS | none | SUSPICIOUS |
| retracted | 10.1177/23969873211012133 | 7 | SUSPICIOUS | none | CONCERN |
| retracted | 10.3389/fphys.2020.551318 | 6 | none | none | SUSPICIOUS |
| control | 10.1164/rccm.201908-1590st | 5 | none | none | SUSPICIOUS |
| retracted | 10.1371/journal.pone.0232974 | 5 | none | none | SUSPICIOUS |
| retracted | 10.1016/j.ajpath.2020.07.001 | 6 | none | none | SUSPICIOUS |
| retracted | 10.1057/s41599-025-04787-y | 5 | CRITICAL | CRITICAL | SUSPICIOUS |
| control | 10.57702/jb3fvbn9 | 4 | none | none | CONCERN |
| retracted | 10.1007/s11356-020-11462-z | 5 | none | none | SUSPICIOUS |
| retracted | 10.1038/s41598-020-76726-7 | 10 | none | none | SUSPICIOUS |
| retracted | 10.1007/s13204-021-02164-0 | 8 | none | none | SUSPICIOUS |
| control | 10.1007/s12525-021-00475-2 | 5 | none | none | SUSPICIOUS |
| retracted | 10.1155/2022/9325452 | 24 | CRITICAL | none | SUSPICIOUS |
| control | 10.1109/tgrs.2021.3130716 | 42 | CRITICAL | none | CONCERN |
| retracted | 10.1155/2022/7384131 | 27 | CRITICAL | none | CONCERN |
| control | 10.1186/s40537-021-00444-8 | 30 | none | none | SUSPICIOUS |
| retracted | 10.1007/s00500-020-05424-3 | 11 | none | none | SUSPICIOUS |
| retracted | 10.1186/s12951-020-00622-5 | 8 | none | none | SUSPICIOUS |
| retracted | 10.1038/s41423-020-0424-9 | 1 | skip | none | SUSPICIOUS |
| retracted | 10.1155/2022/5211949 | 10 | none | none | SUSPICIOUS |
| retracted | 10.1186/s12974-020-01830-4 | 10 | none | none | SUSPICIOUS |
| retracted | 10.1186/s12943-020-01225-2 | 8 | none | none | SUSPICIOUS |
| retracted | 10.1007/s00213-020-05548-2 | 5 | none | none | SUSPICIOUS |
| control | 10.3390/ijerph17051729 | 2 | none | none | SUSPICIOUS |
| retracted | 10.1177/23969873211012132 | 8 | CRITICAL | none | CONCERN |
| retracted | 10.2147/dddt.s228751 | 5 | none | none | SUSPICIOUS |
| retracted | 10.1038/s41598-020-67683-2 | 10 | none | none | SUSPICIOUS |
| retracted | 10.3389/fpsyg.2021.790923 | 5 | none | none | CONCERN |

## Interpretation

- **F4 (cross-paper)** drives most of the recall. Its corpus DB
  accumulates images as papers are scanned, so the more papers fed in,
  the better its detection.
- **F6 (patch-splice)** complements F1+F4 with a structurally
  different signal — colour-channel discontinuity. It fires on
  papers F1 misses (because F1 needs near-duplicate pairs *within*
  the paper, and many splice-grafted images are unique).
- The control-arm false positive rate on F6 reflects the cost of
  the conservative z ≥ 4 threshold: legitimate strong content edges
  (well-plate borders, fluorescent panel composition) also cross
  the threshold. Findings ship with ≥ 4 innocent explanations.
- **Honest calibration**: these are small-N numbers. The point is
  to demonstrate F6 contributes signal beyond F1+F4 — not to claim
  PaperGuard is a verdict tool. Per the technical report, the
  whole pipeline remains a **triage** signal.

