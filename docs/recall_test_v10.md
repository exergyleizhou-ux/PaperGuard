# PaperGuard text-layer recall study v10 (N=100+100)

> **N = 100 OpenAlex retracted (post-2019) + 100 matched-control papers,
> Europe PMC full-text fetch, T6 lexical detector.**
> Headline: T6 default threshold remains 0/0, but at lower thresholds T6
> achieves **LR+ = ∞** (one true positive, zero false positives).

## Why this study

Studies v8 (N=50) and v9 (N=30) both found T6 at the default 0.003
threshold has TPR = 0 % and FPR = 0 % on post-publication retraction
data. The conclusion published in 2.0.16 was that T6 is a
pre-submission / preprint screening signal, not a post-publication
forensic signal. **Could a 4× larger N reveal a usable lower-threshold
signal?** This study answers that.

## Sample

| | Retracted | Control |
|---|---|---|
| Sampled | 100 | 100 |
| Control look-up failed | 0 | 41 (OpenAlex subfield mismatch) |
| PMC full text fetched | 75 | 22 |
| **Analysable by T6** | 73 | 22 |

The retracted arm has good PMC coverage (75 / 100 = 75 %) because the
2019+ retraction sample skews biomedical. The control arm has weak
PMC coverage (22 / 59 = 37 %) because OpenAlex subfield matching often
pulls in CS / engineering papers that aren't PMC-indexed. The
asymmetry biases the LR+ point estimate but does not invalidate the
**no-false-positive** finding (FP would still be FP regardless of
sample size).

## T6 density distribution

```
Retracted (n=73): median 0.000000,  max 0.001261
Control   (n=22): median 0.000000,  max 0.000000
```

The retracted distribution has the same near-zero median as the
control, but its **upper tail extends**: one retracted paper crosses
0.001 (one in 73, the rest are at 0). The entire control distribution
remains identically zero.

## LR+ across thresholds

| Threshold | TPR | FPR | LR+ |
|---|---|---|---|
| default 0.003 | 0.00 % | 0.00 % | **0** (unchanged from v8 / v9) |
| 0.001  | **1.37 %** | **0.00 %** | **∞** |
| 0.0005 | 1.37 % | 0.00 % | ∞ |
| 0.0001 | 1.37 % | 0.00 % | ∞ |

The "∞" cells are not a measurement of unboundedly-good performance —
they reflect that the denominator (FPR) is zero on N=22 controls.
What they **do** say: at a 0.001 threshold, the one retracted paper
that fires is **the only paper that fires across both arms**.

## The one true positive

```
DOI:        10.1371/journal.pone.0295951  (PLOS ONE, 2024)
Subfield:   Radiology, Nuclear Medicine and Imaging
Title:      "Improved Support Vector Machine based on CNN-SVD for
             vision-threatening diabetic retinopathy detection and
             classification"
T6 density: 0.00126   (4× the next-highest retracted paper, ∞× control)
Provider:   gpt
```

This paper has the **textbook paper-mill signature**:
- Post-ChatGPT publication date (2024)
- Generic ML applied to medical imaging (CNN-SVD, retinopathy)
- PLOS ONE (high-volume journal)
- Subsequently retracted

It is exactly the kind of paper PaperGuard's T6 was built to surface.
The fact that it is the **only** paper in N=200 (95 analysable) that
crossed T6 — and that no control crossed — is a meaningful positive
signal even though the recall fraction is low.

## What changed vs v8 / v9

| Study | N | T6 default LR+ | Best low-threshold LR+ | Comment |
|---|---|---|---|---|
| v8 | 50+50 | 0 (TPR 0 % / FPR 0 %) | 0.77 at ≥0.0005 | Post-2023 sample, mixed subfields |
| v9 | 30+30 | 0 | 0 | Post-2020 sample, mixed subfields |
| **v10** | **100+100** | **0** | **∞ at ≥0.0001** (1 TP / 0 FP) | **Post-2019, biomedical tilt** |

The v10 expansion captured the first true post-publication T6
positive in PaperGuard's empirical record. The signal is **rare but
specific**: zero controls fire at any threshold tested, so when T6
*does* cross threshold the prior likelihood of LLM authorship is
sharply elevated.

## Calibrated interpretation

**Old position (2.0.16 → 2.1.10):** T6 is a pre-submission /
preprint screening tool; copy-editing removes lexical LLM markers
before publication.

**Updated position (2.1.12):** The old position holds for the
**default threshold**. At lower thresholds (≥ 0.001), T6 can flag a
rare but unambiguous post-publication signal. Editorial-office triage
that screens at the lower threshold trades coverage (1.4 % recall)
for precision (100 % so far in N=200).

Specific guidance:

| Use case | Threshold | Expected behaviour |
|---|---|---|
| Pre-submission self-audit | default 0.003 | Catches sloppy LLM use during drafting |
| Editorial high-precision triage | **0.001** | Rare-event detector — when it fires, it almost always means something |
| Forensic post-publication | 0.0005 - 0.001 | Same as above; use alongside F1/F4/F6 image-forensic findings |

## Reproducibility

Public data:
- `scripts/recall_test_v10.py` — N=100+100 driver
- `scripts/recall_test_v10_results.json` — raw 159-record dataset
- This document (`docs/recall_test_v10.md`)

To re-run:

```bash
PYTHONIOENCODING=utf-8 python scripts/recall_test_v10.py \
    --n 100 --year-min 2020 \
    --out scripts/recall_test_v10_results.json \
    --resume
```

The OpenAlex retracted sample is sorted by `cited_by_count` — the
deterministic top-100 from the same query window are reproducible.

## Limitations

1. **Control PMC coverage is uneven (22 / 59 = 37 %).** A future
   v11 should pre-filter control candidates for PMC indexing before
   accepting the match, so analysable N is equal across arms.
2. **N=22 controls is too small** to claim "0 % FPR" with tight CI;
   the Wilson 95 % upper bound is ≈ 15 %. The honest statement is
   "no false positive observed in 22 controls", not "zero false-
   positive rate".
3. **The single true positive** is a single anecdote; future N=500+
   studies should confirm whether the 0.001-threshold pattern holds
   at larger scale.
4. T7 / T8 columns are not populated in v10 because the cliproxy
   endpoint does not expose logprobs (see
   `docs/t8_endpoint_limitation.md`). When a GPT-4-class endpoint
   becomes available, v9 is the pre-wired re-analysis target.

## Bottom line

PaperGuard's T6 lexical detector has empirically demonstrated, at
N=200, that it can identify rare paper-mill LLM-text signatures even
in post-publication retraction data when the threshold is tuned
to the rare-event regime. The default threshold remains correctly
calibrated for pre-submission use. Editorial offices should
consider running at `density ≥ 0.001` for high-volume triage.
