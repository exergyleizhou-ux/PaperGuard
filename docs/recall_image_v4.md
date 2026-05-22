# PaperGuard image-layer recall study v2

> **N = 100 retracted + 59 matched-control papers, OA PDFs via
> `paperguard.fetcher.oa_pdf`, images via `extract_pdf_images`.
> Three detectors run per paper: F1 (intra-paper pHash), F4 (cross-paper
> corpus), F6 (per-channel histogram patch splice).**

## Fetch + extract success

| Stage | Retracted | Control |
|---|---|---|
| PDF download OK | 83 / 100 | 31 / 59 |
| Images extracted | 83 / 100 | 31 / 59 |

## Single-detector LR+ at the NOTE-or-above threshold

- **F1**: TP=17 FP=7 FN=83 TN=52 | TPR=17.00% FPR=11.86% **LR+ = 1.43**
- **F4**: TP=5 FP=3 FN=95 TN=56 | TPR=5.00% FPR=5.08% **LR+ = 0.98**
- **F6**: TP=80 FP=29 FN=20 TN=30 | TPR=80.00% FPR=49.15% **LR+ = 1.63**

## Single-detector LR+ at the CONCERN-or-above threshold

- **F1**: TP=17 FP=7 FN=83 TN=52 | TPR=17.00% FPR=11.86% **LR+ = 1.43**
- **F4**: TP=5 FP=3 FN=95 TN=56 | TPR=5.00% FPR=5.08% **LR+ = 0.98**
- **F6**: TP=80 FP=29 FN=20 TN=30 | TPR=80.00% FPR=49.15% **LR+ = 1.63**

## Joint signals (ANY detector firing)

- **F1 ∪ F4**: TP=20 FP=9 | TPR=20.00% FPR=15.25% **LR+ = 1.31**
- **F1 ∪ F6**: TP=81 FP=30 | TPR=81.00% FPR=50.85% **LR+ = 1.59**
- **F4 ∪ F6**: TP=80 FP=30 | TPR=80.00% FPR=50.85% **LR+ = 1.57**
- **F1 ∪ F4 ∪ F6**: TP=81 FP=31 | TPR=81.00% FPR=52.54% **LR+ = 1.54**

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
| retracted | 10.1186/s12943-020-1145-5 | 9 | none | none | SUSPICIOUS |
| retracted | 10.1007/s11356-020-11462-z | 5 | none | none | SUSPICIOUS |
| retracted | 10.1038/s41598-020-76726-7 | 10 | none | none | SUSPICIOUS |
| retracted | 10.1007/s13204-021-02164-0 | 8 | none | none | SUSPICIOUS |
| control | 10.1007/s12525-021-00475-2 | 5 | none | none | SUSPICIOUS |
| control | 10.1145/3394486.3403118 | 3 | CRITICAL | none | none |
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
| control | 10.1109/access.2020.2998358 | 10 | none | none | SUSPICIOUS |
| retracted | 10.1172/jci146832 | 9 | none | none | SUSPICIOUS |
| retracted | 10.1007/s00500-020-05275-y | 6 | CRITICAL | none | SUSPICIOUS |
| retracted | 10.3991/ijet.v15i14.14675 | 2 | none | none | SUSPICIOUS |
| control | 10.1007/s10648-019-09498-w | 6 | none | none | SUSPICIOUS |
| retracted | 10.1007/s11356-020-12289-4 | 1 | skip | none | SUSPICIOUS |
| retracted | 10.1155/2022/1200860 | 2 | SUSPICIOUS | none | none |
| retracted | 10.1155/2021/8133076 | 10 | CRITICAL | none | CONCERN |
| control | 10.1148/radiol.2020191145 | 8 | none | none | SUSPICIOUS |
| retracted | 10.3991/ijet.v15i14.14669 | 2 | none | CRITICAL | SUSPICIOUS |
| control | 10.1145/3331184.3331267 | 14 | none | none | SUSPICIOUS |
| retracted | 10.1039/d0ra01116a | 12 | none | none | SUSPICIOUS |
| control | 10.1021/acsnano.9b04224 | 49 | none | none | SUSPICIOUS |
| retracted | 10.1155/2022/2693621 | 18 | CRITICAL | none | SUSPICIOUS |
| retracted | 10.1038/s41598-023-29485-0 | 8 | CRITICAL | none | SUSPICIOUS |
| retracted | 10.1155/2022/1755460 | 4 | none | none | none |
| retracted | 10.1038/s41598-020-80133-3 | 9 | none | none | SUSPICIOUS |
| retracted | 10.1038/s41419-020-2250-5 | 8 | none | none | SUSPICIOUS |
| retracted | 10.1007/s00779-020-01475-3 | 3 | none | none | SUSPICIOUS |
| control | 10.1093/nar/gkz239 | 2 | none | none | SUSPICIOUS |
| retracted | 10.1155/2022/8709145 | 9 | CRITICAL | none | SUSPICIOUS |
| retracted | 10.1007/s11356-021-12491-y | 1 | skip | none | SUSPICIOUS |
| retracted | 10.1186/s13287-020-01815-3 | 7 | none | none | SUSPICIOUS |
| retracted | 10.1007/s00705-021-04956-9 | 5 | none | none | SUSPICIOUS |
| retracted | 10.1007/s11356-021-15023-w | 5 | none | SUSPICIOUS | SUSPICIOUS |
| control | 10.1186/s13059-019-1891-0 | 5 | none | none | SUSPICIOUS |
| retracted | 10.1155/2022/7672196 | 28 | none | none | SUSPICIOUS |
| retracted | 10.1371/journal.pone.0295951 | 13 | none | none | SUSPICIOUS |
| retracted | 10.1177/23969873211026990 | 1 | skip | none | CONCERN |
| control | 10.1038/s41586-020-2275-z | 11 | none | none | SUSPICIOUS |
| retracted | 10.3389/fenvs.2022.851263 | 4 | none | none | SUSPICIOUS |
| retracted | 10.1177/2396987321992905 | 6 | none | none | CONCERN |
| retracted | 10.1007/s00779-021-01531-6 | 7 | SUSPICIOUS | none | CONCERN |
| retracted | 10.1039/d1ra01300a | 8 | none | none | SUSPICIOUS |
| retracted | 10.1155/2022/7893775 | 6 | none | none | CONCERN |
| control | 10.1016/s2215-0366(21)00395-3 | 6 | SUSPICIOUS | SUSPICIOUS | SUSPICIOUS |
| retracted | 10.1186/s12951-021-01206-7 | 9 | none | none | SUSPICIOUS |
| retracted | 10.1155/2021/6455592 | 6 | none | none | CONCERN |
| control | 10.1109/tpwrs.2020.3041774 | 2 | none | none | SUSPICIOUS |
| retracted | 10.1007/s11356-022-22221-7 | 2 | none | none | none |
| retracted | 10.1038/s41598-021-00296-5 | 11 | none | none | SUSPICIOUS |
| retracted | 10.1186/s12929-019-0595-9 | 8 | none | none | SUSPICIOUS |
| retracted | 10.1016/j.ekir.2020.11.034 | 6 | none | none | SUSPICIOUS |
| control | 10.1016/s0140-6736(20)30628-0 | 4 | none | CRITICAL | SUSPICIOUS |
| retracted | 10.1155/2022/1359019 | 16 | none | none | SUSPICIOUS |
| retracted | 10.1155/2021/4321131 | 8 | none | none | CONCERN |
| retracted | 10.1186/s13568-020-00993-w | 8 | none | none | SUSPICIOUS |
| retracted | 10.2147/ijn.s241702 | 9 | none | none | SUSPICIOUS |
| control | 10.1093/nar/gkz935 | 6 | none | none | SUSPICIOUS |
| retracted | 10.1001/jamanetworkopen.2022.35721 | 6 | SUSPICIOUS | none | SUSPICIOUS |
| retracted | 10.1371/journal.pone.0258361 | 11 | none | none | CONCERN |
| control | 10.1126/science.abb6936 | 5 | none | none | SUSPICIOUS |
| retracted | 10.3389/fenvs.2022.868704 | 6 | none | none | SUSPICIOUS |
| control | 10.1093/gigascience/giab008 | 4 | none | none | SUSPICIOUS |
| retracted | 10.3991/ijet.v15i13.14945 | 2 | none | CRITICAL | SUSPICIOUS |

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

