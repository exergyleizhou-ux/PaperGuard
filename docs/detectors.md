# PaperGuard Detectors — Reference

This document is the canonical per-detector reference: what each one does,
the academic basis, what triggers it, **expected false-positive sources**,
and how to disable or tune it.

## Severity scale

| Level | Meaning | When emitted |
|-------|---------|--------------|
| PASS | No anomaly | Default |
| NOTE | Curiosity | Single weak signal |
| CONCERN | Single-detector worth looking | p < 0.01 single test |
| SUSPICIOUS | Cross-cluster signals | ≥ 2 independent assumption clusters |
| CRITICAL | Joint impossibility | Contains a CRITICAL finding OR ≥ 3 cross-cluster CONCERN+ |

Every finding includes `innocent_explanations` listing at least three
plausible non-misconduct causes. **No finding is by itself a fraud claim.**

---

## Numeric-forensics cluster (`digit_distribution`, `inter_column_relation`)

### A1 — Terminal Digit Distribution

- **Basis:** Mosimann et al. (1995) Accountability in Research.
- **What:** χ²(9) goodness-of-fit on the trailing significant digit of every
  value in a numeric column.
- **Triggers when:** p < 0.01 (CONCERN), p < 1e-6 (SUSPICIOUS), p < 1e-20
  (CRITICAL).
- **Special signal:** Digit 0 + digit 5 jointly > 40% adds a CRITICAL marker
  ("preferred-round-number" fabrication pattern).
- **False positives:** Instrument quantization (balance with 0.05 g step);
  forced rounding to a specific precision; cultural number preferences in
  self-reported data; computed (not measured) columns.

### A2 — Benford First-Digit

- **Basis:** Benford (1938); Nigrini (2012).
- **What:** χ²(8) GoF against Benford's expected distribution
  `P(d) = log10(1 + 1/d)`.
- **Applicability gate:** Column must span ≥ 2 orders of magnitude and have
  ≥ 50 values; otherwise skipped.
- **False positives:** Narrow-range data (heights, blood pressure); bounded
  computed quantities; biased sub-sampling.

### A3 — Inter-Column Arithmetic Relation

- **What:** For every numeric column pair, check if `col_a - col_b` has
  `σ ≈ 0` (constant difference) or `col_a / col_b` ≈ const (constant ratio).
- **Triggers when:** 100% exact match → CRITICAL; ≥ 95% → SUSPICIOUS;
  any match → CONCERN.
- **False positives:** Spreadsheet-formula columns (`= A1 + 0.3`); fixed
  zero-offset calibration; one column is a derived measure of another.

### A5 — Decimal Fraction Consistency

- **What:** Counts unique fractional-part strings within a column. Few unique
  fractions across many values suggests data is from a discrete set rather
  than continuous measurement.
- **Triggers when:** Unique-ratio < `a5_max_unique_ratio` (default 0.3) and
  the dominant fraction repeats ≥ 50% (SUSPICIOUS) or 100% (CRITICAL).
- **False positives:** Rounded data with coarse precision; calculated
  quantities; data from limited discrete experimental set.

---

## Summary-statistic-consistency cluster

### B1 — GRIM (Brown & Heathers 2017)

- **What:** For Likert-scale integer data with reported `mean`, `N`,
  `decimal_places`: check whether `mean × N` is within
  `0.5 × 10^-decimals × N` of an integer.
- **Caller responsibility:** Only feed integer-scale data; the detector
  cannot tell whether your data is integer.

### B4 — Statcheck (Nuijten et al. 2016)

- **What:** Regex-extract `t(df) = X, p = Y` / `F(df1, df2) = X, p = Y` /
  `χ²(df) = X, p = Y` / `r(df) = X, p = Y` / `z = X, p = Y` /
  `Q(df) = X, p = Y` (meta-analysis heterogeneity), recompute the
  two-tailed p, and flag mismatches.
- **One-tailed handling:** If the whole manuscript text contains "one-tailed
  / one-sided / 单尾", and a finding would be consistent under a one-tailed
  recompute, the detector silently switches to one-tailed for that match
  (statcheck-equivalent heuristic).
- **Outputs:** Numeric inconsistency → CONCERN; decision reversal across
  α = 0.05 → SUSPICIOUS.
- **False positives:** Mid-mainscript p-values come from non-NHST procedures
  (Bayes factors, permutation tests, mixed-effects models that don't report
  the test statistic + df); rounded test stats; corrected (BH-FDR) p-values.

### B5 — TIVA (Schimmack 2014)

- **What:** Convert k independent p-values to z, check `χ²(k-1) = OV × (k-1)`
  in the left tail. `Var(z) ≪ 1` → published z's are unrealistically clustered.
- **Caller responsibility:** Provide truly independent studies' p-values
  (one per study), not multiple outcomes from one study.

### B6 — GRIMMER (Anaya 2016; Allard 2018)

- **What:** Extends GRIM to standard deviations. Checks whether the reported
  `(mean, SD, N)` triple is jointly compatible with an integer sample.
- **Stricter than B1:** A B1-pass can still fail B6.

---

## Image-forensics cluster

### F1 — Image Duplication (perceptual hash)

- **What:** pHash every extracted figure, find pairs whose Hamming distance
  is ≤ 8 (CONCERN), ≤ 5 (SUSPICIOUS), ≤ 2 (CRITICAL).
- **Filter:** PDF embeds are excluded if < 200×200 px or < 8 KB (these are
  math glyphs / Nature letterhead / decorations, not science figures).
- **False positives:** Same Western blot with different exposures; figure
  reused intentionally across panels; low-texture images cluster in pHash
  space.

### F2 — Internal Image Duplication (ORB + RANSAC)

- **Basis:** Bik et al. (2016) mBio; Brown & Lowe (2003) RANSAC.
- **What:** Compute ORB keypoints on a single image, self-match descriptors,
  filter for non-trivial translations, run RANSAC for affine consensus.
  ≥ 20 inliers → CONCERN, ≥ 40 → SUSPICIOUS.
- **Limit:** Low-texture images (stains, uniform backgrounds) give noisy
  ORB matches; F2 misses Bik-style splicing on these. Use F3 for such cases.

### F3 — Splice / Copy-Move Forensics

- **Basis:** Cozzolino & Verdoliva (2015) Splicebuster.
- **What:** Block-statistic signatures (mean, std, Laplacian variance) with
  RANSAC-style translation-vote consensus. Spots Bik-style cloning in
  low-texture images that F2 misses.
- **Caller tuning:** `patch_size`, `stride`, `similarity_threshold`,
  `min_pair_distance`. Defaults work for typical 400-800 px scientific images.

---

## Metadata-forensics cluster

### G1 — Image EXIF Temporal Forensics

- **What:** Reads EXIF `DateTimeOriginal`, `Make`, `Model`, `Software`.
  Flags:
  - Capture before claimed `experiment_start` → CRITICAL
  - Capture after claimed `submission_date` → CRITICAL
  - Inconsistent `Make` across same-instrument claim → CONCERN
  - Photoshop / GIMP signature in `Software` → CONCERN

### G3 — Docx rsid Forensics

- **Basis:** OOXML ECMA-376 §17.15.1.55.
- **What:** Word stamps every save with a `w:rsid*` revision-tracking ID.
  python-docx / pandoc / docx4j produce files with 0–3 rsids and no
  paragraph-level rsids — a clear "machine-generated" fingerprint.
- **False positives:** Author used LibreOffice / Google Docs / WPS;
  document was exported then re-saved through a cleaner.

### G4 — File Metadata Forensics

- **What:** Reads `created` / `modified` / `revision` / `creator` from
  xlsx/docx/pdf and checks against claimed timeline / authors.
- **Publisher whitelist:** Springer / Elsevier / Wiley / LaTeX /
  pdfTeX / Acrobat Distiller / Word / LibreOffice etc. as `creator` are
  never flagged as "non-author creator" — these are publishing artifacts.

---

## Text-forensics cluster

### T1 — Text Similarity (Brin et al. 1995; Schleimer 2003)

- **What:** 5-gram word-shingling of the query against a user-supplied
  corpus, Jaccard similarity.
- **Triggers:** `≥ 0.10` (CONCERN), `≥ 0.25` (SUSPICIOUS), `≥ 0.50` (CRITICAL).
- **Caller responsibility:** Build the corpus yourself (preprints by the
  same author, previously published versions, etc.). The detector does not
  fetch from the open web.

### T2 — Clinical-Trial Outcome Consistency (Goldacre 2019)

- **What:** For a given NCT ID, fetch primary outcomes from
  ClinicalTrials.gov v2 API and compare against the paper's reported
  primary outcomes (token-overlap threshold 0.4).
- **Caller responsibility:** Provide both the NCT ID and the paper's stated
  primary outcomes.

### T3 — Data Availability + Ethics Audit

- **Basis:** ICMJE data-sharing guidelines; Gabelica et al. (2022) on
  "available on request" compliance.
- **What:** Regex-scans manuscript text for:
  - Data availability statement presence
  - Verifiable accession (DOI, GEO, SRA, BioProject, ArrayExpress, Zenodo,
    figshare, Dryad, GitHub)
  - "available upon reasonable request" without any accession (CONCERN)
  - Trial registration ID if the caller flags `is_clinical_trial=True`
  - IRB / IACUC / ethics-committee approval if `is_human_subjects=True`
    or `is_animal_study=True`
  - Competing-interests disclosure

### T4 — Tortured Phrases (Cabanac et al. 2021)

- **Basis:** Problematic Paper Screener (PPS), IRIT.
- **What:** Match a curated dictionary (~50 entries) of known
  machine-translated / synonym-laundered phrases that appear in paper-mill
  fingerprints (e.g., "profound neural organization" for "deep neural
  network").
- **Triggers:** Any single match → SUSPICIOUS; ≥ 3 distinct phrases or
  ≥ 5 total hits → CRITICAL. Tortured phrases almost never appear in
  legitimate academic prose, so false-positive rate is low.

---

## Randomization-check cluster

### C1 — Carlisle Baseline-Balance (Carlisle 2017)

- **What:** For an RCT's baseline-variable table, run a Welch t per
  variable, combine p-values via Stouffer; both extreme tails flag as
  non-random.
- **Caller responsibility:** Provide a `CarlisleInput` with ≥ 5 baseline
  variables, each as `BaselineVariable(name, n1, mean1, sd1, n2, mean2, sd2)`.

---

## Cluster aggregation

`evidence/combiner.py` computes the overall severity:

1. Any CRITICAL finding **OR** ≥ 3 distinct assumption clusters with
   CONCERN+ → **CRITICAL**.
2. Any SUSPICIOUS finding **OR** ≥ 2 distinct clusters with CONCERN+ →
   **SUSPICIOUS**.
3. ≥ 1 CONCERN → **CONCERN**.
4. ≥ 1 NOTE → **NOTE**.
5. Otherwise → **PASS**.

The cluster-based escalation prevents a single noisy detector from causing
SUSPICIOUS on its own; it requires independent lines of evidence.
