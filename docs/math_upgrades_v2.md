# Math Upgrades v2 (PaperGuard 2.0.13)

Three statistical depth upgrades layered onto the existing A1 / A2 / A3
detectors. All three preserve the original test as the primary signal
and **add** new finding types that catch fabrication patterns the
original single-pass statistics cannot.

None of the new tests fire on the existing `tests/fixtures/genuine_random.csv`
(verified via the golden anti-regression test) and all three correctly
fire on synthetic fabrication patterns (verified via 16 new unit tests
in `tests/test_math_upgrades_v2.py`).

## Why "extra depth" is needed

The v0-v2.0.12 detectors used **independent single-statistic tests per
column**. Skilled fabricators can defeat these by varying the surface
statistic per column:

- A1's χ²(9) is column-wise. A fabricator who shuffles last digits
  per column passes.
- A3's pair-wise difference test is two-column. A fabricator who
  uses `col4 = 2*col1 + col2` passes.
- A2's Benford test is whole-column. A fabricator using a single
  template + many segments passes (template within each segment looks
  Benford-ish on average).

v2.0.13 closes these holes with three orthogonal axes of evidence:

| Axis | Tests fabrication pattern |
|---|---|
| **Lag-1 autocorrelation** (A1) | "I varied my digits but each time I avoided repeating the previous" |
| **Cross-column joint entropy** (A1) | "I bashed in one row at a time, my row digits aren't independent across columns" |
| **Multivariate OLS** (A3) | "I derived this column from a linear combination of the others" |
| **Segment Benford variance** (A2) | "I generated this in batches from one template" |

## A1 — Lag-1 autocorrelation

### Statistic

For a sequence of N digits `d_1 d_2 ... d_N` (the last-significant
digit of each value in a column):

- Count `M = #{i : d_i = d_{i+1}}` (lag-1 matches)
- Under H_0 (i.i.d. uniform digits): `M ~ Binomial(N-1, 1/10)`
- Test statistic: `z = (M - (N-1)/10) / sqrt((N-1)·0.1·0.9)`
- Two-sided p-value via standard normal

### Why it works

- Real measurements are i.i.d. → `M ≈ (N-1)/10`
- Fabricators "avoiding repeats" → `M ≪ (N-1)/10` (negative auto-corr)
- Fabricators using a periodic template → `M ≫ (N-1)/10` (positive)

### Severity

- p < 1e-4 → SUSPICIOUS
- p < 0.01 → CONCERN
- N < 50 → not applicable

### Reference

Ljung & Box (1978). *On a measure of lack of fit in time series models*.
Biometrika 65(2): 297-303. Our binomial-on-lag-1 is a simplification of
the Ljung-Box Q-statistic for digit-sequence data.

## A1 — Joint multi-column entropy

### Statistic

For a matrix of digits `D[i, j]` (N rows × K columns, where K is the
number of numeric columns):

1. For each row `i`, compute the digit-entropy:
   `H_i = -Σ_d p_d log_2(p_d)` where `p_d = c_d / K` and `c_d` counts
   occurrences of digit `d` in row `i`.
2. Compute the observed mean entropy `Ȟ = (1/N) Σ_i H_i`.
3. Under H_0 (each column independent + each row's digits i.i.d.
   uniform), simulate 200 bootstrap replicates of N×K random digit
   matrices and compute the empirical mean and standard deviation of
   `Ȟ` under H_0.
4. Test statistic: `z = (Ȟ - boot_mean) / boot_std`. Two-sided p-value.

### Why it works

Manual fabrication often happens row-by-row ("I'll write a row of fake
measurements at a time"). The fabricator's row-internal correlations
deviate from the per-cell-independent null. Specifically, rows tend to
have lower digit entropy (e.g. the fabricator typed similar digits
across columns of one row).

### Severity

- p < 1e-4 → SUSPICIOUS
- p < 0.01 → CONCERN
- min_rows < 30 or n_cols < 2 → not applicable

## A3 — Multivariate OLS synthetic-combination detector

### Statistic

For each target column `c`, fit OLS regression:

`c ≈ β_0 + Σ_{p ≠ c} β_p · p`

using `numpy.linalg.lstsq`. Compute:

- `R²` (coefficient of determination)
- `σ_resid` (residual standard deviation)
- `n_nonzero` (count of coefficients with `|β| ≥ 0.01 · max|β|`,
  a sparsity proxy without requiring sklearn)

### Severity

- `R² ≥ 0.99999` AND `σ_resid < 1e-5` → **CRITICAL** (perfect linear
  derivation; column is mathematically synthesized)
- `R² ≥ 0.9999` AND `n_nonzero ≤ 2` → **SUSPICIOUS** (simple sparse
  combination, e.g. `c = 2·a + b`)
- `R² ≥ 0.999` → **CONCERN** (very high collinearity worth
  investigating)
- Otherwise no finding

### Why it works

Pair-wise A3 catches `col_a = col_b + k` but misses
`col_d = 2·col_a + col_b - 0.3`. A 3+-way linear synthesis from
honest data is rare; from fabricated data it's common (the
fabricator computes a "result" column from the others).

### Why the thresholds are so strict

Honest biological measurements are often correlated (e.g. two
temperatures, two enzyme rates). R² of 0.95-0.99 is normal in
real data. We only fire when R² is so close to 1 that the column
is mathematically derived, not merely correlated.

### Why not Lasso?

A real Lasso (L1-regularized regression) would give exact zero
coefficients for unused predictors, making sparsity unambiguous.
Adding scikit-learn as a runtime dependency for one detector
would inflate `pip install paperguard` by ~80 MB. The 1%-of-max
proxy correctly identifies the sparse cases in our test fixtures
without the bloat. Users who need rigorous L1 can run
`paperguard.detectors.a3_arithmetic._multivariate_synthetic_check`
post-hoc with sklearn-fitted coefs.

## A2 — Segment Benford stability

### Statistic

For each column passing the standard Benford applicability test
(N ≥ 50, dynamic range ≥ 2 decades):

1. Split the first-digit list into `N_seg = 3` ordered segments
   `S_1, S_2, S_3` of size ≈ N/3.
2. For each segment, compute the standard Benford χ²(8):
   `χ²_i = Σ_d (O_d^i - E_d^i)² / E_d^i`
3. Compute `Var(χ²_1, χ²_2, χ²_3)` and `Mean(χ²_1, χ²_2, χ²_3)`.

### Severity

- `Var < 0.5` AND `Mean > 5.0` → CONCERN

### Why it works

Real natural data is non-stationary: small subsets have noisy
first-digit distributions. The χ² statistic on N≈70 samples typically
fluctuates by several units between segments due to sampling error.

Fabricators who batch-generate data from a single template produce
near-identical first-digit distributions in each segment → variance
collapses.

### Why the `Mean > 5.0` condition

When real data is genuinely Benford-distributed, every segment will
have χ² ≈ 0 with low variance — but that's not fabrication, that's a
clean Benford fit. We only fire when the segments are uniformly
*non-Benford* (mean χ² > 5 across 3 segments) AND stable across
segments (var < 0.5) — i.e. the same non-Benford pattern in every
segment.

## What these upgrades do NOT do

Honest limitations:

1. **No defence against a sophisticated multi-statistic-aware
   fabricator**. A fabricator who explicitly simulates real data with
   `np.random.normal()` + adds realistic noise will pass all four new
   tests. This is a physical limit (real Gaussian noise is statistically
   indistinguishable from real Gaussian noise) and no detector can
   close it without external evidence.
2. **No improvement on the v7 PDF-only recall**. The v7 study (LR+ 0.62)
   measured how PaperGuard performs on **paper PDFs**, which mostly
   don't carry raw data tables. These upgrades only help when the
   user has actual `.csv` / `.xlsx` raw data.
3. **Bootstrap p-values have finite-sample noise**. The 200-replicate
   bootstrap in the joint-column test gives p-values with ±5%
   variability at p ≈ 0.05. For paper-mill-scale screening, 200 is
   enough; for forensic publication, increase manually.

## Recommended workflow with v2.0.13

1. Always scan raw data files (`.csv`, `.xlsx`) alongside the PDF.
2. Treat any SUSPICIOUS+ finding from the multivariate or joint-column
   tests as a **prompt to ask the authors for the data-generation
   protocol** — not a verdict.
3. Cross-check with external signals (PubPeer commentary, author
   retraction history, ClinicalTrials.gov registration) before forming
   any opinion.
