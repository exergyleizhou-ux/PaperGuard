# Detector Reference

PaperGuard 0.9.0+ ships with **29 detectors** organized into 7 clusters.
Each detector has its own deep-dive page below.

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
- [B5 TIVA](B5.md) — Var(z) across studies should be ≥ 1
- [B6 GRIMMER](B6.md) — extends GRIM to SD consistency
- [B7 P-Curve](B7.md) — left-skewed or near-α pile-up = p-hacking
- [B8 SPRITE](B8.md) — iterative integer-sample reconstruction

### RCT integrity
- [C1 Carlisle Baseline-Balance](C1.md) — Welch t per variable + Stouffer

### Variance structure
- [D1 Residual Smoothness](D1.md) — block-variance stability check
- [D2 Missing-Data Pattern](D2.md) — 0% missing + low column-σ variation

### Image forensics
- [F1 pHash Cross-Image](F1.md) — Hamming-distance on perceptual hash
- [F2 Internal Image Duplication](F2.md) — ORB+RANSAC affine consensus
- [F3 Splice / Copy-Move](F3.md) — block-statistic + translation vote
- [F4 Cross-Paper Image Duplication](F4.md) — persistent pHash SQLite store
- [F5 EXIF Cross-Image Clustering](F5.md) — multi-image timeline + camera consistency

### Metadata forensics
- [G1 EXIF Temporal](G1.md) — per-image acquisition time vs claimed dates
- [G3 Docx rsid](G3.md) — python-docx / pandoc vs Word edit detection
- [G4 File Metadata](G4.md) — creator / created / revision audit

### Text / trial forensics
- [T1 Text Similarity (n-gram)](T1.md) — Jaccard against user corpus
- [T2 Clinical-Trial Outcome](T2.md) — paper vs ClinicalTrials.gov outcome
- [T3 Data Availability + Ethics](T3.md) — ICMJE / FAIR / NCT registration
- [T4 Tortured Phrases](T4.md) — paper-mill MT signatures (PPS dict)
- [T5 Stylometry](T5.md) — Stapel linguistic fingerprint
- [T6 AI-Generated Text Heuristic](T6.md) — LLM leakage + style density

## How to read a detector page

Each page has:

1. **What it detects** — one paragraph
2. **Method** — algorithm + thresholds
3. **Inputs** — what data shape it expects
4. **Severity ladder** — how findings escalate
5. **Innocent explanations** — non-fraud reasons it might fire
6. **Known false positives / negatives**
7. **Academic basis** — citation
8. **Source** — path to implementation
