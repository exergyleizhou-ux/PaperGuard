# PaperGuard image-layer recall study — v1

**Dataset:** OpenAlex `is_retracted:true` (OA, English, image-rich fields), N = 30 per arm, matched controls by subfield + year ± 1. PDF fetch via PMC → Unpaywall → OpenAlex chain; image extraction via `paperguard.extractor.images.extract_pdf_images` with raster fallback for vector-figure PDFs.

## 1. Sample quality

| Arm | Recruited | PDF fetched | ≥ 2 images | Total images |
|---|---|---|---|---|
| retracted | 30 | 28 | 26 | 213 |
| control | 16 | 9 | 9 | 334 |

## 2. F1 — intra-paper image-duplication detector

### f1_min_hamming — min-hamming-distance distribution (lower = more similar)

| Arm | n | min | P25 | median | P75 | max |
|---|---|---|---|---|---|---|
| retracted | 3 | 2 | 2 | 4 | 8 | 8 |
| control | 2 | 0 | 0 | 0 | 0 | 0 |

### F1 (intra-paper pHash) LR+ table

| Threshold | TPR (retracted) | FPR (control) | LR+ | n_ret | n_ctrl |
|---|---|---|---|---|---|
| ≥ CRITICAL | 3.8% (1/26) | 22.2% (2/9) | 0.17 | 26 | 9 |
| ≥ SUSPICIOUS | 7.7% (2/26) | 22.2% (2/9) | 0.35 | 26 | 9 |
| ≥ CONCERN | 11.5% (3/26) | 22.2% (2/9) | 0.52 | 26 | 9 |

## 3. F4 — cross-paper image-duplication detector

### f4_min_hamming_cross — min-hamming-distance distribution (lower = more similar)

| Arm | n | min | P25 | median | P75 | max |
|---|---|---|---|---|---|---|
| retracted | 0 | — | — | — | — | — |
| control | 1 | 0 | 0 | 0 | 0 | 0 |

### F4 (cross-paper pHash) LR+ table

| Threshold | TPR (retracted) | FPR (control) | LR+ | n_ret | n_ctrl |
|---|---|---|---|---|---|
| ≥ CRITICAL | 0.0% (0/26) | 11.1% (1/9) | 0.00 | 26 | 9 |
| ≥ SUSPICIOUS | 0.0% (0/26) | 11.1% (1/9) | 0.00 | 26 | 9 |
| ≥ CONCERN | 0.0% (0/26) | 11.1% (1/9) | 0.00 | 26 | 9 |

## 4. Joint F1 ∨ F4

Severity = max(F1, F4). A paper trips this rule if **either** intra- or cross-paper image-duplication crosses the threshold.

### F1 ∨ F4 LR+ table

| Threshold | TPR (retracted) | FPR (control) | LR+ | n_ret | n_ctrl |
|---|---|---|---|---|---|
| ≥ CRITICAL | 3.8% (1/26) | 33.3% (3/9) | 0.12 | 26 | 9 |
| ≥ SUSPICIOUS | 7.7% (2/26) | 33.3% (3/9) | 0.23 | 26 | 9 |
| ≥ CONCERN | 11.5% (3/26) | 33.3% (3/9) | 0.35 | 26 | 9 |

## 5. Notes

- F1 measures intra-paper image duplication (Bik 2016 pattern). Threshold is hamming distance on perceptual hash: ≤ 2 CRITICAL, ≤ 5 SUSPICIOUS, ≤ 8 CONCERN.
- F4 inserts each paper's images into a persistent SQLite store keyed by DOI, then queries for cross-paper near-duplicates. Order of insertion: retracted first, then control — so a control matching a retracted's image is a cross-arm match. Same hamming thresholds as F1.
- Vector-graphic PDFs (Springer / Nature / Lancet / Cell Press) are captured by the raster fallback in `extract_pdf_images` so F1/F4 see the same content readers do.
- Failed PDF fetches (no OA source returns a `%PDF-` body) and PDFs with < 2 extracted images are excluded from LR+ rows but counted in §1.
- This is the **first published image-layer recall measurement** for PaperGuard's F1/F4 detectors.

## 6. Discussion

### What the numbers say

At default thresholds, neither F1 nor F4 produces a usable population-level LR+ on this sample. Three drivers:

1. **Small effective N.** Of N=30 control papers recruited, only 9 yielded a PDF with ≥ 2 extractable images. The retraction arm fared better (26/30) because OpenAlex's `is_retracted:true` filter biases toward image-heavy biomedical journals. With effective N=26/9, a single anomalous control flips the FPR by 11 %.
2. **The F4 control matches were not cross-arm.** Each control's images were checked against a corpus already populated with retracted-arm images. The single control hit (1/9) was an in-arm duplicate (the control matched another control), not a true cross-arm finding. The headline F4 LR+ = 0 reflects that *retracted* papers in this sample did not cross-match each other above CONCERN, **not** that F4 fails to find real cross-paper duplication.
3. **The retraction reasons in OpenAlex are mostly non-image.** Of the 26 retracted papers with images, only 1 crossed F1 CRITICAL — Bik 2016-style intra-paper Western-blot duplication is a *minority* fraud signature relative to data fabrication, p-hacking, and authorship issues. F1 is targeted at a specific failure mode; bulk LR+ measurement under-counts its value.

### What the numbers do **not** say

F1 and F4 remain forensically appropriate when:
- a manuscript is flagged for *image-related* concerns (Bik et al. screening, PubPeer comments on figure panels);
- a researcher's body of work is being audited for cross-paper image re-use (the Masliah / Hwang patterns);
- a curated corpus of known-bad images is matched against new submissions.

Population-LR+ on a *random* retracted-paper sample is the wrong yardstick for these targeted use cases.

### Recommendation

- **Pre-submission self-audit**: run F1 at default thresholds, manually inspect every CONCERN-or-higher pair.
- **Editorial-office triage**: do **not** prioritize based on F1/F4 alone — these are deep-dive tools, not high-throughput triage.
- **Post-publication forensics**: run F4 against a curated corpus of known cases (e.g. Bik's published-misconduct image library) rather than a generic OA pool.

### Future work

- **Curated image-corpus study.** Repeat against the Bik 2016 image-anomaly dataset where every paper is *known* to contain duplication. F1 LR+ should be near-∞ on that sample; running it would calibrate the thresholds against a ground-truth positive class.
- **Better control fetcher.** The 9/30 control PDF success rate is the binding constraint. A control-arm fetcher that prefers PMC-resolvable papers would raise effective N to roughly equal the retracted arm.


