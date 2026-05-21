# Detector Reference

PaperGuard 2.1.x ships **34 built-in detectors** organized into 8
clusters. Each has its own deep-dive page below. The dedicated
LLM-text guide [`../llm_detection_v2.md`](../llm_detection_v2.md)
covers T6 + T7 + T8 together with empirical calibration.

## Index by cluster

### Digit distribution / numeric forensics
- [A1 Terminal Digit Distribution](A1.md) — χ²(9) on last significant digit
- [A2 Benford First-Digit](A2.md) — χ²(8) on first digit, dynamic-range gated
- [A5 Decimal Fraction Consistency](A5.md) — repeated `.NN` fragment detection
- [A6 Implausible Values](A6.md) — sentinel values + column-name range heuristics
- [A7 Last-Digit 0/5 Preference](A7.md) — bidirectional binomial on P(末位∈{0,5})

### Inter-column relations
- [A3 Inter-Column Arithmetic](A3.md) — constant Δ or ratio between columns

### Summary-statistic consistency
- [B1 GRIM](B1.md) — mean × N must round to integer for integer data
- [B4 Statcheck](B4.md) — recompute reported t/F/χ²/r/z/Q p-values
  ([B4 vs scipy cross-validation: recall 100 %, decision-flip 94 %](../crossval_statcheck.md))
- [B5 TIVA](B5.md) — Var(z) across studies should be ≥ 1
- [B6 GRIMMER](B6.md) — extends GRIM to SD consistency
- [B7 P-Curve](B7.md) — left-skewed or near-α pile-up = p-hacking
- [B8 SPRITE](B8.md) — iterative integer-sample reconstruction

### RCT integrity
- [C1 Carlisle Baseline-Balance](C1.md) — Welch t per variable + Stouffer

### Variance / independence structure
- [D1 Residual Smoothness](D1.md) — block-variance stability check
- [D2 Missing-Data Pattern](D2.md) — 0 % missing + low column-σ variation
- ⭐ [E1 ICC Independence](E1.md) — Heathers 2024 ICRP (new in 2.0.14)

### Image forensics
- [F1 pHash Cross-Image](F1.md) — Hamming-distance on perceptual hash
- [F2 Internal Image Duplication](F2.md) — ORB+RANSAC affine consensus
- [F3 Splice / Copy-Move](F3.md) — block-statistic + translation vote
- [F4 Cross-Paper Image Duplication](F4.md) — persistent pHash SQLite store
- [F5 EXIF Cross-Image Clustering](F5.md) — multi-image timeline + camera consistency
- ⭐ [F6 Per-Channel Histogram Patch Splice](F6.md) — Bik 2016 mechanised
  (new in 2.1.7; [empirically calibrated in 2.1.9](../recall_image_v2.md))

### Metadata forensics
- [G1 EXIF Temporal](G1.md) — per-image acquisition time vs claimed dates
- [G3 Docx rsid](G3.md) — python-docx / pandoc vs Word edit detection
- [G4 File Metadata](G4.md) — creator / created / revision audit

### Paper-mill graph
- [M1 Paper-Mill Graph](M1.md) — co-authorship community detection

### Text / trial / LLM forensics
- [T1 Text Similarity (n-gram)](T1.md) — Jaccard against user corpus
- [T2 Clinical-Trial Outcome](T2.md) — paper vs ClinicalTrials.gov outcome
- [T3 Data Availability + Ethics](T3.md) — ICMJE / FAIR / NCT registration
- [T4 Tortured Phrases](T4.md) — paper-mill MT signatures (PPS dict)
- [T5 Stylometry](T5.md) — Stapel linguistic fingerprint
- [T6 AI-Generated Text — lexical dictionary](T6.md) — phrase signature + dynamic dict
  ([empirically: LR+ = ∞ at 0.001 threshold on N=200](../recall_test_v10.md))
- ⭐ [T7 LLM Perplexity proxy](T7.md) — continuation logprobs (new in 2.0.15;
  needs logprobs-capable endpoint)
- ⭐ [T8 DetectGPT-style curvature](T8.md) — paraphrase + naturalness score
  (new in 2.0.16; [needs GPT-4-class endpoint](../t8_endpoint_limitation.md))

## How to read a detector page

Each page has:

1. **What it detects** — one paragraph
2. **Method** — algorithm + thresholds (live in source file docstring)
3. **Inputs** — what data shape it expects
4. **Severity ladder** — how findings escalate
5. **Innocent explanations** — non-fraud reasons it might fire
6. **Known false positives / negatives**
7. **Academic basis** — citation
8. **Source** — path to implementation
9. **Calibration & empirical evidence** — links to empirical studies

## See also

- [docs/INDEX.md](../INDEX.md) — central documentation directory
- [LLM-detection guide](../llm_detection_v2.md) — T6 / T7 / T8 together
- [Technical report](../paperguard_technical_report.md) — 7-section overview
